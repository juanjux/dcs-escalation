-- Same live geometry throughout. Only exported light and IR capability change.
do
  local cfg=RCAS_NIGHT_TEST
  local started=timer.getTime()
  local fog,detectors,phaseStarted,phaseIndex
  local failures,inconclusive,checks=0,0,0
  local done=false
  local phases={
    {name='DAY_IR_OFF',hour=12,ir=false,expect='visual'},
    {name='NIGHT_IR_OFF',hour=23,ir=false,expect=false},
    {name='NIGHT_IR_ON',hour=23,ir=true,expect='ir'},
    {name='NIGHT_IR_OFF_AGAIN',hour=23,ir=false,expect=false},
    {name='DAY_RECOVERY',hour=12,ir=false,expect='visual'},
  }
  local function log(kind,detail)
    env.info('RCAS_NIGHT_TEST|'..kind..'|elapsed='..string.format('%.1f',timer.getTime()-started)..'|'..detail)
  end
  local function check(ok,detail)
    checks=checks+1
    if not ok then failures=failures+1 end
    log(ok and 'PASS' or 'FAIL',detail)
  end
  local function finish()
    if detectors then detectors:stop() end
    if fog then check(fog:stop(),'visibility restored') end
    done=true
    log('RESULT','failures='..failures..'|inconclusive='..inconclusive..'|checks='..checks)
    trigger.action.outText('RCAS NIGHT FIN: '..failures..' fallos, '..inconclusive..' inconclusos. Guarda dcs.log.',600)
  end
  local function beginPhase(index,now)
    if detectors then
      check(detectors:getDiagnostics().errors==0,'no callback errors phase '..phaseIndex)
      detectors:stop()
      -- Keep the same fog owner: negative phases must expire a previous contact.
      fog.detectors=nil
    end
    phaseIndex,phaseStarted=index,now
    local phase=phases[index]
    local environment=RealisticCAS.newEnvironment({defaultCover='desert',startTime=phase.hour*3600,
      sunrise=6*3600,sunset=18*3600,weather=1,visibility=30000})
    detectors=RealisticCAS.startDetection(fog,{targets={cfg.target},
      observers={{name=cfg.observer,typeName='M-1 Abrams',category='ground',equipment={ir=phase.ir}}},
      environment=environment,debug=true,traceDecisions=true})
    log('PHASE',phase.name..'|modeledHour='..phase.hour..'|ir='..tostring(phase.ir)..'|expect='..tostring(phase.expect))
  end
  timer.scheduleFunction(function(_,now)
    if done then return nil end
    local ok,err=pcall(function()
      local observer=assert(Unit.getByName(cfg.observer),'observer absent')
      local target=assert(Unit.getByName(cfg.target.name),'target absent')
      assert(observer:isExist() and target:isExist(),'unit removed')
      local a,b=observer:getPoint(),target:getPoint()
      a={x=a.x,y=a.y+2,z=a.z};b={x=b.x,y=b.y+1,z=b.z}
      local los=land.isVisible(a,b)
      local distance=math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2)
      log('GEOMETRY','LOS='..tostring(los)..'|distance='..distance..
        '|observer='..a.x..','..a.y..','..a.z..'|target='..b.x..','..b.y..','..b.z)
      if not los or distance<1800 or distance>2200 then
        inconclusive=inconclusive+1;log('INCONCLUSIVE','clear fixed 2km geometry unavailable');finish();return
      end
      if not fog then
        fog=assert(RealisticCAS.start({enabled=true,ttl=15,debug=true,
          targets={{name=cfg.target.groupName,originalInvisible=false}}}))
        beginPhase(1,now)
      end
      local c=fog.service:getContact(target:getGroup():getID(),2)
      log('CONTACT',phases[phaseIndex].name..'|revealed='..tostring(c and c.revealed)..'|reason='..tostring(c and c.reason))
      if now-phaseStarted>=45 then
        local expected=phases[phaseIndex].expect
        local revealed=c and c.revealed or false
        if expected then
          check(revealed and c.reason==expected..':'..cfg.observer,phases[phaseIndex].name..' exact channel '..expected)
        else
          check(not revealed,phases[phaseIndex].name..' contact expired and hidden')
        end
        if phaseIndex==#phases then
          check(detectors:getDiagnostics().errors==0,'no callback errors final phase')
          finish();return
        end
        beginPhase(phaseIndex+1,now)
      end
      trigger.action.outText('RCAS NIGHT / '..math.floor(now-started)..'s / '..phases[phaseIndex].name..
        '. Solo log; FIN ~230s. Luz del modelo, sin cambiar hora DCS.',5,true)
    end)
    if not ok then
      failures=failures+1;log('ERROR',tostring(err))
      local restored,restoreError=pcall(finish)
      if not restored then
        done=true;log('ERROR','cleanup: '..tostring(restoreError))
        trigger.action.outText('RCAS NIGHT ERROR: guarda dcs.log. Sal de la mision.',600)
      end
    end
    if not done then return now+5 end
  end,nil,started+5)
  log('START','Night DCS scene; day phases override exported model light only. IR metadata toggled; no native sensor switch claim.')
end
