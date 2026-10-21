-- Track only campaign ships/buildings, not every object in the mission.
escalationPersistentDamage = {}
local entries = ESCALATION_PERSISTENT_DAMAGE or {}
local initialized = {}
local failed = {}
local previous = {}

local function lifeOf(object)
    local ok, life = pcall(function() return object:getLife() end)
    if not ok or type(life) ~= "number" or life ~= life or life >= 1e37 then return nil end
    return life
end

local function baseline(object, life)
    local ok, value = pcall(function() return object:getLife0() end)
    if ok and type(value) == "number" and value > 0 then return value end
    ok, value = pcall(function() return object:getDesc().life end)
    if ok and type(value) == "number" and value > 0 then return value end
    return life
end

local function restore(object, entry)
    local fraction = entry.health
    if fraction >= 1 or entry.native then return true end
    -- The same DCS mission command used by MOOSE UNIT:SetLife. No explosions:
    -- restoring old damage must not hit neighbours or create new kill events.
    local ok, result, detail = pcall(function()
        local percent = fraction * 100
        local code = string.format("a_unit_set_life_percentage(%.0f, %.9f)", object:getID(), percent)
        if type(a_unit_set_life_percentage) == "function" then
            a_unit_set_life_percentage(object:getID(), percent)
            return true
        end
        if not net or type(net.dostring_in) ~= "function" then
            return false, "native setter and net.dostring_in unavailable in mission sandbox"
        end
        local value, err = net.dostring_in("mission", code .. "; return 'applied'")
        return not err and value == "applied", err or tostring(value)
    end)
    if not ok or not result then
        env.warning("Escalation: cannot restore persistent health for " .. entry.name
            .. " (object " .. tostring(object:getID()) .. ", expected " .. tostring(fraction * 100)
            .. "%): " .. tostring(detail or result))
        trigger.action.outText("Escalation: DCS could not restore persistent ship/building health. See dcs.log.", 30)
        return false
    end
    return true
end

local function objectsFor(entry)
    if entry.x == nil then
        local object = Unit.getByName(entry.name) or StaticObject.getByName(entry.name)
        if not object then object = StaticObject.getByName(entry.name .. " object") end
        return object and {object} or {}
    end
    local objects = {}
    local volume = {id = world.VolumeType.SPHERE, params = {
        point = {x = entry.x, y = land.getHeight({x = entry.x, y = entry.z}), z = entry.z}, radius = 30,
    }}
    world.searchObjects(Object.Category.SCENERY, volume, function(object)
        local life = lifeOf(object)
        if life and life > 0 then
            -- Match the existing scenery death resolver: nearest objective wins.
            local zone = scenery_zone_for(object)
            if zone and zone.name == entry.name then objects[#objects + 1] = object end
        end
        return true
    end)
    return objects
end

local function initialize(entry)
    local objects = objectsFor(entry)
    if #objects == 0 then return end
    local state = {}
    for _, object in ipairs(objects) do
        local life = lifeOf(object)
        if life and life > 0 then
            local maximum = baseline(object, life)
            if maximum > 0 and restore(object, entry) then
                state[#state + 1] = {object = object, maximum = maximum, expected = entry.health}
            end
        end
    end
    if #state > 0 then initialized[entry.name] = state
    else failed[entry.name] = true end
end

function escalationPersistentDamage.snapshot()
    local health = {}
    for name, state in pairs(initialized) do
        local fraction = 1
        local readable = true
        for _, item in ipairs(state) do
            local life = lifeOf(item.object)
            if life ~= nil then
                local current = math.max(0, life / item.maximum)
                if not item.checked then
                    item.checked = true
                    if current > item.expected + math.max(0.01, 1 / item.maximum) then
                        env.warning("Escalation: DCS did not apply persistent health for " .. name)
                        trigger.action.outText("Escalation: DCS did not apply persistent health for " .. name .. ". See dcs.log.", 30)
                        failed[name] = true
                    end
                end
                fraction = math.min(fraction, current)
            else
                local exists, value = pcall(function() return item.object:isExist() end)
                if exists and not value then fraction = 0 end
                if not exists or value then readable = false end
            end
        end
        if failed[name] then initialized[name] = nil
        elseif readable then health[name] = math.min(1, fraction)
        elseif previous[name] ~= nil then health[name] = previous[name] end
    end
    return health
end

function escalationPersistentDamage.poll()
    local current = escalationPersistentDamage.snapshot()
    for name, fraction in pairs(current) do
        if previous[name] ~= fraction then dirty_state = true end
    end
    previous = current
end

local function start(_, now)
    local pending = false
    for _, entry in ipairs(entries) do
        if not initialized[entry.name] and not failed[entry.name] then
            initialize(entry)
            pending = true
        end
    end
    -- Retry late-activated objects briefly; never restore an initialized object twice.
    if pending and now < 60 then return now + 1 end
end
timer.scheduleFunction(start, nil, timer.getTime() + 1)
