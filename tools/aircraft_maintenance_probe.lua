-- Standalone diagnostic only. Never changes campaign state or directly sets life.
EscalationAircraftProbe = { records = {}, samples = {}, cancelled = false }
local P = EscalationAircraftProbe
local config = ESCALATION_AIRCRAFT_PROBE
local tracked, previous, lastLive = {}, {}, {}
for _, name in ipairs(config.units) do tracked[name] = true end

local function read(object, method)
    if not object then return nil end
    local ok, value = pcall(function() return object[method](object) end)
    if ok then return value end
end

local function finite(value)
    return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function quote(value)
    local escapes = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
    return '"' .. tostring(value):gsub('[%z\1-\31\\"]', function(char)
        return escapes[char] or string.format("\\u%04x", char:byte())
    end) .. '"'
end

local function encode(record)
    local fields = {}
    for key, value in pairs(record) do
        local encoded
        if type(value) == "string" then encoded = quote(value)
        elseif type(value) == "boolean" then encoded = tostring(value)
        elseif finite(value) then encoded = tostring(value) end
        if encoded then fields[#fields + 1] = quote(key) .. ":" .. encoded end
    end
    table.sort(fields)
    return "{" .. table.concat(fields, ",") .. "}"
end

-- Always log to dcs.log. A separate JSONL copy is optional: default-sanitized DCS
-- installations must still run the diagnostic without requiring any changes.
local logfile
pcall(function()
    if not (lfs and io and os) then return end
    local directory = lfs.writedir() .. "_debug_logs"
    lfs.mkdir(directory)
    local filename = directory .. "/aircraft-maintenance-probe-" .. os.date("!%Y%m%dT%H%M%SZ") .. ".jsonl"
    logfile = io.open(filename, "a")
end)

local function log(record)
    record.time = record.time or timer.getTime()
    local text = encode(record)
    P.records[#P.records + 1] = record
    env.info("ESCALATION_AIRCRAFT_PROBE " .. text)
    if logfile then
        local ok = pcall(function() logfile:write(text .. "\n"); logfile:flush() end)
        if not ok then logfile = nil end
    end
end

local function nearest(record, point, owner)
    if not point or not owner then return end
    local friendly, enemy = math.huge, math.huge
    for _, base in ipairs(config.bases) do
        local distance = math.sqrt((point.x - base.x)^2 + (point.z - base.z)^2)
        if base.coalition == owner and distance < friendly then
            friendly = distance
            record.nearest_friendly = base.name
            record.friendly_distance_m = distance
        elseif base.coalition ~= owner and base.coalition ~= 0 and distance < enemy then
            enemy = distance
            record.nearest_enemy = base.name
            record.enemy_distance_m = distance
        end
    end
end

function P.sample(name, reason, object)
    object = object or Unit.getByName(name)
    local record = {kind = "sample", name = name, reason = reason, time = timer.getTime()}
    record.exists = object ~= nil and read(object, "isExist") == true
    record.life = read(object, "getLife")
    record.life0 = read(object, "getLife0")
    record.in_air = read(object, "inAir")
    record.coalition = read(object, "getCoalition")
    record.aircraft_type = read(object, "getTypeName")
    if finite(record.life) and finite(record.life0) and record.life0 > 0 and record.life >= 0 then
        record.raw_life_ratio = record.life / record.life0
        record.life_ratio = math.max(0, math.min(1, record.raw_life_ratio))
    end
    local point = read(object, "getPoint")
    if point then
        record.x, record.y, record.z = point.x, point.y, point.z
        local ok, height = pcall(function()
            return land.getHeight({x = point.x, y = point.z})
        end)
        if ok and finite(height) then
            record.ground_height_m = height
            record.agl_m = point.y - height
        end
    end
    if reason ~= "periodic" then nearest(record, point, record.coalition) end
    local old = previous[name]
    if reason ~= "periodic" or not old or old.life ~= record.life or
        old.in_air ~= record.in_air or old.exists ~= record.exists or
        timer.getTime() - old.time >= 10 then
        log(record)
        previous[name] = record
    end
    if record.exists and finite(record.life) and record.life > 0 then
        lastLive[name] = record
    end
    P.samples[name] = record
    return record
end

local eventNames = {}
for _, name in ipairs({"BIRTH", "TAKEOFF", "RUNWAY_TAKEOFF", "LAND", "RUNWAY_TOUCH",
    "HIT", "KILL", "CRASH", "DEAD", "UNIT_LOST", "EJECTION", "PILOT_DEAD",
    "PLAYER_LEAVE_UNIT", "ENGINE_SHUTDOWN"}) do
    local value = world.event["S_EVENT_" .. name]
    if value then eventNames[value] = name end
end

function P:onEvent(event)
    local eventName = eventNames[event.id]
    if not eventName then return end
    local targetEvent = eventName == "HIT" or eventName == "KILL"
    local object
    if targetEvent then object = event.target else object = event.initiator end
    local name = read(object, "getName")
    if not tracked[name] then return end
    local record = {kind = "event", event = eventName, name = name, time = event.time}
    local prior = lastLive[name]
    if prior then
        record.prior_time = prior.time
        record.prior_life_ratio = prior.life_ratio
        record.prior_in_air = prior.in_air
    end
    record.place_name = read(event.place, "getName")
    record.place_coalition = read(event.place, "getCoalition")
    record.place_id = read(event.place, "getID")
    record.place_known = record.place_name ~= nil
    if targetEvent then
        record.attacker = read(event.initiator, "getName")
        record.attacker_type = read(event.initiator, "getTypeName")
        record.attacker_coalition = read(event.initiator, "getCoalition")
        record.weapon = read(event.weapon, "getTypeName")
    end
    nearest(record, read(object, "getPoint"), read(object, "getCoalition"))
    log(record)
    P.sample(name, "event_" .. eventName, object)
end

function P.report()
    local lines = {"Aircraft maintenance telemetry (raw DCS health)"}
    for _, name in ipairs(config.units) do
        local sample = P.sample(name, "manual_report")
        local health = sample.life_ratio and string.format("%.2f%%", sample.life_ratio * 100) or "unknown"
        lines[#lines + 1] = name .. ": " .. health
    end
    trigger.action.outText(table.concat(lines, "\n"), 20)
end

-- Real blast damage, not a native life setter: whether physical damage changes
-- getLife is the question being tested. Only the dedicated parked targets are hit.
local function blast(name, power)
    local object = Unit.getByName(name)
    local point = read(object, "getPoint")
    if point and read(object, "isExist") then
        P.sample(name, "before_blast")
        log({kind = "blast", name = name, power_kg_tnt = power})
        trigger.action.explosion({x = point.x + 5, y = point.y + 1, z = point.z}, power)
    end
end

local root = missionCommands.addSubMenu("Aircraft maintenance probe")
missionCommands.addCommand("Show health readings / sample now", root, P.report)
missionCommands.addCommand("Mark canopy change for comparison", root, function()
    log({kind = "marker", name = config.player, reason = "CANOPY_VISUAL_CHANGED"})
    P.report()
end)
missionCommands.addCommand("Stop automatic target blasts", root, function()
    P.cancelled = true
    log({kind = "marker", reason = "AUTOMATIC_BLASTS_CANCELLED"})
end)
missionCommands.addCommand("Small blast near PLAYER (optional damage test)", root, function()
    blast(config.player, 0.2)
end)

local start = timer.getTime()
local stage = 1
local stages = {{20, 0.1}, {40, 1}, {60, 5}, {80, 20}}
local finished = false
timer.scheduleFunction(function(_, now)
    for _, name in ipairs(config.units) do P.sample(name, "periodic") end
    if stages[stage] and now - start >= stages[stage][1] then
        if not P.cancelled then
            for _, name in ipairs(config.targets) do blast(name, stages[stage][2]) end
        end
        stage = stage + 1
    end
    if not finished and now - start >= 100 then
        finished = true
        P.report()
        trigger.action.outText("Automatic damage test finished. Telemetry continues for landings, crashes and ejections. Results are in dcs.log (ESCALATION_AIRCRAFT_PROBE).", 30)
    end
    return now + 1
end, nil, start + 1)
world.addEventHandler(P)
log({kind = "start", version = 2, separate_log = logfile ~= nil})
for _, name in ipairs(config.units) do P.sample(name, "initial") end
trigger.action.outText("Maintenance probe: watch for 100 seconds. Only the dedicated AI targets receive automatic blasts. Use F10 > Aircraft maintenance probe for readings and optional player tests.", 30)
