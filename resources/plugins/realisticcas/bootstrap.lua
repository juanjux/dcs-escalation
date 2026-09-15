-- Explicit entry point for exported campaign metadata. Loading is inert.
assert(RealisticCAS and RealisticCAS.startDetection,"load Realistic CAS detectors first")
do
  function RealisticCAS.startMission(config)
    local c=config or {}
    if c.enabled~=true then return nil,"disabled" end
    if RealisticCAS.mission or RealisticCAS._running then return nil,"already running" end
    local r=c.registry
    assert(type(r)=="table" and r.schemaVersion==1,"unsupported registry schema")
    for _,field in ipairs({'groups','targets','observers','knownAirDefenseGroups','warnings'}) do
      assert(type(r[field])=='table','missing registry '..field)
    end
    local known,managed,unitNames={},{},{}
    for _,v in ipairs(r.knownAirDefenseGroups) do
      assert(type(v.name)=='string','invalid SAM objective group')
      known[v.name]=true
    end
    for _,v in ipairs(r.groups) do
      assert(type(v.name)=='string' and v.name~='' and not managed[v.name],'invalid target group')
      assert(not known[v.name],'fixed SAM objective must not be concealed: '..v.name)
      assert(v.originalInvisible==false,'visibility ownership required')
      managed[v.name]=true
    end
    for _,v in ipairs(r.targets) do
      assert(type(v.name)=='string' and v.name~='' and not unitNames[v.name],'invalid target unit')
      assert(managed[v.groupName],'target outside managed group list')
      unitNames[v.name]=true
    end
    -- Build the environment before hiding anything. No guessed time or biome.
    local environment=RealisticCAS.newEnvironment(c.environment)
    assert(RealisticCAS.Sensors.finite(c.acquisitionSeconds) and c.acquisitionSeconds>0
      and c.acquisitionSeconds<=600,'campaign acquisition time must be explicit and positive')
    local function log(kind,msg)
      env.info('REALISTIC_CAS_MISSION|'..kind..'|t='..timer.getTime()..'|'..tostring(msg))
    end
    local api={active=false}
    local handler={}
    function api:stop()
      if self.detectors then self.detectors:stop() end
      if self.fog and not self.fog:stop() then
        log('ERROR','visibility restoration incomplete; retry RealisticCAS.mission:stop()')
        return false
      end
      world.removeEventHandler(handler)
      self.active=false
      if RealisticCAS.mission==self then RealisticCAS.mission=nil end
      return true
    end
    function handler:onEvent(event)
      if event and world.event.S_EVENT_MISSION_END and event.id==world.event.S_EVENT_MISSION_END then
        local ok,result=pcall(function()return api:stop()end)
        if not ok or not result then log('ERROR','mission-end cleanup: '..tostring(result)) end
      end
    end
    RealisticCAS.mission=api -- Retain a recovery handle even if startup rollback fails.
    local ok,err=pcall(function()
      api.fog=assert(RealisticCAS.start({enabled=true,targets=r.groups,ttl=c.ttl,
        debug=c.debug,expiryBudget=c.expiryBudget}))
      api.detectors=RealisticCAS.startDetection(api.fog,{targets=r.targets,observers=r.observers,
        environment=environment,acquisitionSeconds=c.acquisitionSeconds,
        acquisitionMaxGap=c.acquisitionMaxGap,interval=c.interval,revisit=c.revisit,
        targetBudget=c.targetBudget,workBudget=c.workBudget,cellSize=c.cellSize,
        observerBudget=c.observerBudget,losBudget=c.losBudget,observerQuantum=c.observerQuantum,
        debug=c.debug,traceDecisions=c.traceDecisions})
      world.addEventHandler(handler)
      api.active=true
      for _,warning in ipairs(r.warnings)do log('WARNING',warning)end
      log('START','managedGroups='..#r.groups..'|targetUnits='..#r.targets..
        '|observers='..#r.observers..'|knownSAMGroups='..#r.knownAirDefenseGroups..
        '|acquisitionSeconds='..c.acquisitionSeconds)
    end)
    if not ok then
      log('ERROR','startup: '..tostring(err))
      local cleaned,result=pcall(function()return api:stop()end)
      if not cleaned or not result then log('ERROR','rollback: '..tostring(result))end
      return nil,tostring(err)
    end
    return api
  end
end
