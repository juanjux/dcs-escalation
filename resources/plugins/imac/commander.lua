-- Decision engine: all observations and native orders pass through an adapter.
assert(EscalationIMAC and EscalationIMAC.geometry,'load IMAC geometry first')
do
  local API,G=EscalationIMAC,EscalationIMAC.geometry
  local NM=1852
  function API.newCommander(config,io)
    local opt=config.options
    local api={states={},paused={},active=true,history={}}
    local now=0
    local tracks,threats,samples,authority={},{},{},{}
    for _,meta in ipairs(config.flights) do
      assert(not api.states[meta.group],'duplicate IMAC group')
      api.states[meta.group]={meta=meta,index=1,revision=0,cooldown=0}
    end
    local function record(s,kind,reason)
      local entry={time=now,group=s.meta.group,side=s.meta.side,kind=kind,reason=reason}
      api.history[#api.history+1]=entry
      if #api.history>128 then table.remove(api.history,1) end
      io.report(entry)
    end
    local function release(s,reason)
      if not s.order then return end
      s.revision=s.revision+1;s.order=nil;s.cooldown=now+30
      record(s,'resume',reason)
      -- No popTask: it could remove a tanker's or human commander's task.
    end
    local function nativeRefuel(s)
      local state=EscalationBARCAP and EscalationBARCAP.states[s.meta.group]
      return state and (state.refuelling or state.finished)
    end
    local function available(s,p)
      return p and p.airborne and not p.player and p.healthy and not p.refuelling and
        p.fuel>s.meta.bingo+0.05 and not nativeRefuel(s) and not s.paused and
        not api.paused[s.meta.side] and authority[s.meta.side] and not s.finished and
        (not s.meta.endTime or now<s.meta.endTime) and s.index<s.meta.recoveryIndex
    end
    local function push(s,kind,data,duration)
      if s.order or now<s.cooldown then return false end
      s.revision=s.revision+1
      s.order={kind=kind,data=data,issued=now,deadline=now+duration,revision=s.revision}
      local ok,why=io.order(s,s.order)
      if not ok then s.order=nil;s.cooldown=now+60;record(s,'error',tostring(why));return false end
      record(s,kind,data.reason or kind)
      return true
    end
    function api:reached(name,index)
      local s=self.states[name]
      if s and index>s.index then
        s.index=index
        if index>=s.meta.attackIndex then s.pendingHold=nil end
      end
    end
    function api:pause(side,value)
      self.paused[side]=value==true
      if value then for _,s in pairs(self.states) do if s.meta.side==side then release(s,'commander paused') end end end
    end
    function api:pauseFlight(name,value)
      local s=self.states[name]
      if s then s.paused=value==true;if value then release(s,'flight released for manual control') end end
    end
    function api:stop()
      self.active=false
      for _,s in pairs(self.states) do release(s,'commander stopped') end
    end
    function api:shouldStop(name,revision)
      local s=self.states[name]
      if not self.active or not s or not s.order or s.revision~=revision then return true end
      -- Native stop conditions also run between decision ticks. BINGO, player
      -- takeover, station expiry and loss of authority release tasks immediately.
      now=io.time()
      authority[s.meta.side]=io.authority(s.meta.side)
      if not available(s,io.sample(s.meta)) then
        release(s,'temporary order ended');return true
      end
      if now>=s.order.deadline then
        if s.order.kind=='hold' or s.order.kind=='recoveryHold' then
          -- Let the next decision cycle install recovery while the safe hold
          -- stays above the attack route. Native callback ordering is undefined.
          s.abortReason=s.abortReason or 'DEAD wait expired'
          s.order.deadline=now+opt.interval*2
        else release(s,'temporary order expired');return true end
      end
      return false
    end
    local function dangers(s,p)
      local out={}
      for _,t in ipairs(tracks[s.meta.side]) do
        if t.kind=='fighter' or t.kind=='unknown' then
          local d=G.distance(p.point,t.point)
          if d<opt.defendRangeNm*NM and
            (d<15*NM or G.closing(p.point,p.velocity,t.point,t.velocity)>20) then out[#out+1]=t end
        end
      end
      return out
    end
    local function destination(s)
      local route=s.meta.route
      local p=route[math.min(#route,s.meta.recoveryIndex+1)]
      return {x=p.x,y=p.alt,z=p.y}
    end
    local function retreat(s,p,reason)
      s.abortReason=reason
      local ok,why=io.recover(s,p,threats[s.meta.side])
      if ok then
        s.revision=s.revision+1;s.order=nil;s.finished=true;s.abortReason=nil;record(s,'rtb',reason)
      else
        -- Keep an existing safe hold suspended above the original attack route.
        -- A failed recovery search must not accidentally resume that attack.
        if s.order then s.order.deadline=now+60
        else
          local q=G.escape(p.point,{},threats[s.meta.side],io.height,p.speed,destination(s))
          if q then push(s,'recoveryHold',{point=q,reason='waiting for a safe recovery corridor'},60) end
        end
        if now>=(s.nextRecovery or 0) then
          s.nextRecovery=now+60;record(s,'blocked','no safe recovery corridor: '..tostring(why))
        end
      end
    end
    local function blocker(s,p)
      if s.meta.mode~='strike' or s.index>=s.meta.attackIndex then return end
      local target=s.meta.route[s.index+1]
      if not target then return end
      local q={x=target.x,y=target.alt,z=target.y}
      local length=G.distance(p.point,q)
      local reach=p.speed*180+10000
      if length>reach then
        local f=reach/length;q.x=p.point.x+(q.x-p.point.x)*f;q.z=p.point.z+(q.z-p.point.z)*f
      end
      local altitude=math.min(p.point.y,io.altitude(target))
      local clear,t=G.leg(p.point,q,altitude,threats[s.meta.side],10000)
      if not clear then return t,p.point,q,altitude end
    end
    local function workingDEAD(s,t)
      for name,other in pairs(api.states) do
        local p=samples[name]
        if other.meta.side==s.meta.side and (other.meta.deadSupport or other.meta.mode=='dead') and p and p.airborne and p.healthy and
          p.fuel>other.meta.bingo+0.05 and not other.finished and not other.paused and
          (not other.order or other.order.kind~='evade') and
          other.index<other.meta.recoveryIndex and
          (other.meta.package==s.meta.package or G.distance(p.point,t.point)<60*NM) then return true end
      end
      return false
    end
    local function resumeHold(s,p)
      local hold=s.pendingHold
      if not hold then return end
      s.pendingHold=nil
      if now>=hold.deadline then retreat(s,p,'DEAD wait expired');return end
      local clear,t=G.leg(hold.data.from,hold.data.to,hold.data.altitude,threats[s.meta.side],10000)
      if clear then return end
      if not workingDEAD(s,t) then retreat(s,p,'DEAD unavailable; attack cancelled');return end
      local q=G.escape(p.point,{},threats[s.meta.side],io.height,p.speed,destination(s))
      if not q then retreat(s,p,'no safe holding area');return end
      hold.data.point=q;s.cooldown=0
      push(s,'hold',hold.data,hold.deadline-now)
    end
    local function service(s,p)
      if not available(s,p) then release(s,'unavailable, BINGO, recovery or command lost');return end
      if s.abortReason then
        if now>=(s.retryRecovery or 0) then
          s.retryRecovery=now+30;retreat(s,p,s.abortReason)
        end
        return
      end
      if s.pendingHold and now>=s.pendingHold.deadline then
        s.pendingHold=nil;retreat(s,p,'DEAD wait expired');return
      end
      local order=s.order
      if order then
        if now>=order.deadline then
          if order.kind=='hold' then retreat(s,p,'DEAD wait expired')
          else release(s,'temporary order expired');resumeHold(s,p) end
          return
        end
        if order.kind=='intercept' then
          local target
          for _,t in ipairs(tracks[s.meta.side]) do if t.key==order.data.key then target=t;break end end
          local anchor=s.meta.route[s.meta.stationStart]
          local centre={x=anchor.x,z=anchor.y}
          local aim=target and G.copy(target.point)
          if aim then
            local seconds=math.min(60,G.distance(p.point,aim)/math.max(100,p.speed))
            aim.x=aim.x+target.velocity.x*seconds;aim.z=aim.z+target.velocity.z*seconds
          end
          if not target or not p.ammo or nativeRefuel(s) or
            p.fuel<=s.meta.bingo+0.08+(s.meta.burnPerMeter or 0)*G.distance(p.point,centre) or
            G.distance(p.point,centre)>opt.patrolLeashNm*NM or
            G.distance(aim,centre)>opt.patrolLeashNm*NM or
            not G.safe(p.point,aim,math.min(p.point.y,aim.y),threats[s.meta.side],io.height,12000) or
            not G.safe(p.point,target.point,math.min(p.point.y,target.point.y),threats[s.meta.side],io.height,12000) then
            release(s,'contact lost, patrol limit, fuel or unsafe pursuit');return
          end
          local d=G.distance(target.point,order.data.asset)
          if d>order.data.nearest+5000 then order.retreatSince=order.retreatSince or now
          else order.retreatSince=nil;order.data.nearest=math.min(order.data.nearest,d) end
          if order.retreatSince and now-order.retreatSince>=opt.pursuitSeconds then
            release(s,'enemy withdrawing; return to patrol')
          end
        elseif order.kind=='evade' then
          if #dangers(s,p)==0 then
            order.clearSince=order.clearSince or now
            if now-order.clearSince>=30 then release(s,'air threat cleared');resumeHold(s,p) end
          else order.clearSince=nil end
          if not G.safe(p.point,order.data.point,p.point.y,threats[s.meta.side],io.height,15000,true) then
            release(s,'evasion corridor changed')
          end
        elseif order.kind=='hold' then
          local danger=dangers(s,p)
          if #danger>0 then
            local q=G.escape(p.point,danger,threats[s.meta.side],io.height,p.speed,destination(s))
            if q then
              s.order=nil
              if push(s,'evade',{point=q,reason='enemy fighters approaching; leave holding area'},600) then
                s.pendingHold=order
              else s.order=order;s.revision=order.revision end
              return
            end
          end
          local clear,threat=G.leg(order.data.from,order.data.to,order.data.altitude,threats[s.meta.side],10000)
          if clear then release(s,'attack corridor clear')
          elseif not workingDEAD(s,threat) then retreat(s,p,'DEAD unavailable; attack cancelled') end
        end
        return
      end
      if now<s.cooldown or s.meta.mode=='observe' or s.meta.mode=='cap' then return end
      local danger=dangers(s,p)
      if #danger>0 then
        local q=G.escape(p.point,danger,threats[s.meta.side],io.height,p.speed,destination(s))
        if q then push(s,'evade',{point=q,reason='enemy fighters approaching; reposition safely'},600) end
        return
      end
      if s.pendingHold then resumeHold(s,p);return end
      local threat,from,to,altitude=blocker(s,p)
      if threat then
        if workingDEAD(s,threat) then
          local q=G.escape(p.point,{},threats[s.meta.side],io.height,p.speed,destination(s))
          if q then push(s,'hold',{point=q,from=G.copy(from),to=G.copy(to),altitude=altitude,
            reason='known SAM blocks ingress; waiting for DEAD'},opt.holdSeconds)
          else retreat(s,p,'no safe holding area') end
        else retreat(s,p,'known SAM blocks ingress; no active DEAD') end
      end
    end
    local function targetPriority(t,side)
      local best,asset
      for name,s in pairs(api.states) do
        local p=samples[name]
        if s.meta.side==side and p and p.airborne and not s.finished then
          local vulnerable=s.meta.mode~='cap'
          local distance=G.distance(p.point,t.point)
          local closing=G.closing(p.point,p.velocity,t.point,t.velocity)
          local attacker=t.kind=='bomber' or t.kind=='attack' or t.kind=='transport'
          if (closing>20 or distance<15*NM) and
            ((vulnerable and distance<opt.defendRangeNm*NM) or (attacker and distance<opt.interceptRangeNm*NM)) then
            local score=(vulnerable and 1000000 or 0)+(attacker and 200000 or 0)-distance
            if not best or score>best then best,asset=score,G.copy(p.point) end
          end
        end
      end
      return best,asset
    end
    local function assign(side)
      local reserved,targets={},{}
      for _,s in pairs(api.states) do
        if s.order and s.order.kind=='intercept' then reserved[s.order.data.groupId]=true end
      end
      for _,t in ipairs(tracks[side]) do
        local priority,asset=targetPriority(t,side)
        if priority and not reserved[t.groupId] then targets[#targets+1]={track=t,priority=priority,asset=asset} end
      end
      table.sort(targets,function(a,b)
        if a.priority==b.priority then return a.track.key<b.track.key end
        return a.priority>b.priority
      end)
      for _,candidate in ipairs(targets) do
        local t=candidate.track
        if not reserved[t.groupId] then
          local best,bestDistance
          for name,s in pairs(api.states) do
            local p=samples[name]
            if s.meta.side==side and s.meta.mode=='cap' and not s.order and now>=s.cooldown and
              s.index>=s.meta.stationStart and available(s,p) and p.ammo then
              local anchor=s.meta.route[s.meta.stationStart]
              local centre={x=anchor.x,z=anchor.y}
              local d=G.distance(p.point,t.point)
              local seconds=math.min(60,d/math.max(100,p.speed))
              local aim={x=t.point.x+t.velocity.x*seconds,y=t.point.y,z=t.point.z+t.velocity.z*seconds}
              local maxRange=s.meta.burnPerMeter and opt.interceptRangeNm*NM or 30*NM
              local reserve=s.meta.bingo+0.08+(s.meta.burnPerMeter or 0)*2*d
              if d<maxRange and p.fuel>reserve and G.distance(t.point,centre)<opt.patrolLeashNm*NM and
                G.distance(aim,centre)<opt.patrolLeashNm*NM and
                now+d/math.max(100,p.speed)+120<s.meta.endTime and
                G.safe(p.point,t.point,math.min(p.point.y,t.point.y),threats[side],io.height,12000) and
                G.safe(p.point,aim,math.min(p.point.y,aim.y),threats[side],io.height,12000) and
                (not bestDistance or d<bestDistance or (d==bestDistance and name<best.meta.group)) then
                best,bestDistance=s,d
              end
            end
          end
          if best and push(best,'intercept',{key=t.key,groupId=t.groupId,asset=candidate.asset,
            nearest=G.distance(t.point,candidate.asset),reason='intercept detected '..t.kind..' threat'},900) then
            reserved[t.groupId]=true
          end
        end
      end
    end
    function api:tick()
      if not self.active then return end
      now=io.time()
      for side=1,2 do
        authority[side]=not self.paused[side] and io.authority(side)
        tracks[side]=authority[side] and io.contacts(side) or {}
        threats[side]=io.threats(side)
      end
      for name,s in pairs(self.states) do samples[name]=io.sample(s.meta) end
      for name,s in pairs(self.states) do service(s,samples[name]) end
      for side=1,2 do if authority[side] then assign(side) end end
    end
    return api
  end
end
