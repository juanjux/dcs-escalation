-- Matched combat measurement, not a scripted victory condition.
do
  local cfg=RCAS_COMBAT_TEST
  local start=timer.getTime()
  local records,firstContact={},{}
  local fog,detectors
  local failures=0;local casShots=0;local groundShots=0;local opened=false;local done=false
  local function log(kind,msg)
    env.info('RCAS_COMBAT_TEST|'..cfg.variant..'|'..kind..'|elapsed='..string.format('%.1f',timer.getTime()-start)..'|'..msg)
  end
  for _,v in ipairs(cfg.units) do records[v.name]={meta=v,dead=false,hits=0,initialAmmo={},shots={}} end
  local function ammoKey(name)
    return tostring(name):match('([^%.]+)$'):lower():gsub('[^%w]','')
  end
  local function nameOf(object)
    if not object then return nil end
    local ok,name=pcall(function()return object:getName()end)
    return ok and name or nil
  end
  local function weaponOf(object)
    if not object then return 'unknown' end
    local ok,name=pcall(function()return object:getTypeName()end)
    return ok and name or 'unknown'
  end
  local handler={}
  function handler:onEvent(event)
    if done then return end
    local ok,err=pcall(function()
      local source,target=nameOf(event.initiator),nameOf(event.target)
      local s,t=records[source],records[target]
      if event.id==world.event.S_EVENT_SHOT or
        (world.event.S_EVENT_SHOOTING_START and event.id==world.event.S_EVENT_SHOOTING_START) then
        if s then
          if s.meta.kind=='cas' then
            casShots=casShots+1;log('CAS_FIRE',source..'|event='..event.id..'|weapon='..weaponOf(event.weapon))
            if event.id==world.event.S_EVENT_SHOT and event.weapon then
              local key=ammoKey(weaponOf(event.weapon))
              s.shots[key]=(s.shots[key] or 0)+1
              if s.initialAmmo[key] and s.shots[key]==s.initialAmmo[key]+1 then
                log('AMMO_EXCEEDED_INITIAL',source..'|weapon='..key..'|initial='..s.initialAmmo[key]..'|shots='..s.shots[key])
              end
            end
          else
            groundShots=groundShots+1
            if cfg.groundHoldFire then
              if groundShots==1 then failures=failures+1 end
              log('ERROR','ground HOLD FIRE violated: '..source..'|event='..event.id)
            end
          end
        end
      elseif event.id==world.event.S_EVENT_HIT and t then
        t.hits=t.hits+1;t.lastHitBy=source
      elseif world.event.S_EVENT_KILL and event.id==world.event.S_EVENT_KILL and t then
        -- A native KILL is an attribution. Merely being the last HIT is not.
        -- DCS may emit a later KILL with an unavailable initiator for the same
        -- wreck. Never erase an earlier native attribution with that event.
        t.dead=true
        if not t.killer or (t.killKind=='other' and s) then
          t.killer=source;t.killKind=s and s.meta.kind or 'other'
          t.friendly=s and s.meta.side==t.meta.side or false
        end
        log('KILL',t.meta.name..'|killer='..tostring(source)..'|kind='..t.killKind..
          '|friendly='..tostring(t.friendly)..'|weapon='..weaponOf(event.weapon))
      elseif (event.id==world.event.S_EVENT_DEAD or
        (world.event.S_EVENT_UNIT_LOST and event.id==world.event.S_EVENT_UNIT_LOST) or
        (world.event.S_EVENT_CRASH and event.id==world.event.S_EVENT_CRASH)) and s then
        if not s.dead then log('DEATH',source..'|event='..event.id) end
        if event.id==world.event.S_EVENT_CRASH then
          s.crash=true;log('CRASH',source..'|previousHits='..s.hits..'|nativeKiller='..tostring(s.killer))
        end
        s.dead=true
      end
    end)
    if not ok then failures=failures+1;log('ERROR','event: '..tostring(err)) end
  end
  world.addEventHandler(handler)
  local function snapshot(final)
    local totals={red_ground={alive=0,damaged=0,cas=0,ground=0,friendly=0,unknown=0},
      blue_ground={alive=0,damaged=0,cas=0,ground=0,friendly=0,unknown=0},
      blue_cas={alive=0,damaged=0,cas=0,ground=0,friendly=0,unknown=0}}
    local sectors={}
    for name,r in pairs(records) do
      local u=Unit.getByName(name)
      local live=u and u:isExist() and u:getLife()>1
      if not live then r.dead=true end
      local total=assert(totals[r.meta.side..'_'..r.meta.kind])
      if r.dead then
        local cause=r.friendly and 'friendly' or (r.killKind=='cas' and 'cas' or r.killKind=='ground' and 'ground' or 'unknown')
        total[cause]=total[cause]+1
      else
        total.alive=total.alive+1
        local life=u:getLife()
        r.initialLife=r.initialLife or life
        if life<r.initialLife-0.1 then total.damaged=total.damaged+1 end
      end
      if final then
        log('UNIT_FINAL',name..'|dead='..tostring(r.dead)..'|killer='..tostring(r.killer)..
          '|lastHitBy_UNCONFIRMED='..tostring(r.lastHitBy)..'|hits='..r.hits..'|crashEvent='..tostring(r.crash))
        for key,count in pairs(r.shots)do
          log('STORE_USAGE',name..'|weapon='..key..'|initial='..tostring(r.initialAmmo[key])..'|shots='..count)
        end
      end
      if r.meta.kind=='ground' then
        local key=r.meta.side..'_'..(r.meta.sector or 'FRONT')
        local sector=sectors[key] or {alive=0,dead=0,cas=0};sectors[key]=sector
        if r.dead then
          sector.dead=sector.dead+1
          if r.killKind=='cas' and not r.friendly then sector.cas=sector.cas+1 end
        else sector.alive=sector.alive+1 end
      end
      if live and r.meta.kind=='cas' then
        local p=u:getPoint()
        log('AIR',name..'|altMSL='..p.y..'|inAir='..tostring(u:inAir())..'|life='..u:getLife())
        if final or math.floor(timer.getTime()-start)%60<1 then
          for _,ammo in ipairs(u:getAmmo() or {}) do
            log('AMMO',name..'|'..tostring(ammo.desc and ammo.desc.displayName)..'|count='..tostring(ammo.count))
          end
        end
      end
    end
    for name,t in pairs(totals) do
      log('SCORE',name..'|alive='..t.alive..'|damaged='..t.damaged..'|CAS_kills='..t.cas..
        '|ground_kills='..t.ground..'|friendly_kills='..t.friendly..'|unattributed_deaths='..t.unknown)
    end
    for name,t in pairs(sectors)do
      log('SECTOR',name..'|alive='..t.alive..'|dead='..t.dead..'|CAS_kills='..t.cas)
    end
    if fog then
      local revealed=0
      for _,v in ipairs(cfg.groups) do
        local g=Group.getByName(v.name)
        if g and g:isExist() then
          local c=fog.service:getContact(g:getID(),v.side=='red' and 2 or 1)
          if c and c.revealed then
            revealed=revealed+1
            if not firstContact[v.name] then
              firstContact[v.name]=true;log('FIRST_REVEAL',v.name..'|reason='..tostring(c.reason)..'|observedAt='..c.observedAt)
            end
          end
        end
      end
      local d=detectors:getDiagnostics()
      log('FOG','revealedGroups='..revealed..'|pendingSearch='..d.pendingAcquisitions..
        '|completedSearch='..d.acquisitionCompletions..'|resetSearch='..d.acquisitionResets..
        '|work='..d.work..'|LOS='..d.los..'|errors='..d.errors)
    end
    return totals
  end
  local function finish()
    local totals=snapshot(true)
    if detectors then
      failures=failures+detectors:getDiagnostics().errors
      detectors:stop()
    end
    if fog and not fog:stop() then failures=failures+1;log('ERROR','visibility restore failed') end
    done=true;world.removeEventHandler(handler)
    local inconclusive=casShots==0 and 1 or 0
    if casShots==0 then log('INCONCLUSIVE','CAS never fired; cannot infer balance from passive AI') end
    if cfg.groundHoldFire and groundShots>0 then
      inconclusive=inconclusive+1;log('INCONCLUSIVE','ground fire contaminated isolated CAS comparison')
    end
    RCAS_COMBAT_TEST_RESULT={failures=failures,inconclusive=inconclusive,casShots=casShots,groundShots=groundShots,totals=totals}
    log('RESULT','errors='..failures..'|inconclusive='..inconclusive..'|CAS_fire_events='..casShots..
      '|ground_fire_events='..groundShots..'|scenarioHash='..cfg.scenarioHash)
    trigger.action.outText('RCAS BATTLE FIN '..cfg.variant..': '..failures..' errores, '..inconclusive..
      ' inconclusos. Comparar bajas, no hay ganador impuesto. Guarda dcs.log.',600)
  end
  local ok,err=pcall(function()
    if cfg.enabled then
      fog=assert(RealisticCAS.start({enabled=true,targets=cfg.groups,ttl=cfg.ttl,debug=true}))
      detectors=RealisticCAS.startDetection(fog,{targets=cfg.targets,observers=cfg.observers,
        environment=RealisticCAS.newEnvironment({defaultCover='desert',startTime=12*3600,
          sunrise=6*3600,sunset=18*3600,weather=1,visibility=30000}),
        acquisitionSeconds=cfg.acquisitionSeconds,interval=0.25,revisit=5,
        targetBudget=64,workBudget=256,debug=true})
    end
    -- Capture undamaged baseline before the first engagement.
    for name,r in pairs(records) do
      local u=assert(Unit.getByName(name),'missing initial unit '..name)
      assert(u:isExist(),'inactive initial unit '..name)
      r.initialLife=u:getLife()
      if r.meta.kind=='cas' then
        for _,ammo in ipairs(u:getAmmo() or {})do
          local desc=ammo.desc or {}
          local key=ammoKey(desc.typeName or desc.displayName or 'unknown')
          r.initialAmmo[key]=(r.initialAmmo[key] or 0)+(ammo.count or 0)
          log('INITIAL_AMMO',name..'|weapon='..key..'|count='..tostring(ammo.count))
        end
      end
    end
    if cfg.groundHoldFire then
      for _,g in ipairs(cfg.groups)do
        local actual=assert(Group.getByName(g.name),'missing ground group')
        actual:getController():setOption(0,4)
      end
      log('PHASE','ground ROE HOLD_FIRE both sides for entire test')
    end
    timer.scheduleFunction(function(_,now)
      if done then return nil end
      local success,detail=pcall(function()
        local elapsed=now-start
        if not cfg.groundHoldFire and cfg.groundOpenAt and elapsed>=cfg.groundOpenAt and not opened then
          for _,g in ipairs(cfg.groups) do
            local actual=Group.getByName(g.name)
            if actual and actual:isExist() then actual:getController():setOption(0,2) end
          end
          opened=true;log('PHASE','ground ROE OPEN_FIRE both sides')
        end
        if elapsed>=cfg.duration then finish();return end
        snapshot(false)
        trigger.action.outText('RCAS BATTLE '..cfg.variant..' / '..math.floor(elapsed)..'s / '..cfg.duration..
          's. CAS fire events='..casShots..'. Solo log.',30,true)
      end)
      if not success then
        failures=failures+1;log('ERROR',tostring(detail));done=true
        if detectors then detectors:stop() end
        if fog then pcall(function()fog:stop()end) end
        world.removeEventHandler(handler)
        trigger.action.outText('RCAS BATTLE ERROR '..cfg.variant..'. Guarda dcs.log y sal.',600)
        return nil
      end
      if not done then return now+30 end
    end,nil,start+30)
    log('START','scenarioHash='..cfg.scenarioHash..'|acquisition='..cfg.acquisitionSeconds..
      '|ttl='..cfg.ttl..'|nativeKillEvent='..tostring(world.event.S_EVENT_KILL)..'|groundOpenAt='..tostring(cfg.groundOpenAt)..
      '|groundHoldFire='..tostring(cfg.groundHoldFire)..'|unlimitedWeaponsRequested='..tostring(cfg.unlimitedWeaponsRequested))
  end)
  if not ok then
    done=true;log('ERROR','startup: '..tostring(err));world.removeEventHandler(handler)
    if detectors then detectors:stop() end
    if fog then pcall(function()fog:stop()end) end
    trigger.action.outText('RCAS BATTLE STARTUP ERROR '..cfg.variant..'. Guarda dcs.log y sal.',600)
  end
end
