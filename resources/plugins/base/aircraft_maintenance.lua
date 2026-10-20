-- Observe only campaign aircraft seeded by the generator. Never changes DCS life.
EscalationAircraftMaintenance = {states = {}, previous = {}, places = {}}
local M = EscalationAircraftMaintenance
local config = ESCALATION_AIRCRAFT_MAINTENANCE
aircraft_damage_state = {}
aircraft_damage_mission_id = config.mission_id

local function read(object, method)
    if not object then return nil end
    local ok, value = pcall(function() return object[method](object) end)
    if ok then return value end
end

local function finite(value)
    return type(value) == "number" and value == value and math.abs(value) < math.huge
end

for _, name in ipairs(config.units) do
    local state = {unit = name, was_airborne = false}
    M.states[name] = state
    aircraft_damage_state[#aircraft_damage_state + 1] = state
end

function M.sample(name, object)
    local state = M.states[name]
    object = object or Unit.getByName(name)
    if not state or not object or read(object, "isExist") ~= true then return end
    if state.player_left and state.recovered then return end
    local oldHealth, oldAir, oldRecovered = state.health, state.in_air, state.recovered
    local now = timer.getTime()
    local life, maximum = read(object, "getLife"), read(object, "getLife0")
    local health
    if finite(life) and finite(maximum) and maximum > 0 and life >= 0 then
        health = math.max(0, math.min(1, life / maximum))
    end
    state.health = health
    state.sample_time = now
    if health and health > 0 and health < 1 and not state.first_damage_time then
        state.first_damage_time = now
        state.pre_crash_health = health
    end
    -- Do not overwrite prior damage with the final impact's zero life reading.
    if health and health > 0 and health < 1 and state.first_damage_time
            and now - state.first_damage_time >= 2 and not state.crash_time then
        state.pre_crash_health = health
    end
    local inAir = read(object, "inAir")
    local previous = M.previous[name]
    if inAir == true then
        state.was_airborne = true
        state.ground_since, state.stopped_since = nil, nil
        state.recovered = false
        state.landing_time, state.landing_place, state.landing_name = nil, nil, nil
    elseif inAir == false and state.was_airborne then
        if previous == true then state.ground_since = now end
    end
    M.previous[name] = inAir
    state.in_air = inAir
    local point = read(object, "getPoint")
    if point then state.x, state.z = point.x, point.z end
    local velocity = read(object, "getVelocity")
    local speed
    if velocity and finite(velocity.x) and finite(velocity.y) and finite(velocity.z) then
        speed = math.sqrt(velocity.x^2 + velocity.y^2 + velocity.z^2)
        local place = M.places[name]
        if place then
            local reference = read(place.object, "getPoint")
            if reference and place.point and now > place.time then
                local dt = now - place.time
                local dx = velocity.x - (reference.x - place.point.x) / dt
                local dy = velocity.y - (reference.y - place.point.y) / dt
                local dz = velocity.z - (reference.z - place.point.z) / dt
                speed = math.sqrt(dx^2 + dy^2 + dz^2)
            end
            place.point, place.time = reference, now
        end
    end
    if inAir == false and speed and speed < 1 and state.was_airborne then
        state.stopped_since = state.stopped_since or now
    else
        state.stopped_since = nil
    end
    -- A native LAND event plus a surviving, stationary aircraft is evidence.
    -- A disappeared unit, an airborne change or an F10 marker alone is not.
    if state.landing_time and state.stopped_since and now - state.stopped_since >= 30
            and finite(life) and life > 0 and not state.crash_time
            and not state.ejected and not state.killed then
        state.recovered = true
    end
    if oldHealth ~= state.health or oldAir ~= state.in_air or oldRecovered ~= state.recovered then
        dirty_state = true
    end
end

function M.poll()
    for _, name in ipairs(config.units) do M.sample(name) end
end

local observedEvents = {}
for _, name in ipairs({"HIT", "KILL", "LAND", "EJECTION", "CRASH", "DEAD",
        "UNIT_LOST", "PLAYER_LEAVE_UNIT", "TAKEOFF"}) do
    local id = world.event["S_EVENT_" .. name]
    if id then observedEvents[id] = true end
end

function M:onEvent(event)
    local id = event.id
    if not observedEvents[id] then return end
    local targetEvent = id == world.event.S_EVENT_KILL or id == world.event.S_EVENT_HIT
    local object
    if targetEvent then object = event.target else object = event.initiator end
    local name = read(object, "getName")
    local state = M.states[name]
    if not state then return end
    dirty_state = true
    local now = event.time or timer.getTime()
    if id == world.event.S_EVENT_EJECTION then
        state.ejected, state.recovered = true, false
    elseif id == world.event.S_EVENT_KILL then
        -- The base debrief treats a weapon whose type is the attacker's own
        -- unit type as a collision, not a weapon kill. Keep that distinction.
        local weapon = read(event.weapon, "getTypeName")
        local attacker = read(event.initiator, "getTypeName")
        if weapon and weapon == attacker then
            state.crash_time = state.crash_time or now
            state.recovered = false
        else
            state.killed, state.recovered = true, false
        end
    elseif id == world.event.S_EVENT_CRASH or id == world.event.S_EVENT_DEAD
            or id == world.event.S_EVENT_UNIT_LOST then
        -- Preserve a confirmed return if DCS removes a parked player after the
        -- slot is left. The base plugin independently guards these despawns.
        if not state.player_left or not state.recovered then
            state.crash_time = state.crash_time or now
            state.recovered = false
        end
    elseif id == world.event.S_EVENT_PLAYER_LEAVE_UNIT then
        state.player_left = true
    elseif id == world.event.S_EVENT_LAND then
        state.landing_time = now
        state.landing_place = read(event.place, "getID")
        state.landing_name = read(event.place, "getName")
        M.places[name] = {object = event.place, time = timer.getTime(),
            point = read(event.place, "getPoint")}
    elseif id == world.event.S_EVENT_HIT then
        state.hit = true
    end
    M.sample(name, object)
end

world.addEventHandler(M)
M.poll()
timer.scheduleFunction(function(_, now)
    M.poll()
    return now + 1
end, nil, timer.getTime() + 1)
