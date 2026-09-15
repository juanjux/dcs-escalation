-- Live radar-on/velocity bridge test, NOT access to a native RBM/GMTI mode.
do
  local cfg=RCAS_RADAR_TEST
  local start=timer.getTime()
  local fog,detectors,index,phaseStart
  local failures,inconclusive,checks=0,0,0
  local counts={};local done=false
  local phases={
    {name='CAS',role='CAS',gmti=true},
    {name='STRIKE',role='STRIKE',gmti=true,blocked=true},
    {name='CAS_NO_GMTI',role='CAS',gmti=false},
    {name='BAI',role='BAI',gmti=true},
    {name='ARMED_RECON',role='Armed Recon',gmti=true},
  }
  local function log(kind,msg)
    env.info('RCAS_RADAR_TEST|'..kind..'|elapsed='..string.format('%.1f',timer.getTime()-start)..'|'..msg)
  end
  local function check(ok,msg)
    checks=checks+1;if not ok then failures=failures+1 end
    log(ok and 'PASS' or 'FAIL',msg)
  end
  local function expected(v,p)
    if p.blocked or v.kind=='far' then return false end
    if v.kind=='near' then return 'rbm' end
    return p.gmti and 'gmti' or false
  end
  local function finish()
    if detectors then detectors:stop() end
    if fog then check(fog:stop(),'visibility restored') end
    done=true
    log('RESULT','failures='..failures..'|inconclusive='..inconclusive..'|checks='..checks)
    trigger.action.outText('RCAS RADAR FIN: '..failures..' fallos, '..inconclusive..' inconclusos. Guarda dcs.log.',600)
  end
  local function beginPhase(i,now)
    if detectors then
      check(detectors:getDiagnostics().errors==0,'no callback errors phase '..index)
      detectors:stop();fog.detectors=nil
    end
    index,phaseStart=i,now
    counts={}
    for _,v in ipairs(cfg.targets) do counts[v.name]={opportunities=0,hits=0,bad=0} end
    local p=phases[i]
    local environment=RealisticCAS.newEnvironment({defaultCover='desert',startTime=23*3600,
      sunrise=6*3600,sunset=18*3600,weather=1,visibility=30000})
    detectors=RealisticCAS.startDetection(fog,{targets=cfg.targets,
      observers={{name=cfg.observer,typeName='FA-18C_hornet',category='air',role=p.role,
        equipment={targetingPod=false,ir=false,eo=false,rbm=true,gmti=p.gmti}}},
      environment=environment,debug=true,traceDecisions=true})
    log('PHASE',p.name..'|role='..p.role..'|gmtiCapability='..tostring(p.gmti))
  end
  timer.scheduleFunction(function(_,now)
    if done then return nil end
    local ok,err=pcall(function()
      local u=assert(Unit.getByName(cfg.observer),'observer missing')
      assert(u:isExist(),'observer removed')
      if not fog then
        fog=assert(RealisticCAS.start({enabled=true,ttl=15,debug=true,targets=cfg.groups}))
        beginPhase(1,now)
      end
      local a=u:getPosition()
      local radarOK,on=pcall(function() return u:getRadar() end)
      local elapsed=now-phaseStart
      for _,v in ipairs(cfg.targets) do
        local t=assert(Unit.getByName(v.name),'target missing '..v.name)
        assert(t:isExist(),'target removed')
        local b,velocity=t:getPoint(),t:getVelocity()
        local dx,dy,dz=b.x-a.p.x,b.y+1-a.p.y,b.z-a.p.z
        local distance=math.sqrt(dx*dx+dy*dy+dz*dz)
        local angle=math.abs(math.atan2(-dx*a.x.z+dz*a.x.x,dx*a.x.x+dz*a.x.z))
        local depression=math.atan2(-dy,math.sqrt(dx*dx+dz*dz))
        local speed=math.sqrt(velocity.x^2+velocity.z^2)
        local radial=math.abs((dx*velocity.x+dz*velocity.z)/math.max(distance,0.001))
        local los=land.isVisible(a.p,{x=b.x,y=b.y+1,z=b.z})
        local base=u:inAir() and radarOK and on==true and angle<math.rad(50)
          and depression>0 and depression<math.rad(70) and los
        -- Independent conservative geometric windows, no call to model assess().
        local properRange=v.kind=='near' and distance>1000 and distance<11000
          or v.kind~='near' and distance>13000 and distance<23500
        local motion=v.kind=='moving' and speed>2.5 and radial>1.5
          or v.kind~='moving' and speed<0.1
        local usable=base and properRange and motion
        local c=fog.service:getContact(t:getGroup():getID(),2)
        local stats=counts[v.name]
        local want=expected(v,phases[index])
        if elapsed>25 then
          if usable then stats.opportunities=stats.opportunities+1 end
          if c and c.revealed and c.observedAt>phaseStart then
            if want and c.reason==want..':'..cfg.observer then stats.hits=stats.hits+1
            else stats.bad=stats.bad+1 end
          end
        end
        log('SAMPLE',phases[index].name..'|'..v.name..'|radar='..tostring(radarOK and on)..
          '|distance='..distance..'|altMSL='..a.p.y..'|azimuthDeg='..math.deg(angle)..
          '|speed='..speed..'|radial='..radial..'|LOS='..tostring(los)..'|usable='..tostring(usable)..
          '|revealed='..tostring(c and c.revealed)..'|reason='..tostring(c and c.reason))
        if elapsed>=120 then
          if stats.opportunities<3 then
            inconclusive=inconclusive+1
            log('INCONCLUSIVE',phases[index].name..'|'..v.name..' opportunities='..stats.opportunities..
              '|hits='..stats.hits..'|unexpected='..stats.bad..'|check radar, cone, range, LOS and movement')
          else
            check(stats.bad==0,phases[index].name..'|'..v.name..' no wrong channel')
            if want then
              check(stats.hits>0,phases[index].name..'|'..v.name..' fresh '..want..
                '|hits='..stats.hits..'|opportunities='..stats.opportunities)
            else
              check(not (c and c.revealed),phases[index].name..'|'..v.name..' hidden/expired')
            end
          end
        end
      end
      if elapsed>=120 then
        if index==#phases then
          check(detectors:getDiagnostics().errors==0,'no callback errors final phase');finish();return
        end
        beginPhase(index+1,now)
      end
      trigger.action.outText('RCAS RADAR / '..math.floor(now-start)..'s / '..phases[index].name..
        '. Solo log. FIN ~615s.',5,true)
    end)
    if not ok then
      failures=failures+1;log('ERROR',tostring(err))
      local restored,detail=pcall(finish)
      if not restored then
        done=true;log('ERROR','cleanup: '..tostring(detail))
        trigger.action.outText('RCAS RADAR ERROR: guarda dcs.log y sal de la mision.',600)
      end
    end
    if not done then return now+5 end
  end,nil,start+5)
  log('START','Native pose, velocity and radar-on; modeled RBM/GMTI and roles, not native radar mode control.')
end
