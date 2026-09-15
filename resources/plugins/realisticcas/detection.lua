-- Incremental spatial search. All engine reads are injected; no global scan.
assert(RealisticCAS and RealisticCAS.Sensors, "load core.lua and sensors.lua first")
do
  local S=RealisticCAS.Sensors
  function RealisticCAS.newDetection(options)
    local o=options or {}
    for _,name in ipairs({"clock","readObserver","readTarget","environment","lineOfSight","reveal"}) do
      assert(type(o[name])=="function",name.." callback required")
    end
    local cellSize=o.cellSize or 5000
    assert(S.finite(cellSize) and cellSize>=1000 and cellSize<=50000,"invalid cell size")
    local targetBudget=o.targetBudget or 64
    local workBudget=o.workBudget or 128
    local observerBudget=o.observerBudget or 64
    local losBudget=o.losBudget or 64
    local observerQuantum=o.observerQuantum or 128
    for _,n in ipairs({targetBudget,workBudget,observerBudget,losBudget,observerQuantum}) do
      assert(S.finite(n) and n>=1 and n<=4096 and n==math.floor(n),"invalid work budget")
    end
    local revisit=o.revisit or 5
    assert(S.finite(revisit) and revisit>=1 and revisit<=300,"invalid revisit")
    -- Zero retains the isolated sensor-probe contract. Campaign integration will
    -- explicitly enable search time; one unknown group can occupy each observer.
    local acquisition=o.acquisitionSeconds or 0
    assert(S.finite(acquisition) and acquisition>=0 and acquisition<=600,"invalid acquisition time")
    local maxGap=o.acquisitionMaxGap or math.max(60,revisit*2)
    assert(S.finite(maxGap) and maxGap>=revisit and maxGap<=3600,"invalid acquisition observation gap")
    if acquisition>0 then assert(type(o.isRevealed)=="function","contact visibility callback required") end
    local targets, observers, cells, membership={},{},{},{}
    local targetIds,observerIds={},{}
    -- Coarser coalition occupancy rejects empty sectors before fine-cell scans.
    -- Never depends on native AI detection (targets can be SetInvisible).
    local coarseSize=math.max(cellSize,25000)
    local occupied={}
    local targetCursor,observerCursor=1,1
    local job,enabled=nil,true
    local stats={targetReads=0,observerReads=0,candidates=0,los=0,reveals=0,errors=0,work=0,sweeps=0,
      rejectedEnvelope=0,blockedLOS=0,acquisitionStarts=0,acquisitionCompletions=0,
      acquisitionResets=0,pendingAcquisitions=0,maxSweepGap=0,overdueVisits=0,
      losBudgetHits=0,workBudgetHits=0,pendingJobs=0,culledObservers=0,cullChecks=0}
    local api={}
    local function log(kind,detail)
      if o.log then pcall(o.log,kind,detail) end
    end
    local nextWarning=0
    local function overdue(now,detail)
      stats.overdueVisits=stats.overdueVisits+1
      if now>=nextWarning then
        log("WARNING","perception scheduler overloaded: "..detail)
        nextWarning=now+60
      end
    end
    local function trace(kind,observer,id,target,detail)
      if not o.traceDecisions then return end
      local a,b=observer.point,target.point
      log(kind,string.format("%s -> %s|a=%.2f,%.2f,%.2f|b=%.2f,%.2f,%.2f|%s",
        job.observer.id,id,a.x,a.y,a.z,b.x,b.y,b.z,detail))
    end
    local function call(name,...)
      local ok,result=pcall(o[name],...)
      if not ok then stats.errors=stats.errors+1;log("ERROR",name..": "..tostring(result));return nil end
      return result
    end
    local function resetFocus(v,reason)
      if not v.focus then return end
      stats.pendingAcquisitions=stats.pendingAcquisitions-1
      stats.acquisitionResets=stats.acquisitionResets+1
      log("SEARCH_RESET",v.id.." -> "..v.focus.group.."|"..reason)
      v.focus=nil
    end
    local function acquired(v,target,now)
      if acquisition==0 then return true end
      local id=target.groupName or target.name
      assert(type(id)=="string","acquisition requires a target group/name")
      local f=v.focus
      if f and f.group~=id then return false end
      if f and now-f.last>maxGap then
        overdue(now,v.id.." acquisition observation gap="..(now-f.last))
        resetFocus(v,"observation gap");f=nil
      end
      if not f then
        f={group=id,last=now,progress=0,sweep=v.sweep}
        v.focus=f;stats.pendingAcquisitions=stats.pendingAcquisitions+1
        stats.acquisitionStarts=stats.acquisitionStarts+1
        log("SEARCH_START",v.id.." -> "..id.."|required="..acquisition)
        return false
      end
      -- Seeing ten members in one sweep is one group observation, not ten
      -- samples of search time. Scheduler stalls never count as continuous eyes-on.
      if f.sweep~=v.sweep then
        f.progress=f.progress+math.min(now-f.last,revisit)
        f.last=now;f.sweep=v.sweep
      end
      if f.progress<acquisition then return false end
      return true
    end
    local function key(x,z) return x..":"..z end
    local function unlink(id)
      local m=membership[id]
      if not m then return end
      local counts=occupied[m.coarse]
      counts[m.side]=counts[m.side]-1
      if counts[1]+counts[2]==0 then occupied[m.coarse]=nil end
      local bucket=cells[m.key]
      local last=table.remove(bucket)
      if m.index<=#bucket then bucket[m.index]=last;membership[last].index=m.index end
      if #bucket==0 then cells[m.key]=nil end
      membership[id]=nil
    end
    local function locate(id,p,side)
      local k=key(math.floor(p.x/cellSize),math.floor(p.z/cellSize))
      local ck=key(math.floor(p.x/coarseSize),math.floor(p.z/coarseSize))
      if membership[id] and membership[id].key==k and membership[id].coarse==ck and
        membership[id].side==side then return end
      unlink(id)
      cells[k]=cells[k] or {};local bucket=cells[k]
      bucket[#bucket+1]=id;membership[id]={key=k,index=#bucket,coarse=ck,side=side}
      occupied[ck]=occupied[ck] or {[1]=0,[2]=0}
      occupied[ck][side]=occupied[ck][side]+1
    end
    function api:addTarget(id)
      assert(type(id)=="string" and id~="","target unit name required")
      if targetIds[id] then return false end
      targetIds[id]=true
      targets[#targets+1]=id;return true
    end
    function api:addObserver(id,profile)
      assert(type(id)=="string" and id~="" and type(profile)=="table","observer and profile required")
      assert(S.finite(S.maxRange(profile)) and S.maxRange(profile)<=100000,"unsupported range")
      if observerIds[id] then return false end
      observerIds[id]=true
      observers[#observers+1]={id=id,profile=profile,nextVisit=0,sweep=0};return true
    end
    function api:stop()
      enabled=false;job=nil;cells={};membership={};occupied={}
      for _,v in ipairs(observers) do v.focus=nil;v.job=nil end
      stats.pendingAcquisitions=0
      stats.pendingJobs=0
    end
    function api:tick()
      if not enabled then return end
      local now=o.clock();assert(S.finite(now),"invalid clock")
      -- Each index refresh is bounded. Stale entries can delay a discovery, but
      -- candidates are re-read before every reveal: never publish stale truth.
      for _=1,math.min(targetBudget,#targets) do
        local id=targets[targetCursor];targetCursor=targetCursor%#targets+1
        stats.targetReads=stats.targetReads+1
        local t=call("readTarget",id)
        if t and S.vector(t.point) and (t.side==1 or t.side==2) then
          locate(id,t.point,t.side)
        else unlink(id) end
      end
      -- Round-robin slices share ONE tick budget. Dense observers retain their
      -- cursor without monopolising future ticks; inactive units also cost a slot.
      local used,losUsed,visits=0,0,0
      local quantum=math.min(observerQuantum,math.max(1,
        math.floor(workBudget/math.max(1,math.min(4,#observers)))))
      -- Do not repeatedly give a boundary observer only the last one or two
      -- work tokens. Leave its full slice for the next tick instead.
      while visits<math.min(observerBudget,#observers) and
        used<=workBudget-quantum and losUsed<losBudget do
        visits=visits+1
        local v=observers[observerCursor];observerCursor=observerCursor%#observers+1
        job=v.job
        if not job and now>=v.nextVisit then
          stats.observerReads=stats.observerReads+1
          local snapshot=call("readObserver",v.id)
          if snapshot and S.vector(snapshot.point) then
            if v.lastSweep then
              local gap=now-v.lastSweep
              stats.maxSweepGap=math.max(stats.maxSweepGap,gap)
              if gap>maxGap then overdue(now,v.id.." sweep gap="..gap) end
            end
            v.lastSweep=now
            v.sweep=v.sweep+1
            local r=S.maxRange(v.profile)
            job={observer=v, minX=math.floor((snapshot.point.x-r)/cellSize),
              maxX=math.floor((snapshot.point.x+r)/cellSize),
              minZ=math.floor((snapshot.point.z-r)/cellSize),
              maxZ=math.floor((snapshot.point.z+r)/cellSize), seen={}}
            job.x,job.z,job.item=job.minX,job.minZ,1
            job.culling=true
            job.cx0=math.floor((snapshot.point.x-r)/coarseSize)
            job.cx1=math.floor((snapshot.point.x+r)/coarseSize)
            job.cz0=math.floor((snapshot.point.z-r)/coarseSize)
            job.cz1=math.floor((snapshot.point.z+r)/coarseSize)
            job.cx,job.cz=job.cx0,job.cz0
          else resetFocus(v,"observer unavailable");v.nextVisit=now+revisit end
        end
        if job then
          stats.observerReads=stats.observerReads+1
          local observer=call("readObserver",job.observer.id)
          if not observer or not S.vector(observer.point) then
            resetFocus(job.observer,"observer unavailable");job=nil;v.nextVisit=now+revisit
          end
          local slice=0
          while job and used<workBudget and losUsed<losBudget and slice<quantum do
            slice=slice+1
            used=used+1;stats.work=stats.work+1
            if job.culling then
              stats.cullChecks=stats.cullChecks+1
              local counts=occupied[key(job.cx,job.cz)]
              local enemy=observer.side==1 and 2 or 1
              if counts and counts[enemy]>0 then
                job.culling=false
              else
                job.cz=job.cz+1
                if job.cz>job.cz1 then job.cz=job.cz0;job.cx=job.cx+1 end
                if job.cx>job.cx1 then
                  resetFocus(v,"no indexed enemy in range")
                  v.nextVisit=now+revisit;job=nil
                  stats.sweeps=stats.sweeps+1;stats.culledObservers=stats.culledObservers+1
                end
              end
            else
              local bucket=cells[key(job.x,job.z)]
              local id=bucket and bucket[job.item]
              if id then
                job.item=job.item+1
                if not job.seen[id] then
                  job.seen[id]=true;stats.candidates=stats.candidates+1
                  stats.targetReads=stats.targetReads+1
                  local target=call("readTarget",id)
                  if target and target.side~=observer.side and S.vector(target.point) then
                    local env=call("environment",observer,target,now)
                    local result,reason=S.assess(observer,target,env,job.observer.profile)
                    if result then
                      local v=job.observer
                      local known=acquisition>0 and call("isRevealed",target,observer)==true
                      local group=target.groupName or target.name
                      if known and v.focus and v.focus.group==group then resetFocus(v,"shared contact") end
                      -- Other unknown groups wait while this observer examines one.
                      -- Already shared contacts may still be observed/renewed normally.
                      local available=acquisition==0 or known or not v.focus or v.focus.group==group
                      if available then
                      stats.los=stats.los+1
                      losUsed=losUsed+1
                      if call("lineOfSight",observer.point,target.point)==true then
                        trace("LOS_CLEAR",observer,id,target,result.mode.."|distance="..result.distance)
                        if (known or acquired(v,target,now)) and call("reveal",target,observer,result)==true then
                          if acquisition>0 and not known then
                            stats.acquisitionCompletions=stats.acquisitionCompletions+1
                            stats.pendingAcquisitions=stats.pendingAcquisitions-1
                            v.focus=nil
                            log("SEARCH_COMPLETE",v.id.." -> "..group)
                          end
                          stats.reveals=stats.reveals+1
                          log("DETECT",job.observer.id.." -> "..id.." via "..result.mode)
                        end
                      else
                        stats.blockedLOS=stats.blockedLOS+1
                        trace("LOS_BLOCKED",observer,id,target,result.mode.."|distance="..result.distance)
                      end
                      end
                    else
                      stats.rejectedEnvelope=stats.rejectedEnvelope+1
                      trace("ENVELOPE_REJECT",observer,id,target,tostring(reason))
                    end
                  end
                end
              else
                job.item=1;job.z=job.z+1
                if job.z>job.maxZ then job.z=job.minZ;job.x=job.x+1 end
                if job.x>job.maxX then
                  local v=job.observer
                  if v.focus and v.focus.sweep~=v.sweep then resetFocus(v,"no valid observation this sweep") end
                  job.observer.nextVisit=now+revisit;job=nil;stats.sweeps=stats.sweeps+1
                end
              end
            end
          end
        end
        if v.job and not job then stats.pendingJobs=stats.pendingJobs-1 end
        if not v.job and job then stats.pendingJobs=stats.pendingJobs+1 end
        v.job=job
      end
      job=nil
      if used>=workBudget then stats.workBudgetHits=stats.workBudgetHits+1 end
      if losUsed>=losBudget then stats.losBudgetHits=stats.losBudgetHits+1 end
    end
    function api:getDiagnostics()
      local d={enabled=enabled,targets=#targets,observers=#observers,searching=stats.pendingJobs>0}
      for k,v in pairs(stats) do d[k]=v end
      return d
    end
    return api
  end
end
