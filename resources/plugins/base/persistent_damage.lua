-- Track only campaign ships/buildings, not every object in the mission.
escalationPersistentDamage = {}
local entries = ESCALATION_PERSISTENT_DAMAGE or {}
local initialized = {}
local failed = {}
local previous = {}
local restoring = {}
local BUILDING_TOLERANCE = 0.020001

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
    if fraction >= 1 or entry.native or entry.building then return true end
    -- Legacy ship missions can still use the native command through a bridge.
    local ok, result, detail = pcall(function()
        if entry.unsupported then
            return false, "partial terrain-scenery health restoration is unsupported"
        end
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

local function failBuilding(entry, reason)
    env.warning("Escalation: cannot restore persistent building health for " .. entry.name .. ": " .. tostring(reason))
    trigger.action.outText("Escalation: could not restore building health for " .. entry.name .. ". See dcs.log.", 30)
    failed[entry.name] = true
    restoring[entry.name] = nil
end

local function boundingRadius(object)
    local ok, box = pcall(function() return object:getDesc().box end)
    if not ok or type(box) ~= "table" or type(box.min) ~= "table" or type(box.max) ~= "table" then return nil end
    local squared = 0
    for _, axis in ipairs({"x", "y", "z"}) do
        local low, high = box.min[axis], box.max[axis]
        if type(low) ~= "number" or type(high) ~= "number" or low ~= low or high ~= high
            or math.abs(low) == math.huge or math.abs(high) == math.huge or low > high then return nil end
        -- A sphere enclosing the entire local box remains conservative at any attitude.
        local extent = math.max(math.abs(low), math.abs(high))
        squared = squared + extent * extent
    end
    return math.sqrt(squared)
end

local function safeBuildingPulse(item)
    local point = item.object:getPoint()
    local safe = true
    -- Very close objects and fragile neighbours were not covered by the native
    -- pulse controls. Leave their saved health unchanged instead of risking them.
    local volume = {id = world.VolumeType.SPHERE, params = {point = point, radius = 10}}
    for _, category in ipairs({Object.Category.UNIT, Object.Category.STATIC, Object.Category.SCENERY}) do
        world.searchObjects(category, volume, function(other)
            if other:getID() ~= item.object:getID() then
                local life = lifeOf(other)
                if life and life > 0 then
                    local p = other:getPoint()
                    local distance = (p.x - point.x)^2 + (p.z - point.z)^2
                    if distance ~= distance or distance == math.huge or distance < 25 then safe = false
                    elseif baseline(other, life) < item.maximum / 4 then
                        -- Native searches can return objects well outside the query sphere.
                        -- Discard a fragile candidate only when its entire bounding sphere
                        -- is outside the protected area. Unknown bounds still block pulses.
                        local radius = boundingRadius(other)
                        if radius == nil or distance <= (10 + radius)^2 then safe = false end
                    end
                end
            end
            return safe
        end)
        if not safe then return false end
    end
    return true
end

local function advanceBuilding(entry)
    local state = restoring[entry.name]
    local pulsed = false
    for _, item in ipairs(state) do
        local life = lifeOf(item.object)
        if life == nil then
            failBuilding(entry, "life query unavailable during initialization")
            return
        end
        if item.remaining > 0 and life / item.maximum > entry.health + BUILDING_TOLERANCE then
            local ok, reason = pcall(function()
                if not safeBuildingPulse(item) then error("nearby object is too close or too fragile") end
                local p = item.object:getPoint()
                trigger.action.explosion({x = p.x, y = p.y + 0.25, z = p.z}, item.power)
            end)
            if not ok then failBuilding(entry, reason); return end
            item.remaining = item.remaining - 1
            pulsed = true
        else item.remaining = 0 end
    end
    -- Read on the next tick after the final pulse, never its pre-impact value.
    if pulsed then return end
    for _, item in ipairs(state) do
        if lifeOf(item.object) / item.maximum > entry.health + BUILDING_TOLERANCE then
            failBuilding(entry, "DCS did not apply the initial damage")
            return
        end
        item.checked = true
    end
    initialized[entry.name] = state
    restoring[entry.name] = nil
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
                local item = {object = object, maximum = maximum, expected = entry.health}
                if entry.building then
                    local damage = math.max(0, life / maximum - entry.health)
                    -- DCS ignores individual hits below 2% of the original life.
                    -- Balanced small pulses avoid the collateral of a large hit.
                    item.remaining = damage >= 0.02 and math.max(1, math.floor(damage / 0.021)) or 0
                    item.power = item.remaining > 0 and damage * maximum / (item.remaining * 2.5) or 0
                    item.checked = true
                end
                state[#state + 1] = item
            end
        end
    end
    if #state > 0 and entry.building and entry.health < 0.98 then restoring[entry.name] = state
    elseif #state > 0 then initialized[entry.name] = state
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
    local missing = false
    for _, entry in ipairs(entries) do
        if not initialized[entry.name] and not failed[entry.name] then
            if not restoring[entry.name] then initialize(entry) end
            if restoring[entry.name] then
                advanceBuilding(entry)
                pending = pending or restoring[entry.name] ~= nil
            elseif not initialized[entry.name] and not failed[entry.name] then missing = true end
        end
    end
    -- Retry late-activated objects briefly; never restore an initialized object twice.
    if pending or (missing and now < 60) then return now + 2 end
end
timer.scheduleFunction(start, nil, timer.getTime() + 1)
