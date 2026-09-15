-- Controlled cloud attenuation through the live DCS bridge; not native pod calibration.
do
  local cfg=RCAS_CLOUD_TEST
  local start=timer.getTime()
  local fog,detectors,index,phaseStart
  local failures,inconclusive,checks=0,0,0
  local opportunities,hits,unexpected=0,0,0
  local done=false
  local phases={
    {name='CLEAR_MODEL',vt=1,it=1,expect='eo'},
    {name='IR_THROUGH_LAYER',vt=0,it=0.85,expect='ir'},
    {name='OPAQUE_LAYER',vt=0,it=0,expect=false},
    {name='CLEAR_RECOVERY',vt=1,it=1,expect='eo'},
  }
  local function log(kind,msg)
    env.info('RCAS_CLOUD_TEST|'..kind..'|elapsed='..string.format('%.1f',timer.getTime()-start)..'|'..msg)
  end
  local function check(ok,msg)
    checks=checks+1;if not ok then failures=failures+1 end
    log(ok and 'PASS' or 'FAIL',msg)
  end
  local function finish()
    if detectors then detectors:stop() end
    if fog then check(fog:stop(),'visibility restored') end
    done=true
    log('RESULT','failures='..failures..'|inconclusive='..inconclusive..'|checks='..checks)
    trigger.action.outText('RCAS CLOUD FIN: '..failures..' fallos, '..inconclusive..' inconclusos. Guarda dcs.log.',600)
  end
  local function beginPhase(i,now)
    if detectors then
      check(detectors:getDiagnostics().errors==0,'no callback errors phase '..index)
      detectors:stop();fog.detectors=nil
    end
    index,phaseStart=i,now;opportunities,hits,unexpected=0,0,0
    local p=phases[i]
    local environment=RealisticCAS.newEnvironment({defaultCover='desert',startTime=12*3600,
      sunrise=6*3600,sunset=18*3600,weather=1,visibility=30000,
      clouds={base=1500,top=3500,visualTransmission=p.vt,irTransmission=p.it}})
    detectors=RealisticCAS.startDetection(fog,{targets={cfg.target},
      observers={{name=cfg.observer,typeName='A-10C_2',category='air',role='CAS',equipment={targetingPod=true}}},
      environment=environment,debug=true,traceDecisions=true})
    log('PHASE',p.name..'|visualTransmission='..p.vt..'|irTransmission='..p.it)
  end
  timer.scheduleFunction(function(_,now)
    if done then return nil end
    local ok,err=pcall(function()
      local u=assert(Unit.getByName(cfg.observer),'observer missing')
      local t=assert(Unit.getByName(cfg.target.name),'target missing')
      assert(u:isExist() and t:isExist(),'unit removed')
      if not fog then
        fog=assert(RealisticCAS.start({enabled=true,ttl=15,debug=true,
          targets={{name=cfg.target.groupName,originalInvisible=false}}}))
        beginPhase(1,now)
      end
      local a,b=u:getPosition(),t:getPoint()
      local dx,dy,dz=b.x-a.p.x,b.y+1-a.p.y,b.z-a.p.z
      local distance=math.sqrt(dx*dx+dy*dy+dz*dz)
      local agl=a.p.y-land.getHeight({x=a.p.x,y=a.p.z})
      local angle=math.abs(math.atan2(-dx*a.x.z+dz*a.x.x,dx*a.x.x+dz*a.x.z))
      local los=land.isVisible(a.p,{x=b.x,y=b.y+1,z=b.z})
      -- Independent, conservative positive-control window; does not call assess().
      -- Both endpoints must straddle the modeled slab; range fits 0.85 IR too.
      local usable=u:inAir() and agl<=6500 and a.p.y>3500 and b.y+1<1500
        and distance>=1000 and distance<=9500 and angle<math.rad(110) and los
      local c=fog.service:getContact(t:getGroup():getID(),2)
      local phase=phases[index]
      local elapsed=now-phaseStart
      if elapsed>25 then
        if usable then opportunities=opportunities+1 end
        if c and c.revealed and c.observedAt>phaseStart then
          if phase.expect and c.reason==phase.expect..':'..cfg.observer then hits=hits+1
          else unexpected=unexpected+1 end
        end
      end
      log('SAMPLE',phase.name..'|distance='..distance..'|altMSL='..a.p.y..'|agl='..agl..
        '|azimuthDeg='..math.deg(angle)..'|LOS='..tostring(los)..'|usable='..tostring(usable)..
        '|revealed='..tostring(c and c.revealed)..'|reason='..tostring(c and c.reason))
      if elapsed>=120 then
        check(unexpected==0,phase.name..' no wrong channel or opaque-layer reveal')
        if opportunities<3 then
          inconclusive=inconclusive+1;log('INCONCLUSIVE',phase.name..' insufficient clear geometry windows: '..opportunities)
        elseif phase.expect then
          check(hits>0,phase.name..' fresh channel '..phase.expect..'|hits='..hits..'|opportunities='..opportunities)
        else
          check(not (c and c.revealed),phase.name..' expired and hidden|opportunities='..opportunities)
        end
        if index==#phases then
          check(detectors:getDiagnostics().errors==0,'no callback errors final phase');finish();return
        end
        beginPhase(index+1,now)
      end
      trigger.action.outText('RCAS CLOUD / '..math.floor(now-start)..'s / '..phases[index].name..
        '. Solo log. FIN ~490s.',5,true)
    end)
    if not ok then
      failures=failures+1;log('ERROR',tostring(err))
      local restored,detail=pcall(finish)
      if not restored then
        done=true;log('ERROR','cleanup: '..tostring(detail))
        trigger.action.outText('RCAS CLOUD ERROR: guarda dcs.log y sal de la mision.',600)
      end
    end
    if not done then return now+5 end
  end,nil,start+5)
  log('START','Native flying pose/LOS; cloud attenuation is controlled model input, unchanged native weather.')
end
