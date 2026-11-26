-- Only observes flights selected as prerequisites. DCS mission triggers score
-- the authored objectives independently, including kills by another flight.
EscalationFlightOutcomes = {}
do
    local flights, byUnit = {}, {}

    local function hasWorkRemaining(unit)
        if not unit:inAir() then return true end
        local inventory = unit:getAmmo()
        if not inventory then return true end
        for _, store in ipairs(inventory) do
            if store.count > 0 and
                EscalationGroundStores.isGroundWeapon(store.desc or {}) ~= false then
                -- An unknown store or unavailable inventory is not proof of Winchester.
                return true
            end
        end
        return false
    end

    function EscalationFlightOutcomes.returning(groupName)
        if not next(flights) then return end
        local group = Group.getByName(groupName)
        if not group or not group:isExist() then return end
        for _, unit in ipairs(group:getUnits() or {}) do
            local flight = byUnit[unit:getName()]
            if flight then flight.returned = true end
        end
    end

    local handler = {}
    function handler:onEvent(event)
        local events = world.event
        local shot = event.id == events.S_EVENT_SHOT
        local finished = event.id == events.S_EVENT_LAND or event.id == events.S_EVENT_DEAD
            or event.id == events.S_EVENT_CRASH or event.id == events.S_EVENT_UNIT_LOST
            or event.id == events.S_EVENT_AI_ABORT_MISSION
        if not shot and not finished then return end
        local actor = event.initiator
        if not actor or not actor.getName then return end
        local ok, name = pcall(actor.getName, actor)
        local flight = ok and byUnit[name]
        if not flight then return end
        flight.seen[name] = true
        if shot and event.weapon then
            local okDesc, desc = pcall(event.weapon.getDesc, event.weapon)
            if okDesc and desc and EscalationGroundStores.isGroundWeapon(desc) ~= false then
                table.insert(flight.pending, event.weapon)
            end
        elseif finished then
            flight.finished[name] = true
        end
    end

    local function ended(flight, key)
        for i = #flight.pending, 1, -1 do
            local weapon = flight.pending[i]
            local ok, exists = pcall(weapon.isExist, weapon)
            if ok and exists then return false end
            table.remove(flight.pending, i)
        end
        if flight.returned or trigger.misc.getUserFlag("prerequisite-return-" .. key) == 1 then
            return true
        end
        local active = false
        for _, name in ipairs(flight.members) do
            if not flight.finished[name] then
                local unit = Unit.getByName(name)
                if unit and unit:isExist() and unit:isActive() then
                    flight.seen[name] = true
                    if hasWorkRemaining(unit) then active = true end
                elseif not flight.seen[name] then
                    -- A flight may be late activated.
                    active = true
                end
            end
        end
        return not active
    end

    local function tick(_, now)
        for key, flight in pairs(flights) do
            local outcome = "scenario-outcome-" .. key
            if trigger.misc.getUserFlag(outcome) == 0 then
                if ended(flight, key) then
                    -- Let native objective triggers observe the same impact tick first.
                    if flight.ending then trigger.action.setUserFlag(outcome, 2) end
                    flight.ending = true
                else
                    flight.ending = false
                end
            end
            if trigger.misc.getUserFlag(outcome) ~= 0 then
                for _, name in ipairs(flight.members) do byUnit[name] = nil end
                flights[key] = nil
            end
        end
        if next(flights) then return now + 3 end
        world.removeEventHandler(handler)
    end

    function EscalationFlightOutcomes.start(config)
        for key, names in pairs(config) do
            local flight = {members = names, pending = {}, seen = {}, finished = {}}
            flights[key] = flight
            for _, name in ipairs(names) do byUnit[name] = flight end
        end
        world.addEventHandler(handler)
        timer.scheduleFunction(tick, nil, timer.getTime() + 1)
    end
end
