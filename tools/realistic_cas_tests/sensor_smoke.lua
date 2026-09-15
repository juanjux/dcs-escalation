-- Actual perception pipeline: no manual fog:observe calls in this test.
do
  local cfg=RCAS_SENSOR_TEST
  local start=timer.getTime()
  local fog=assert(RealisticCAS.start({enabled=true,ttl=30,debug=true,targets=cfg.groups}))
  local environment=RealisticCAS.newEnvironment({defaultCover='desert',startTime=12*3600,
    sunrise=6*3600,sunset=18*3600,weather=1,visibility=30000,zones=cfg.zones})
  -- Midday, clear sky. Sunrise/sunset placeholders cannot affect this short run.
  local detectors=RealisticCAS.startDetection(fog,{targets=cfg.targets,observers=cfg.observers,
    environment=environment,debug=true})
  local seen={};local fail=0;local finished=false;local stopped=false
  local function log(kind,detail)
    env.info('RCAS_SENSOR_TEST|'..kind..'|elapsed='..string.format('%.1f',timer.getTime()-start)..'|'..detail)
  end
  local function check(ok,message)
    if not ok then fail=fail+1 end
    log(ok and 'PASS' or 'FAIL',message)
  end
  timer.scheduleFunction(function(_,now)
    if finished then return nil end
    local ok,err=pcall(function()
      for _,v in ipairs(cfg.targets) do
        local u=Unit.getByName(v.name)
        local g=u:getGroup();local enemy=g:getCoalition()==1 and 2 or 1
        local c=fog.service:getContact(g:getID(),enemy)
        if c and c.revealed then
          if not seen[v.name] then log('FIRST_CONTACT',v.name..'|reason='..c.reason) end
          seen[v.name]=true
        end
        if now-start<300 and v.expect==false and c and c.revealed then
          check(false,'unexpected reveal '..v.name)
        end
        log('CONTACT',v.name..'|revealed='..tostring(c and c.revealed)..'|reason='..tostring(c and c.reason))
      end
      for _,v in ipairs(cfg.observers) do
        local u=Unit.getByName(v.name)
        if u and u:isExist() then
          local radarOK,radar=pcall(function()return u:getRadar()end)
          local p=u:getPoint()
          log('OBSERVER',v.name..'|radar='..tostring(radarOK and radar)..'|altMSL='..p.y)
        end
      end
      local elapsed=now-start
      if elapsed>=300 and not stopped then
        for _,v in ipairs(cfg.targets) do
          if v.expect==true then check(seen[v.name]==true,'detected '..v.name)
          elseif v.expect==false then check(not seen[v.name],'kept hidden '..v.name) end
        end
        check(detectors:getDiagnostics().errors==0,'no detector callback errors')
        detectors:stop();stopped=true;log('PHASE','sensors stopped, waiting for TTL')
      end
      if elapsed>=350 and elapsed<355 then
        for _,v in ipairs(cfg.targets) do
          local g=Group.getByName(v.groupName);local enemy=g:getCoalition()==1 and 2 or 1
          check(not fog.service:isRevealed(g:getID(),enemy),'expired '..v.name)
        end
      end
      if elapsed>=380 then
        check(fog:stop(),'restored visibility')
        log('RESULT','failures='..fail..'|radar channel must be checked in FIRST_CONTACT/OBSERVER')
        trigger.action.outText('RCAS SENSOR FIN: '..fail..' fallos. Guarda dcs.log.',600)
        finished=true;return
      end
      trigger.action.outText('RCAS SENSOR / '..math.floor(elapsed)..'s. Solo log. FIN a 380s.',5,true)
    end)
    if not ok then fail=fail+1;log('ERROR',tostring(err)) end
    if not finished then return now+5 end
  end,nil,start+5)
  log('START','live geometry + LOS + actual core; synthetic desert/city cover, not automatic terrain classification')
end
