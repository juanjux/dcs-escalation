-- Test instrumentation only. Enemy truth is logged, never passed to navigation,
-- visibility changes, sensor observations or flight controllers.
do
  local c=LIVE_CONFIG
  local aircraft,threats,pairsState={},{},{}
  local function call(object,method)
    if not object then return nil end
    local ok,value=pcall(function()return object[method](object)end)
    if ok then return value end
    return nil
  end
  local function unit(name)
    local ok,u=pcall(Unit.getByName,name)
    if ok and call(u,'isExist') then return u end
  end
  local function log(kind,text)
    env.info('AFAC_LIVE_FIRE|'..kind..'|t='..timer.getTime()..'|'..text)
  end
  for _,row in ipairs(c.aircraft)do
    row.hits=0
    aircraft[row.name]=row
  end
  for _,row in ipairs(c.threats)do
    row.shots=0;row.bursts=0;row.firing=false
    threats[row.name]=row
  end
  local function knowledge(row,side)
    if row.known then return true,'campaign' end
    local mission=RealisticCAS.mission
    local service=mission and mission.fog and mission.fog.service
    local g=Group.getByName(row.groupName)
    if not service or not g then return false,'unknown' end
    local id=call(g,'getID')
    if not id then return false,'unknown' end
    local known=service:isRevealed(id,side)==true
    local contact=service:getContact(id,side)
    return known,contact and contact.reason or 'unknown'
  end
  local function phase(row)
    if (RealisticCAS.afacReturn or {})[row.group] then return 'return' end
    if (RealisticCAS.afacStations or {})[row.group] then return 'station' end
    return 'approach'
  end
  local function health(u)
    local life,maximum=call(u,'getLife'),call(u,'getLife0')
    return life and maximum and maximum>0 and life/maximum or -1
  end
  local handler={}
  function handler:onEvent(event)
    if not event or not event.id then return end
    local name=call(event.initiator,'getName')
    local threat=threats[name]
    if threat then
      if event.id==world.event.S_EVENT_SHOT then
        threat.shots=threat.shots+1
      elseif world.event.S_EVENT_SHOOTING_START and event.id==world.event.S_EVENT_SHOOTING_START then
        threat.bursts=threat.bursts+1;threat.firing=true
      elseif world.event.S_EVENT_SHOOTING_END and event.id==world.event.S_EVENT_SHOOTING_END then
        threat.firing=false
      end
      if not threat.firstFire and (threat.shots>0 or threat.bursts>0) then
        threat.firstFire=timer.getTime()
        local known,reason=knowledge(threat,3-threat.coalition)
        log('FIRST_FIRE','threat='..name..'|known='..tostring(known)..'|reason='..reason)
      end
    end
    if event.id==world.event.S_EVENT_HIT then
      local target=call(event.target,'getName')
      local row=aircraft[target]
      if row then
        row.hits=row.hits+1
        log('HIT','case='..row.case..'|source='..tostring(name)..'|phase='..phase(row)..
          '|health='..health(event.target)..'|weapon='..tostring(call(event.weapon,'getTypeName')))
      end
    end
  end
  world.addEventHandler(handler)
  log('START','readOnly=true|interval=1|groundTruthNotShared=true|envelopes=approximate'..
    '|fireDiscovery='..tostring(c.fireDiscovery)..'|acquisitionSeconds='..tostring(c.acquisitionSeconds))
  timer.scheduleFunction(function(_,now)
    local samples={}
    for _,t in ipairs(c.threats)do
      local u=unit(t.name)
      local p=call(u,'getPoint')
      if p then samples[#samples+1]={meta=t,point=p}end
    end
    for _,row in ipairs(c.aircraft)do
      local u=unit(row.name)
      local p=call(u,'getPoint')
      if p and call(u,'inAir') then
        local stage=phase(row)
        local nav=(RealisticCAS.afacNavigation or {})[row.group]
        log('AIRCRAFT','case='..row.case..'|phase='..stage..'|health='..health(u)..
          '|AGL='..(p.y-land.getHeight({x=p.x,y=p.z}))..'|revision='..tostring(nav and nav.revision))
        for _,sample in ipairs(samples)do
          local t,q=sample.meta,sample.point
          local known,reason=knowledge(t,row.side)
          local dx,dz=p.x-q.x,p.z-q.z
          local horizontal=math.sqrt(dx*dx+dz*dz)
          local relative=p.y-q.y
          local inside=horizontal<=t.radius and (not t.ceiling or relative<=t.ceiling)
          local buffered=horizontal<=t.radius+1000 and (not t.ceiling or relative<=t.ceiling+300)
          local key=row.name..'/'..t.name
          local state=pairsState[key] or {exposure=0};pairsState[key]=state
          if state.known and state.inside and known and inside then
            state.exposure=state.exposure+now-state.last
          end
          if known and buffered and not (state.known and state.buffered) then
            state.entered=now
            log('KNOWN_DANGER','case='..row.case..'|threat='..t.name..'|phase='..stage..
              '|reason='..reason..'|horizontal='..horizontal..'|relativeAltitude='..relative)
          elseif state.entered and not buffered then
            log('ESCAPED','case='..row.case..'|threat='..t.name..'|phase='..stage..
              '|elapsed='..(now-state.entered)..'|known='..tostring(known))
            state.entered=nil
          end
          if horizontal<=t.radius+5000 or not state.lastLog or now-state.lastLog>=10 then
            log('ENVELOPE','case='..row.case..'|threat='..t.name..'|phase='..stage..
              '|known='..tostring(known)..'|reason='..reason..'|horizontal='..horizontal..
              '|slant='..math.sqrt(horizontal*horizontal+relative*relative)..
              '|relativeAltitude='..relative..'|radius='..t.radius..'|ceiling='..tostring(t.ceiling)..
              '|insideModel='..tostring(inside)..'|insideBuffer='..tostring(buffered)..
              '|sampledKnownExposure='..state.exposure..'|shots='..t.shots..
              '|bursts='..t.bursts..'|firing='..tostring(t.firing)..'|hits='..row.hits)
            state.lastLog=now
          end
          state.last=now;state.known=known;state.inside=inside;state.buffered=buffered
        end
      end
    end
    return now<3600 and now+1 or nil
  end,nil,timer.getTime()+1)
end
