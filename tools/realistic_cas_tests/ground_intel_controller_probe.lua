-- One pair at a time: separate controller scope, update rate and native memory.
do
  local c=__CONFIG__
  local missionStarted=timer.getTime()
  local active,index,failures=nil,0,0
  local results={}
  local handler={}
  local beginCase
  local function log(kind,text)
    local elapsed=active and timer.getTime()-active.started or 0
    env.info('GROUND_INTEL_V'..c.version..'|'..kind..'|missionT='..string.format('%.1f',timer.getTime()-missionStarted)..
      '|case='..(active and active.row.label or 'none')..'|t='..string.format('%.1f',elapsed)..'|'..text)
  end
  local function pack(...)return {n=select('#',...),...}end
  local function raw(value)
    if type(value)=='table' then
      if type(value.x)=='number' and type(value.z)=='number' then
        return string.format('{x=%.1f,y=%s,z=%.1f}',value.x,tostring(value.y),value.z)
      end
      return '{table}'
    end
    return type(value)..':'..tostring(value)
  end
  local function at(state,seconds,fn)
    timer.scheduleFunction(function()
      if active~=state then return nil end
      local ok,err=pcall(fn)
      if not ok then state.errors=state.errors+1;log('ERROR',tostring(err))end
    end,nil,state.started+seconds)
  end
  local function validContact(state)
    local target=Unit.getByName(state.row.name)
    if not target or not target:isExist() or target:getLife()<=0 then return nil end
    local g=target:getGroup()
    if not state.fog.service:isRevealed(g:getID(),state.row.side)then return nil end
    return target
  end
  local function checkWeather(state)
    local thickness=world.weather.getFogThickness()
    local visibility=world.weather.getFogVisibilityDistance()
    log('WEATHER','thickness='..tostring(thickness)..'|visibility='..tostring(visibility))
    local expectedThickness=state.row.denseFog and c.fogThickness or 0
    local expectedVisibility=state.row.denseFog and c.fogVisibility or 0
    assert(math.abs(thickness-expectedThickness)<1,'fog thickness not applied')
    assert(math.abs(visibility-expectedVisibility)<1,'fog visibility not applied')
    state.weatherVerified=true
  end
  local function setWeather(state)
    assert(world.weather and world.weather.setFogThickness and world.weather.setFogVisibilityDistance and
      world.weather.getFogThickness and world.weather.getFogVisibilityDistance,'native fog API unavailable')
    -- Enable the layer before setting visibility. A visibility request while
    -- fog is disabled did not survive the native clear-to-fog transition.
    world.weather.setFogThickness(state.row.denseFog and c.fogThickness or 0)
    world.weather.setFogVisibilityDistance(state.row.denseFog and c.fogVisibility or 0)
  end
  local function sample(state,label)
    local target=assert(Unit.getByName(state.row.name),'target absent')
    local receiver=assert(Unit.getByName(state.row.receiver),'receiver absent')
    local p,eye=target:getPoint(),receiver:getPoint()
    local forward=receiver:getPosition().x
    local dx,dz=p.x-eye.x,p.z-eye.z
    local distance=math.sqrt(dx*dx+dz*dz)
    if c.sensorIsolation then
      checkWeather(state)
      if state.row.denseFog then
        assert(math.max(eye.y,p.y)+5<c.fogThickness,'units above fog layer')
        assert(distance>c.fogVisibility*5,'target inside fog visibility range')
      end
    end
    local detected=false
    local ammo=0
    for _,entry in ipairs(receiver:getAmmo()or{})do ammo=ammo+(entry.count or 0)end
    log('GEOMETRY','phase='..label..'|range='..string.format('%.1f',distance)..
      '|forwardDot='..string.format('%.3f',(dx*forward.x+dz*forward.z)/math.max(distance,1))..
      '|LOS='..tostring(land.isVisible({x=eye.x,y=eye.y+2,z=eye.z},{x=p.x,y=p.y+2,z=p.z}))..
      '|revealed='..tostring(validContact(state)~=nil)..'|ammo='..ammo)
    for _,scope in ipairs({'unit','group'})do
      local controller=scope=='unit' and receiver:getController()or receiver:getGroup():getController()
      for _,mode in ipairs({'default','explicit-all'})do
        local result
        if mode=='default' then result=pack(controller:isTargetDetected(target))
        else result=pack(controller:isTargetDetected(target,1,2,4,8,16,32))end
        detected=detected or result[1]==true
        local fields={}
        for n=1,math.max(result.n,7)do fields[#fields+1]='r'..n..'='..raw(result[n])end
        log('RAW','phase='..label..'|scope='..scope..'|mode='..mode..'|'..table.concat(fields,'|'))
      end
      local names={}
      for _,contact in pairs(controller:getDetectedTargets(1,2,4,8,16,32)or{})do
        local ok,name=pcall(function()return contact.object:getName()end)
        names[#names+1]=ok and name or '<unavailable>'
        detected=detected or (ok and name==state.row.name)
      end
      table.sort(names)
      log('NATIVE_CONTACTS','phase='..label..'|scope='..scope..'|names='..table.concat(names,','))
    end
    local elapsed=timer.getTime()-state.started
    if detected then
      state.firstDetection=state.firstDetection or elapsed
      if validContact(state)then state.nativeSamples=state.nativeSamples+1
      elseif state.lastObservation and elapsed>state.lastObservation+c.ttl+5 then
        state.concealedNativeSamples=state.concealedNativeSamples+1
      end
    end
  end
  local function notify(state)
    local method=state.row.method
    if method=='CONTROL' or method=='PRODUCTION' then return end
    local target=validContact(state)
    if not target then return end
    local receiver=assert(Unit.getByName(state.row.receiver))
    local controller=method:find('GROUP',1,true)and receiver:getGroup():getController()or receiver:getController()
    local result=pack(controller:knowTarget(target,true,true))
    state.notifications=state.notifications+1
    log('KNOW','method='..method..'|returns='..result.n..'|r1='..raw(result[1]))
    sample(state,'immediate-after-know')
  end
  local function observe(state)
    local target=assert(Unit.getByName(state.row.name))
    sample(state,'before-observation')
    assert(state.fog:observe(state.row.groupName,state.row.side,target:getPoint(),
      'visual:probe',target:getTypeName(),state.row.name))
    state.lastObservation=timer.getTime()-state.started
    sample(state,'after-observation-before-know')
    notify(state)
  end
  local function finish(state)
    log('RESULT','method='..state.row.method..'|visibleShots='..state.visibleShots..
      '|concealedShots='..state.concealedShots..'|notifications='..state.notifications..
      '|deliveryCalls='..state.intel:getDiagnostics().delivered..'|nativeSamples='..state.nativeSamples..
      '|concealedNativeSamples='..state.concealedNativeSamples..
      '|firstDetection='..tostring(state.firstDetection)..'|firstShot='..tostring(state.firstShot)..
      '|weatherVerified='..tostring(state.weatherVerified)..'|errors='..state.errors)
    failures=failures+state.errors
    results[state.row.side]=results[state.row.side]or{}
    results[state.row.side][state.row.scenario]=state
    state.intel:stop()
    for _,name in ipairs({state.row.receiverGroup,state.row.groupName})do
      local g=Group.getByName(name);if g and g:isExist()then g:destroy()end
    end
    assert(state.fog:stop(),'fog cleanup failed')
    active=nil
    timer.scheduleFunction(function()beginCase()end,nil,timer.getTime()+2)
  end
  local function setup(state)
    local row=state.row
    local receiver=assert(Unit.getByName(row.receiver),'late receiver activation failed')
    assert(receiver:isExist(),'receiver inactive')
    state.fog=assert(RealisticCAS.start({enabled=true,targets={{name=row.groupName,originalInvisible=false}},
      ttl=c.ttl,debug=true,onObservation=function(name,side,contact)
        if row.method=='PRODUCTION' then state.intel:observe(name,side,contact)end
      end,onTick=function()state.intel:tick()end}))
    state.intel=RealisticCAS.newGroundIntel(state.fog,
      {{name=row.receiver,category='ground',coalition=row.side}},
      {{name=row.name,groupName=row.groupName,coalition=row.coalition}},
      {log=function(kind,detail)log('PRODUCTION_'..kind,detail)end})
    log('CASE_START','method='..row.method..'|one target; unit and group snapshots; same geometry')
    trigger.action.outText('Ground intel V'..c.version..': '..index..'/'..#c.cases..' '..row.label,20)
    at(state,20,function()observe(state)end)
    at(state,30,function()
      receiver:getGroup():getController():setOption(AI.Option.Ground.id.ROE,AI.Option.Ground.val.ROE.OPEN_FIRE)
      log('PHASE','OPEN_FIRE')
    end)
    at(state,120,function()
      local g=assert(Group.getByName(row.groupName));local p=g:getUnits()[1]:getPoint()
      assert(not validContact(state),'target must be concealed before movement')
      g:getController():setTask({id='Mission',params={route={points={
        {x=p.x,y=p.z,speed=5,speed_locked=true,ETA_locked=true,ETA=0,type='Turning Point',action='Off Road',
          task={id='ComboTask',params={tasks={}}}},
        {x=p.x,y=p.z+250,speed=5,speed_locked=true,ETA_locked=false,type='Turning Point',action='Off Road',
          task={id='ComboTask',params={tasks={}}}}
      }}}})
      log('PHASE','concealed target moving 250 metres')
    end)
    at(state,150,function()observe(state)end)
    -- Diagnostic refresh deliberately tests the native API; it never observes a
    -- target or extends the fog lifetime, and stops as soon as the contact expires.
    if row.method:find('REFRESH',1,true)then
      timer.scheduleFunction(function(_,now)
        if active~=state then return nil end
        local ok,err=pcall(function()notify(state)end)
        if not ok then state.errors=state.errors+1;log('ERROR',tostring(err))end
        return now+c.refresh
      end,nil,state.started+25)
    end
    timer.scheduleFunction(function(_,now)
      if active~=state then return nil end
      local ok,err=pcall(function()sample(state,'periodic')end)
      if not ok then state.errors=state.errors+1;log('ERROR',tostring(err))end
      return now+5
    end,nil,state.started+5)
    at(state,c.duration,function()finish(state)end)
  end
  local function reportIsolation()
    for _,side in ipairs({2,1})do
      local rows=results[side]or{}
      local clear,dense=rows.CLEAR_CONTROL,rows.FOG_CONTROL
      local qualified=clear and dense and clear.errors==0 and dense.errors==0 and
        clear.weatherVerified and dense.weatherVerified and clear.nativeSamples>0 and
        clear.visibleShots>0 and dense.nativeSamples==0 and dense.visibleShots==0 and
        clear.concealedShots==0 and dense.concealedShots==0 and
        clear.concealedNativeSamples==0 and dense.concealedNativeSamples==0
      local name=side==2 and 'BLUE' or 'RED'
      local status=qualified and 'ISOLATED' or 'INCONCLUSIVE'
      log('QUALIFICATION','side='..name..'|status='..status..
        '|clearAcquisition='..tostring(clear and clear.nativeSamples or 'missing')..
        '|clearShots='..tostring(clear and clear.visibleShots or 'missing')..
        '|fogAcquisition='..tostring(dense and dense.nativeSamples or 'missing')..
        '|fogShots='..tostring(dense and dense.visibleShots or 'missing'))
      trigger.action.outText('Ground intel V'..c.version..' '..name..' sensor control: '..status,45)
      for _,key in ipairs({'FOG_PRODUCTION','FOG_UNIT_REFRESH','FOG_GROUP_REFRESH'})do
        local row=rows[key]
        local valid=qualified and row and row.errors==0 and row.weatherVerified
        log('EFFECT','side='..name..'|method='..key..
          '|knowledge='..(valid and (row.nativeSamples>0 and 'OBSERVED' or 'NOT_OBSERVED')or 'INCONCLUSIVE')..
          '|engagement='..(valid and (row.visibleShots>0 and 'OBSERVED' or 'NOT_OBSERVED')or 'INCONCLUSIVE')..
          '|expiry='..(row and row.errors==0 and
            (row.concealedShots==0 and row.concealedNativeSamples==0 and 'NO_LEAK_OBSERVED' or 'LEAK_OBSERVED')or 'INCONCLUSIVE'))
      end
    end
  end
  beginCase=function()
    index=index+1
    if index>#c.cases then
      if c.sensorIsolation then
        reportIsolation()
        local ok,err=pcall(function()setWeather({row={denseFog=false}})end)
        if not ok then failures=failures+1;log('WEATHER_CLEANUP_ERROR',tostring(err))end
      end
      log('COMPLETE','cases='..#c.cases..'|errors='..failures..'|Native behavior requires review, not inferred from call acceptance.')
      world.removeEventHandler(handler)
      trigger.action.outText('GROUND INTEL V'..c.version..' COMPLETE. Sequence finished; errors='..failures..
        '. Control qualification and measured effects are in dcs.log. The mission can be ended.',90)
      return
    end
    local row=c.cases[index]
    local state={row=row,started=timer.getTime()+(c.sensorIsolation and 4 or 2),
      visibleShots=0,concealedShots=0,notifications=0,errors=0,
      nativeSamples=0,concealedNativeSamples=0}
    active=state
    local function activationFailed(err)
      failures=failures+1;log('ACTIVATION_ERROR',tostring(err))
      for _,name in ipairs({row.receiverGroup,row.groupName})do
        pcall(function()
          local g=Group.getByName(name);if g and g:isExist()then g:destroy()end
        end)
      end
      active=nil
      timer.scheduleFunction(function()beginCase()end,nil,timer.getTime()+2)
    end
    local function activate()
      if active~=state then return end
      local ok,err=pcall(function()
        -- No units exist during the weather transition. Check actual native
        -- getters after two seconds, before allowing any sensor acquisition.
        if c.sensorIsolation then checkWeather(state)end
        trigger.action.activateGroup(assert(Group.getByName(row.receiverGroup)))
        trigger.action.activateGroup(assert(Group.getByName(row.groupName)))
      end)
      if not ok then activationFailed(err);return end
      timer.scheduleFunction(function()
        if active~=state then return end
        local ready,why=pcall(function()setup(state)end)
        if not ready then
          state.errors=state.errors+1;log('SETUP_ERROR',tostring(why))
          if state.intel then state.intel:stop()end
          for _,name in ipairs({row.receiverGroup,row.groupName})do
            local g=Group.getByName(name);if g and g:isExist()then g:destroy()end
          end
          if state.fog then state.fog:stop()end
          failures=failures+state.errors;active=nil
          timer.scheduleFunction(function()beginCase()end,nil,timer.getTime()+2)
        end
      end,nil,state.started)
    end
    if c.sensorIsolation then
      local ok,err=pcall(function()setWeather(state)end)
      if not ok then activationFailed(err);return end
      timer.scheduleFunction(activate,nil,timer.getTime()+2)
    else activate()end
  end
  function handler:onEvent(event)
    local state=active
    if not state or not state.fog or not event then return end
    if event.id~=world.event.S_EVENT_SHOT and event.id~=world.event.S_EVENT_HIT then return end
    local ok,origin=pcall(function()return event.initiator:getName()end)
    if not ok or origin~=state.row.receiver then return end
    local visible=validContact(state)~=nil
    if event.id==world.event.S_EVENT_SHOT then
      state.firstShot=state.firstShot or timer.getTime()-state.started
      if visible then state.visibleShots=state.visibleShots+1 else state.concealedShots=state.concealedShots+1 end
      log('SHOT','revealed='..tostring(visible))
    else
      local named,target=pcall(function()return event.target:getName()end)
      log('HIT','target='..(named and target or '<unknown>')..'|revealed='..tostring(visible))
    end
  end
  world.addEventHandler(handler)
  log('START',#c.cases..' sequential 240-second cases; observations20/150; TTL80; no overlapping live pairs'..
    '|sensorIsolation='..tostring(c.sensorIsolation))
  beginCase()
end
