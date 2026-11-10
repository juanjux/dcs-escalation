-- Controlled observations isolate native sharing, expiry and target memory.
do
  local c=__CONFIG__
  local started=timer.getTime()
  local fog,intel
  local shots={}
  local function log(kind,text)
    env.info('GROUND_INTEL_PROBE|'..kind..'|t='..string.format('%.1f',timer.getTime()-started)..'|'..text)
  end
  local function later(seconds,fn)
    timer.scheduleFunction(function()
      local ok,err=pcall(fn)
      if not ok then log('ERROR',tostring(err))end
    end,nil,started+seconds)
  end
  fog=assert(RealisticCAS.start({enabled=true,targets=c.groups,ttl=40,debug=true,
    onObservation=function(name,side,contact)intel:observe(name,side,contact)end,
    onTick=function()intel:tick()end}))
  intel=RealisticCAS.newGroundIntel(fog,c.observers,c.targets,{log=log})
  local function observe()
    for _,row in ipairs(c.cases)do
      local u=assert(Unit.getByName(row.name))
      assert(fog:observe(row.groupName,row.side,u:getPoint(),'visual:probe',u:getTypeName(),row.name))
    end
    log('PHASE','genuine observations injected; TTL 40 seconds')
  end
  later(20,observe)
  later(40,function()
    for _,row in ipairs(c.cases)do
      local g=assert(Group.getByName(row.receiverGroup))
      g:getController():setOption(AI.Option.Ground.id.ROE,AI.Option.Ground.val.ROE.OPEN_FIRE)
    end
    log('PHASE','receivers OPEN_FIRE; targets still visible')
  end)
  later(80,function()
    for _,row in ipairs(c.cases)do
      local g=assert(Group.getByName(row.groupName));local p=g:getUnits()[1]:getPoint()
      g:getController():setTask({id='Mission',params={route={points={
        {x=p.x,y=p.z,speed=5,speed_locked=true,type='Turning Point',action='Off Road',
          task={id='ComboTask',params={tasks={}}}},
        {x=p.x,y=p.z+250,speed=5,speed_locked=true,type='Turning Point',action='Off Road',
          task={id='ComboTask',params={tasks={}}}}
      }}}})
    end
    log('PHASE','expired targets move 250 metres while concealed; no intel refresh')
  end)
  later(140,observe)
  local handler={}
  function handler:onEvent(event)
    if not event or event.id~=world.event.S_EVENT_SHOT or not event.initiator then return end
    local ok,name=pcall(function()return event.initiator:getName()end)
    if not ok then return end
    for _,row in ipairs(c.cases)do
      if row.receiver==name then
        local g=Group.getByName(row.groupName)
        local visible=g and fog.service:isRevealed(g:getID(),row.side)==true
        shots[row.label]=shots[row.label] or {visible=0,concealed=0}
        local phase=visible and 'visible' or 'concealed'
        shots[row.label][phase]=shots[row.label][phase]+1
        log('SHOT',row.label..'|targetState='..phase)
      end
    end
  end
  world.addEventHandler(handler)
  timer.scheduleFunction(function(_,now)
    if now-started>=240 then return nil end
    for _,row in ipairs(c.cases)do
      local ok,err=pcall(function()
        local u=assert(Unit.getByName(row.name));local receiver=assert(Unit.getByName(row.receiver))
        local g=u:getGroup();local p=u:getPoint();local eye=receiver:getPoint()
        local result={receiver:getController():isTargetDetected(u)}
        local last=result[6]
        local delta=last and math.sqrt((p.x-last.x)^2+(p.z-last.z)^2) or -1
        local visible=fog.service:isRevealed(g:getID(),row.side)
        log('SAMPLE',row.label..'|shared='..tostring(row.shared)..'|revealed='..tostring(visible)..
          '|detected='..tostring(result[1])..'|nativeVisible='..tostring(result[2])..
          '|lastSeen='..tostring(result[3])..'|lastPositionError='..string.format('%.1f',delta)..
          '|x='..string.format('%.1f',p.x)..'|z='..string.format('%.1f',p.z)..
          '|LOS='..tostring(land.isVisible({x=eye.x,y=eye.y+2,z=eye.z},{x=p.x,y=p.y+2,z=p.z})))
      end)
      if not ok then log('ERROR',row.label..'|'..tostring(err))end
    end
    return now+5
  end,nil,started+5)
  later(240,function()
    for _,row in ipairs(c.cases)do
      local count=shots[row.label] or {visible=0,concealed=0}
      log('RESULT',row.label..'|visibleShots='..count.visible..'|concealedShots='..count.concealed)
    end
    local stats=intel:getDiagnostics()
    log('COMPLETE','delivered='..stats.delivered..'|errors='..stats.errors..
      '|Review native samples and concealed shots; this is not an offline acceptance claim.')
    intel:stop()
    -- Keep expired targets hidden; stopping fog here would reveal them to native AI.
    for _,row in ipairs(c.cases)do
      Group.getByName(row.receiverGroup):getController():setOption(
        AI.Option.Ground.id.ROE,AI.Option.Ground.val.ROE.WEAPON_HOLD)
    end
    world.removeEventHandler(handler)
    trigger.action.outText('GROUND INTEL PROBE COMPLETE. 240 seconds. The mission can be ended.',60)
  end)
  trigger.action.outText('GROUND INTEL PROBE: automatic A/B and expiry test. No orders needed. Wait for COMPLETE at 240 seconds.',45)
  log('START','observations at 20/140, TTL 40, open fire at 40, concealed movement at 80')
end
