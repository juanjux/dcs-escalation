-- Standalone engineering instrument, NOT the Realistic CAS mission plugin.
-- RCAS_CONFIG is embedded by build_missions.py. No MIST/MOOSE dependency.
do
  local cfg = RCAS_CONFIG
  local started = timer.getTime()
  local counts, ammoPrevious, snapshots, weapons = {}, {}, {}, {}
  local errors, applied, phase = 0, {}, "INIT"
  local experiment, lastSample
  local function log(s) env.info("RCAS_TEST|" .. cfg.name .. "|" .. s) end
  local function safe(label, f)
    local ok, value = pcall(f)
    if not ok then
      errors = errors + 1
      log("ERROR|" .. label .. "|" .. tostring(value))
    end
    return ok, value
  end
  local function unit(n)
    local u = Unit.getByName(n)
    if u and u:isExist() then return u end
  end
  local function group(n)
    local g = Group.getByName(n)
    if g and g:isExist() then return g end
  end
  local function dump(v, depth)
    if type(v) ~= "table" then return tostring(v) end
    if depth > 6 then return "..." end
    local r = {}
    for k, x in pairs(v) do r[#r+1] = tostring(k).."="..dump(x,depth+1) end
    table.sort(r)
    return "{"..table.concat(r,",").."}"
  end
  local function position(p)
    if not p then return "nil" end
    return string.format("%.1f,%.1f,%.1f",p.x,p.y,p.z)
  end
  local function count(n)
    if not counts[n] then counts[n] = {shot=0, gun=0, hit=0, loss=0, spent=0} end
    return counts[n]
  end
  local function objectName(o)
    if not o then return "nil" end
    local ok, n = pcall(function() return o:getName() end)
    return ok and n or "unknown"
  end
  local events = {}
  for _, key in ipairs({"S_EVENT_SHOT","S_EVENT_SHOOTING_START","S_EVENT_SHOOTING_END",
    "S_EVENT_HIT","S_EVENT_DEAD","S_EVENT_CRASH","S_EVENT_KILL","S_EVENT_UNIT_LOST"}) do
    local id = world.event[key]
    log("EVENT_AVAILABLE|"..key.."="..tostring(id))
    if id then events[id] = key end
  end
  local handler = {}
  function handler:onEvent(e)
    if not e or not events[e.id] then return end
    safe("event",function()
      local kind, n, target = events[e.id], objectName(e.initiator), objectName(e.target)
      local c = count(n)
      if kind == "S_EVENT_SHOT" then c.shot = c.shot + 1 end
      if kind == "S_EVENT_SHOOTING_START" then c.gun = c.gun + 1 end
      if kind == "S_EVENT_HIT" then count(target).hit = count(target).hit + 1 end
      if kind == "S_EVENT_DEAD" or kind == "S_EVENT_CRASH" or kind == "S_EVENT_UNIT_LOST" then
        c.loss = c.loss + 1 -- raw event count, NOT unique losses
      end
      local weapon = "nil"
      if e.weapon then
        pcall(function() weapon=e.weapon:getTypeName() end)
        if kind == "S_EVENT_SHOT" then
          local id = #weapons+1
          weapons[id] = {object=e.weapon,shooter=n,kind=weapon,active=true}
          log("WEAPON_NEW|id="..id.."|shooter="..n.."|kind="..weapon)
        end
      end
      log(string.format("EVENT|t=%.1f|%s|from=%s|target=%s|weapon=%s|phase=%s",
        timer.getTime()-started,kind,n,target,weapon,phase))
      if e.initiator then
        pcall(function() log("EVENT_ORIGIN|"..n.."|"..position(e.initiator:getPoint())) end)
      end
      if experiment then experiment:onEvent(e, n, weapon) end
    end)
  end
  world.addEventHandler(handler)

  local function act(a)
    if a.op == "phase" then phase = a.label; return end
    if a.op == "mark" then
      local p = {x=a.x,y=land.getHeight({x=a.x,y=a.z}),z=a.z}
      if a.coalition then trigger.action.markToCoalition(a.id,a.text,p,a.coalition,true)
      else trigger.action.markToAll(a.id,a.text,p,true) end
      return
    end
    if a.op == "removeMark" then trigger.action.removeMark(a.id); return end
    if a.op == "snapshot" then
      local u = assert(unit(a.target),a.target.." missing")
      local p = u:getPoint()
      snapshots[a.target] = {x=p.x,y=p.y,z=p.z}
      trigger.action.markToAll(a.id,"LAST KNOWN (frozen)",snapshots[a.target],true)
      return
    end
    local obj = a.scope == "unit" and unit(a.target) or group(a.target)
    assert(obj,a.target.." missing")
    local c = assert(obj:getController(),"no controller: "..a.target)
    if a.op == "invisible" then
      c:setCommand({id="SetInvisible",params={value=a.value}})
    elseif a.op == "immortal" then
      c:setCommand({id="SetImmortal",params={value=a.value}})
    elseif a.op == "roe" then c:setOption(0,a.value)
    elseif a.op == "ground_roe" then
      local value = assert(AI.Option.Ground.val.ROE[a.value],"unknown ground ROE")
      c:setOption(AI.Option.Ground.id.ROE,value)
      log("GROUND_ROE|"..a.target.."|"..a.value.."="..value)
    elseif a.op == "task" then c:pushTask(a.task)
    elseif a.op == "know" then
      c:knowTarget(assert(unit(a.other),a.other.." missing"),true,true)
    elseif a.op == "move" then
      local first = obj:getUnit(1):getPoint()
      c:setTask({id="Mission",params={route={points={
        {x=first.x,y=first.z,action="Off Road",type="Turning Point",speed=a.speed,
          speed_locked=true,task={id="ComboTask",params={tasks={}}}},
        {x=a.x,y=a.z,action="Off Road",type="Turning Point",speed=a.speed,
          speed_locked=true,task={id="ComboTask",params={tasks={}}}}
      }}}})
    else error("unknown operation: "..a.op) end
    log("ACTION|t="..math.floor(timer.getTime()-started).."|"..dump(a,0))
  end

  local function samplePair(pair)
    local observer, target = unit(pair.observer), unit(pair.target)
    if not observer or not target then return pair.label..": absent/dead" end
    local c = observer:getController()
    if pair.controller == "group" then c = observer:getGroup():getController() end
    assert(c,"no observer controller")
    local p, q = observer:getPoint(), target:getPoint()
    local pEye = {x=p.x,y=p.y+2,z=p.z}
    local qEye = {x=q.x,y=q.y+2,z=q.z}
    local range = math.sqrt((p.x-q.x)^2+(p.y-q.y)^2+(p.z-q.z)^2)
    local fields, summary = {}, "?"
    for _, mode in ipairs({"ALL","VISUAL","OPTIC","RADAR"}) do
      local result
      if mode == "ALL" then result={c:isTargetDetected(target)}
      else result={c:isTargetDetected(target,Controller.Detection[mode])} end
      fields[#fields+1] = mode.."="..tostring(result[1]).."/vis="..tostring(result[2])..
        "/knowType="..tostring(result[3]).."/knowDistance="..tostring(result[4])..
        "/lastTime="..tostring(result[5]).."/lastPos="..position(result[6])..
        "/lastVel="..position(result[7])
      local raw = {}
      for i=1,7 do raw[i]="r"..i.."("..type(result[i])..")="..dump(result[i],0) end
      log("DETECT_RAW|"..pair.label.."|"..mode.."|"..table.concat(raw,"|"))
      if mode == "ALL" then summary=tostring(result[1]) end
    end
    local stale = snapshots[pair.target]
    local drift = stale and math.sqrt((q.x-stale.x)^2+(q.z-stale.z)^2) or 0
    log(string.format("DETECT|t=%.1f|%s|range=%.0f|AGL=%.0f|LOS=%s|actual=%s|moved=%.0f|%s",
      timer.getTime()-started,pair.label,range,p.y-land.getHeight({x=p.x,y=p.z}),
      tostring(land.isVisible(pEye,qEye)),position(q),drift,table.concat(fields,"|")))
    return pair.label..": det="..summary.." r="..math.floor(range).."m"
  end

  if RCAS_EXPERIMENT_FACTORY then
    experiment=RCAS_EXPERIMENT_FACTORY({cfg=cfg,unit=unit,group=group,act=act,
      log=log,started=started,position=position})
  end

  local function tick(_, now)
    local elapsed = now-started
    for i,a in ipairs(cfg.actions) do
      if elapsed >= a.at and not applied[i] then
        applied[i] = true
        safe("action "..i,function() act(a) end)
      end
    end
    if experiment and not experiment.done then
      local ok = safe("experiment",function() experiment:tick(elapsed) end)
      if not ok then experiment:finish("INVALID: error de instrumentacion") end
    end
    if experiment and lastSample and elapsed-lastSample<5 and not experiment.done then
      return now+1
    end
    lastSample=elapsed
    local lines = {cfg.name.." / "..math.floor(elapsed).."s / "..phase.." / ERR="..errors}
    if experiment then
      for _, line in ipairs(experiment:lines(elapsed)) do lines[#lines+1]=line end
    end
    for _, name in ipairs(cfg.units) do
      safe("state "..name,function()
        local u, c = unit(name), count(name)
        if u then
          local remaining = 0
          local inventory = u:getAmmo() or {}
          for _, ammo in ipairs(inventory) do remaining=remaining+ammo.count end
          if ammoPrevious[name] ~= remaining then
            log("AMMO|t="..math.floor(elapsed).."|"..name.."|"..dump(inventory,0))
          end
          if ammoPrevious[name] and remaining < ammoPrevious[name] then
            c.spent = c.spent + ammoPrevious[name]-remaining
          end
          ammoPrevious[name] = remaining
          local p = u:getPoint()
          log(string.format("STATE|t=%.1f|%s|life=%.1f|AGL=%.0f|position=%s|ammo=%d|spent=%d",
            elapsed,name,u:getLife(),p.y-land.getHeight({x=p.x,y=p.z}),position(p),remaining,c.spent))
          log("MOTION|t="..math.floor(elapsed).."|"..name.."|velocity="..position(u:getVelocity())..
            "|orientation="..dump(u:getPosition(),0).."|radar="..dump({u:getRadar()},0))
        end
        if cfg.display[name] then
          lines[#lines+1] = name..": "..(u and "alive" or "ABSENT")..
            " shot="..c.shot.." gun="..c.gun.." hit="..c.hit.." ammo-="..c.spent
        end
      end)
    end
    for _, pair in ipairs(cfg.pairs) do
      local ok, msg = safe("detection "..pair.label,function() return samplePair(pair) end)
      if ok and pair.display then lines[#lines+1]=msg end
    end
    for id, w in ipairs(weapons) do
      if w.active then
        safe("weapon "..id,function()
          if not w.object:isExist() then
            w.active=false
            log("WEAPON_GONE|t="..math.floor(elapsed).."|id="..id)
          else
            log("WEAPON_TRACK|t="..math.floor(elapsed).."|id="..id.."|shooter="..w.shooter..
              "|kind="..w.kind.."|position="..position(w.object:getPoint())..
              "|target="..objectName(w.object:getTarget()))
          end
        end)
      end
    end
    if elapsed >= cfg.duration or (experiment and experiment.done) then
      lines[#lines+1]="FIN. Captura + dcs.log (RCAS_TEST). No mas fases."
    end
    trigger.action.outText(table.concat(lines,"\n"),11,true)
    log("SUMMARY|"..table.concat(lines," | "))
    if elapsed < cfg.duration and not (experiment and experiment.done) then
      return now+(experiment and 1 or 10)
    end
  end

  for _, name in ipairs(cfg.units) do
    safe("sensors "..name,function()
      local u = unit(name)
      if u then
        log("SENSORS|"..name.."|"..dump(u:getSensors(),0))
        log("RADAR|"..name.."|"..dump({u:getRadar()},0))
      end
    end)
  end
  log("START|"..dump(cfg,0))
  log("ENVIRONMENT|"..dump({date=env.mission.date,start_time=env.mission.start_time,
    weather=env.mission.weather,theatre=env.mission.theatre,forcedOptions=env.mission.forcedOptions},0))
  timer.scheduleFunction(tick,nil,started+1)
end
