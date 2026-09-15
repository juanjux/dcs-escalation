-- DCS bridge for bounded perception. Explicit metadata only, no campaign scanning.
assert(RealisticCAS and RealisticCAS.newDetection,"load detection.lua first")
do
  local S=RealisticCAS.Sensors
  function RealisticCAS.startDetection(fog,config)
    assert(fog and fog.active and not fog.stopping,"active visibility owner required")
    assert(not fog.detectors,"detectors already attached")
    local c=config or {}
    assert(type(c.observers)=="table" and type(c.targets)=="table","explicit observer/target lists required")
    assert(type(c.environment)=="function","environment provider required")
    local observers,targets={},{}
    local interval=c.interval or 1
    assert(S.finite(interval) and interval>=0.1 and interval<=60,"invalid interval")
    local function log(kind,detail)
      if c.debug or kind=="ERROR" or kind=="WARNING" then
        env.info("REALISTIC_CAS_SENSOR|"..kind.."|t="..timer.getTime().."|"..tostring(detail))
      end
    end
    for _,v in ipairs(c.observers) do
      assert(type(v.name)=="string" and v.name~="" and not observers[v.name],"invalid/duplicate observer")
      assert(type(v.typeName)=="string","observer aircraft/vehicle type required")
      local p=S.profile(v.typeName,v.category,v.equipment)
      observers[v.name]={typeName=v.typeName,category=v.category,role=v.role,profile=p,
        allowPlayer=v.allowPlayer==true}
    end
    for _,v in ipairs(c.targets) do
      assert(type(v.name)=="string" and v.name~="" and type(v.groupName)=="string" and
        v.groupName~="" and not targets[v.name],"invalid/duplicate target")
      targets[v.name]=v.groupName
    end
    local function live(name)
      local u=Unit.getByName(name)
      if not u or not u:isExist() or u:getLife()<=0 then return nil end
      local side=u:getCoalition()
      if side~=1 and side~=2 then return nil end
      return u
    end
    local engine=RealisticCAS.newDetection({clock=timer.getTime,cellSize=c.cellSize,
      targetBudget=c.targetBudget,workBudget=c.workBudget,revisit=c.revisit,log=log,
      observerBudget=c.observerBudget,losBudget=c.losBudget,observerQuantum=c.observerQuantum,
      traceDecisions=c.traceDecisions==true,
      acquisitionSeconds=c.acquisitionSeconds,
      acquisitionMaxGap=c.acquisitionMaxGap,
      environment=c.environment,
      readTarget=function(name)
        local u=live(name);if not u then return nil end
        local g=u:getGroup()
        if not g or g:getName()~=targets[name] or g:getCategory()~=Group.Category.GROUND then return nil end
        local pos=u:getPoint()
        return {name=name,groupName=targets[name],side=u:getCoalition(),position=pos,
          point={x=pos.x,y=pos.y+1,z=pos.z},velocity=u:getVelocity()}
      end,
      readObserver=function(name)
        local u=live(name);if not u then return nil end
        local meta=observers[name]
        if u:getTypeName()~=meta.typeName then return nil end
        if not meta.allowPlayer and u:getPlayerName() then return nil end
        local g=u:getGroup();if not g then return nil end
        local ground=g:getCategory()==Group.Category.GROUND
        if ground~=(meta.category=="ground") then return nil end
        if not ground and not u:inAir() then return nil end
        local pose=u:getPosition();local p=pose.p
        local agl=ground and 2 or math.max(0,p.y-land.getHeight({x=p.x,y=p.z}))
        local radar=false
        if not ground and (meta.profile.rbmRange>0 or meta.profile.gmtiRange>0) then
          local ok,on=pcall(function() return u:getRadar() end)
          radar=ok and on==true
        end
        return {name=name,side=u:getCoalition(),point={x=p.x,y=p.y+(ground and 2 or 0),z=p.z},
          forward=pose.x,agl=agl,role=meta.role,radarOn=radar}
      end,
      lineOfSight=function(a,b) return land.isVisible(a,b) end,
      isRevealed=function(target,observer)
        local g=Group.getByName(target.groupName)
        return g and fog.service:isRevealed(g:getID(),observer.side)==true
      end,
      reveal=function(target,observer,result)
        if not fog.active or fog.stopping then return false end
        return fog:observe(target.groupName,observer.side,target.position,result.mode..":"..observer.name)
      end})
    for name,meta in pairs(observers) do engine:addObserver(name,meta.profile) end
    for name in pairs(targets) do engine:addTarget(name) end
    timer.scheduleFunction(function(_,now)
      if not fog.active or fog.stopping or not engine:getDiagnostics().enabled then
        engine:stop();return nil
      end
      local ok,err=pcall(function()engine:tick()end)
      if not ok then log("ERROR",err) end
      if c.debug then
        local d=engine:getDiagnostics()
        log("STATS","candidates="..d.candidates.."|los="..d.los.."|reveals="..d.reveals..
          "|work="..d.work.."|errors="..d.errors.."|sweeps="..d.sweeps..
          "|blockedLOS="..d.blockedLOS.."|rejectedEnvelope="..d.rejectedEnvelope..
          "|maxSweepGap="..d.maxSweepGap.."|overdue="..d.overdueVisits..
          "|losBudgetHits="..d.losBudgetHits.."|workBudgetHits="..d.workBudgetHits..
          "|culledObservers="..d.culledObservers.."|cullChecks="..d.cullChecks)
        log("SEARCH_STATS","pending="..d.pendingAcquisitions.."|started="..d.acquisitionStarts..
          "|completed="..d.acquisitionCompletions.."|resets="..d.acquisitionResets)
      end
      return now+interval
    end,nil,timer.getTime()+interval)
    fog.detectors=engine
    return engine
  end
end
