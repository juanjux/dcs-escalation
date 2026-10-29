-- Fuel-managed AI BARCAP. Native BINGO is disabled only while on station.
-- A pushed native Refueling task suspends the mission orbit; completion resumes it.
-- The original absolute station end never changes. Failed refuelling uses the
-- generated home route, retaining normal airfield/carrier/despawn recovery.
EscalationBARCAP = {states={}}
local api = EscalationBARCAP
local BINGO_OPTION = 6
local MIN_STATION_LEFT = 20 * 60
local INTERVAL = 5
local TOPPED_OFF = .9
local MAX_TANKING = 15 * 60

local function living(name)
    local group = Group.getByName(name)
    if group and group:isExist() then return group end
end

local function sample(group, cfg)
    local lowest, point = math.huge, nil
    for _, unit in ipairs(group:getUnits() or {}) do
        if unit:isExist() then
            if unit.getPlayerName and unit:getPlayerName() then return nil end
            local ammunition = false
            lowest = math.min(lowest, unit:getFuel())
            point = point or unit:getPoint()
            -- Do not interrupt native Winchester RTB or damaged-aircraft recovery.
            if unit:getLife() < unit:getLife0() * .99 then return nil end
            for _, entry in ipairs(unit:getAmmo() or {}) do
                local desc = entry.desc or {}
                if entry.count > 0 and (
                    (cfg.gunfighter and desc.category == 0)
                    or (not cfg.gunfighter and desc.missileCategory == 1)
                ) then ammunition = true end
            end
            if not ammunition then return nil end
        end
    end
    if not point then return nil end
    return lowest, point
end

local function restore(group)
    pcall(function() group:getController():setOption(BINGO_OPTION, true) end)
end

local function rtb(state, group, reason)
    state.finished = true
    restore(group)
    local ok, err = pcall(function()
        local controller = group:getController()
        if state.cfg.unlimitedOutsideStation then
            controller:setCommand({id="SetUnlimitedFuel",params={value=true}})
        end
        local points = {}
        local located, position = pcall(function()
            for _, unit in ipairs(group:getUnits() or {}) do
                if unit:isExist() then return unit:getPoint() end
            end
        end)
        if located and position then
            points[1] = {
                x=position.x,y=position.z,alt=position.y,alt_type="BARO",
                speed=state.cfg.home[1].speed or 180,speed_locked=true,ETA_locked=false,
                type="Turning Point",action="Turning Point",
                task={id="ComboTask",params={tasks={}}},
            }
        end
        for _, point in ipairs(state.cfg.home) do points[#points+1]=point end
        controller:setTask({id="Mission",params={airborne=true,route={points=points}}})
    end)
    env.info("BARCAP FUEL| "..state.cfg.group.." RTB: "..reason)
    if not ok then env.warning("BARCAP FUEL| recovery route failed: "..tostring(err)) end
end

local function tanker(state, point, fuel, now)
    local best, distance
    for _, candidate in ipairs(state.cfg.tankers) do
        local group = living(candidate.group)
        if group and now >= candidate.startTime and now < candidate.endTime then
            for _, unit in ipairs(group:getUnits() or {}) do
                if unit:isExist() and unit:inAir() and unit:getFuel() > .1 then
                    local position = unit:getPoint()
                    local gap = math.sqrt((position.x-point.x)^2+(position.z-point.z)^2)
                    -- Cruise estimate plus 25% detour allowance and landing reserve.
                    local needed = gap * state.cfg.burnPerMeter * 1.25 + state.cfg.reserve
                    local trip = gap / 180 -- conservative cruise speed, m/s
                    if fuel > needed and now+trip+300 < candidate.endTime
                        and (not distance or gap < distance) then
                        best, distance = candidate, gap
                    end
                end
            end
        end
    end
    return best, distance
end

function api.done(name)
    local state = api.states[name]
    if not state or state.finished or timer.getTime() >= state.cfg.endTime then return true end
    local group = living(name)
    if not group then return true end
    local ok, fuel = pcall(sample, group, state.cfg)
    return not ok or fuel == nil or fuel >= TOPPED_OFF
end

local function update(state, now)
    if state.finished then return nil end
    local group = living(state.cfg.group)
    if not group then state.finished=true; return nil end
    if now >= state.cfg.endTime then
        if state.refuelling then rtb(state,group,"station ended during refuelling")
        else state.finished=true; restore(group) end
        return nil
    end
    if not state.active then
        if tonumber(trigger.misc.getUserFlag(state.cfg.flag)) ~= 1 then return now+INTERVAL end
        state.active = true
        group:getController():setOption(BINGO_OPTION, false)
    elseif tonumber(trigger.misc.getUserFlag(state.cfg.flag)) ~= 1 then
        state.finished=true; restore(group); return nil
    end
    local fuel, point = sample(group,state.cfg)
    if fuel == nil then
        -- Leave damage/Winchester decisions to DCS, not to the fuel monitor.
        state.finished=true; restore(group); return nil
    end
    if state.refuelling then
        if fuel >= TOPPED_OFF then
            state.refuelling = false
            env.info("BARCAP FUEL| "..state.cfg.group.." refuel complete; resuming orbit")
        elseif not living(state.tanker.group) or now >= state.tanker.endTime
            or fuel <= state.cfg.reserve or now >= state.deadline then
            rtb(state,group,"tanker lost, reserve reached or refuelling timeout")
            return nil
        end
    elseif fuel <= state.cfg.bingo then
        if state.cfg.endTime-now <= MIN_STATION_LEFT then
            rtb(state,group,"twenty minutes or less remain on station")
            return nil
        end
        local selected, distance = tanker(state,point,fuel,now)
        if not selected then rtb(state,group,"no reachable compatible tanker"); return nil end
        state.tanker, state.started, state.refuelling = selected, now, true
        state.deadline = now + (state.cfg.tankingSeconds or MAX_TANKING) + distance/180
        local quoted = string.format("%q",state.cfg.group)
        group:getController():pushTask({
            id="ControlledTask", params={
                task={id="Refueling",params={}},
                stopCondition={condition="return EscalationBARCAP.done("..quoted..")"},
            },
        })
        env.info("BARCAP FUEL| "..state.cfg.group.." refuelling; station end unchanged")
    end
    return now+INTERVAL
end

for _, cfg in ipairs(ESCALATION_BARCAP_REFUELLING or {}) do
    local state={cfg=cfg}
    api.states[cfg.group]=state
    timer.scheduleFunction(function(_,now)
        local ok, nextTime = pcall(update,state,now)
        if ok then return nextTime end
        env.warning("BARCAP FUEL| monitor failed: "..tostring(nextTime))
        local group=living(cfg.group)
        if group then rtb(state,group,"monitor failure") end
        return nil
    end,nil,timer.getTime()+INTERVAL)
end
