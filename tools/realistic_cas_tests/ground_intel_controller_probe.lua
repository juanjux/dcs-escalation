-- One pair at a time: separate controller scope, update rate and native memory.
do
  local c=__CONFIG__
  local missionStarted=timer.getTime()
  local active,index,failures=nil,0,0
  local handler={}
  local beginCase
  local function log(kind,text)
    local elapsed=active and timer.getTime()-active.started or 0
    env.info('GROUND_INTEL_V2|'..kind..'|missionT='..string.format('%.1f',timer.getTime()-missionStarted)..
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
  local function sample(state,label)
    local target=assert(Unit.getByName(state.row.name),'target absent')
    local receiver=assert(Unit.getByName(state.row.receiver),'receiver absent')
    local p,eye=target:getPoint(),receiver:getPoint()
    local forward=receiver:getPosition().x
    local dx,dz=p.x-eye.x,p.z-eye.z
    local distance=math.sqrt(dx*dx+dz*dz)
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
        local fields={}
        for n=1,math.max(result.n,7)do fields[#fields+1]='r'..n..'='..raw(result[n])end
        log('RAW','phase='..label..'|scope='..scope..'|mode='..mode..'|'..table.concat(fields,'|'))
      end
      local names={}
      for _,contact in pairs(controller:getDetectedTargets(1,2,4,8,16,32)or{})do
        local ok,name=pcall(function()return contact.object:getName()end)
        names[#names+1]=ok and name or '<unavailable>'
      end
      table.sort(names)
      log('NATIVE_CONTACTS','phase='..label..'|scope='..scope..'|names='..table.concat(names,','))
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
    sample(state,'after-observation-before-know')
    notify(state)
  end
  local function finish(state)
    log('RESULT','method='..state.row.method..'|visibleShots='..state.visibleShots..
      '|concealedShots='..state.concealedShots..'|notifications='..state.notifications..
      '|deliveryCalls='..state.intel:getDiagnostics().delivered..'|errors='..state.errors)
    failures=failures+state.errors
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
    trigger.action.outText('Ground intel V2: '..index..'/'..#c.cases..' '..row.label,20)
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
  beginCase=function()
    index=index+1
    if index>#c.cases then
      log('COMPLETE','cases='..#c.cases..'|errors='..failures..'|Native behavior requires review, not inferred from call acceptance.')
      world.removeEventHandler(handler)
      trigger.action.outText('GROUND INTEL V2 COMPLETE. Sequence finished; errors='..failures..'. The mission can be ended.',90)
      return
    end
    local row=c.cases[index]
    local state={row=row,started=timer.getTime()+2,visibleShots=0,concealedShots=0,notifications=0,errors=0}
    active=state
    local ok,err=pcall(function()
      trigger.action.activateGroup(assert(Group.getByName(row.receiverGroup)))
      trigger.action.activateGroup(assert(Group.getByName(row.groupName)))
    end)
    if not ok then
      failures=failures+1;log('ACTIVATION_ERROR',tostring(err))
      for _,name in ipairs({row.receiverGroup,row.groupName})do
        pcall(function()
          local g=Group.getByName(name);if g and g:isExist()then g:destroy()end
        end)
      end
      active=nil
      timer.scheduleFunction(function()beginCase()end,nil,timer.getTime()+2)
      return
    end
    timer.scheduleFunction(function()
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
  function handler:onEvent(event)
    local state=active
    if not state or not state.fog or not event then return end
    if event.id~=world.event.S_EVENT_SHOT and event.id~=world.event.S_EVENT_HIT then return end
    local ok,origin=pcall(function()return event.initiator:getName()end)
    if not ok or origin~=state.row.receiver then return end
    local visible=validContact(state)~=nil
    if event.id==world.event.S_EVENT_SHOT then
      if visible then state.visibleShots=state.visibleShots+1 else state.concealedShots=state.concealedShots+1 end
      log('SHOT','revealed='..tostring(visible))
    else
      local named,target=pcall(function()return event.target:getName()end)
      log('HIT','target='..(named and target or '<unknown>')..'|revealed='..tostring(visible))
    end
  end
  world.addEventHandler(handler)
  log('START','12 sequential 240-second cases; observations20/150; TTL80; no overlapping live pairs')
  beginCase()
end
