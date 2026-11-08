-- Selective missile defence. Only a missile's engine-reported fixed-wing target
-- group receives Evade Fire; unrelated groups retain Passive Defense.
-- Accepted setOption calls are logged, not proof of a native evasive manoeuvre.
-- One bounded polling loop follows unresolved and retargeting missiles. Resolved
-- ground/ship shots and known non-missile weapons do not enter that loop.

local config = dcsRetribution and dcsRetribution.plugins
    and dcsRetribution.plugins.ai_reaction or {}
local DEBUG = config.DEBUG == true
local OPT = AI.Option.Air.id.REACTION_ON_THREAT
local PASS, EVADE = 1, 2
local INTERVAL, POLL_BUDGET = 0.25, 64
local RETRY_INTERVAL, EVADE_REASSERT = 1, 5
local BASELINE_INTERVAL, REASSERT_EVERY = 10, 6
local SUMMARY_INTERVAL = 60
local tracks, byWeapon, groups = {}, {}, {}
local cursor, sweep = 1, 0
local nextSummary = timer.getTime() + SUMMARY_INTERVAL
local logWindow, logCount, warningCount, nextScreen = -1, 0, 0, 0
local stats = {
    shots=0, ignored=0, targetReads=0, unresolved=0, retargets=0,
    optionErrors=0, targetErrors=0, existenceErrors=0,
    evadeWrites=0, passiveWrites=0, suppressed=0, pollErrors=0,
}

-- Routine transitions and errors are useful without DEBUG, but bounded during salvos.
local function log(kind, message, now, warning)
    local window = math.floor(now / 10)
    if window ~= logWindow then logWindow, logCount, warningCount = window, 0, 0 end
    if (warning and warningCount >= 10) or (not warning and logCount >= 30) then
        stats.suppressed = stats.suppressed + 1; return
    end
    if warning then warningCount = warningCount + 1 else logCount = logCount + 1 end
    local text = "AIReaction| " .. kind .. " t=" .. tostring(now) .. " " .. message
    local writer = warning and env.warning or env.info
    writer(text)
end

local function debug(message, now)
    if not DEBUG then return end
    log("DEBUG", message, now)
    if now >= nextScreen then
        trigger.action.outText("AIReaction: " .. message, 8)
        nextScreen = now + 15
    end
end

local function groupState(group, name)
    local state = groups[name]
    if not state then
        state = {name=name, group=group, count=0, nextWrite=0, nextWarning=0}
        groups[name] = state
    else
        state.group = group
    end
    return state
end

local function apply(state, now)
    local desired = state.count > 0 and EVADE or PASS
    if now < state.nextWrite then return state.applied == desired end
    if state.applied == desired and desired == PASS then return true end
    local ok, result = pcall(function()
        local controller = state.group:getController()
        if not controller then return false end
        return controller:setOption(OPT, desired)
    end)
    if not ok or result == false then
        stats.optionErrors = stats.optionErrors + 1
        state.nextWrite = now + RETRY_INTERVAL
        if now >= state.nextWarning then
            log("OPTION_FAILED", string.format("group=%q requested=%d error=%q",
                state.name, desired, ok and "no controller or rejected" or tostring(result)),
                now, true)
            state.nextWarning = now + 10
        end
        return false
    end
    local changed = state.applied ~= desired
    state.applied = desired
    state.nextWrite = desired == EVADE and now + EVADE_REASSERT or math.huge
    if desired == EVADE then
        stats.evadeWrites = stats.evadeWrites + 1
        if changed then
            log("COMMAND_ACCEPTED", string.format("group=%q option=EVADE missiles=%d weapon=%q",
                state.name, state.count, state.weapon or "?"), now)
            debug("Evade Fire requested for " .. state.name, now)
        end
    else
        stats.passiveWrites = stats.passiveWrites + 1
        if state.reportClear then
            log("COMMAND_ACCEPTED", string.format("group=%q option=PASSIVE missiles=0",
                state.name), now)
            state.reportClear = nil
        end
    end
    return true
end

local function release(name, now)
    local state = name and groups[name]
    if not state then return end
    state.count = math.max(0, state.count - 1)
    if state.count == 0 then
        state.nextWrite = now
        state.reportClear = true
        apply(state, now)
    end
end

local function targetWarning(record, phase, now)
    stats.targetErrors = stats.targetErrors + 1
    if now >= (record.nextWarning or 0) then
        log("TARGET_QUERY_FAILED", string.format("weapon=%q phase=%s", record.name, phase), now, true)
        record.nextWarning = now + 10
    end
end

local function targetOf(record, now)
    stats.targetReads = stats.targetReads + 1
    local ok, target = pcall(function() return record.weapon:getTarget() end)
    if not ok then
        targetWarning(record, "getTarget", now)
        return "unknown"
    end
    if not target then return "unknown" end
    if Object and Object.getCategory and Object.Category then
        local okObject, category = pcall(Object.getCategory, target)
        if okObject and category ~= nil and category ~= Object.Category.UNIT then return "other" end
    end
    local okGroup, group = pcall(function() return target:getGroup() end)
    if not okGroup then targetWarning(record, "getGroup", now); return "unknown" end
    if not group then return "unknown" end
    local okCategory, category = pcall(function() return group:getCategory() end)
    if not okCategory then targetWarning(record, "getCategory", now); return "unknown" end
    if category == nil then return "unknown" end
    if category ~= Group.Category.AIRPLANE then return "other" end
    local okName, name = pcall(function() return group:getName() end)
    if not okName then targetWarning(record, "getName", now); return "unknown" end
    if not name then return "unknown" end
    return "air", group, name
end

local function poll(record, now)
    local status, group, name = targetOf(record, now)
    if status == "other" then return false end
    if status == "unknown" then
        -- A temporary seeker/target gap must not cancel an existing defensive order.
        if not record.groupName then stats.unresolved = stats.unresolved + 1 end
        return true
    end
    local state = groupState(group, name)
    state.weapon = record.name
    if record.groupName ~= name then
        local previous = record.groupName
        record.groupName = name
        state.count = state.count + 1
        state.reportClear = nil
        if state.count == 1 then state.nextWrite = now end
        log("TARGET_RESOLVED", string.format("weapon=%q group=%q missiles=%d",
            record.name, name, state.count), now)
        apply(state, now)
        if previous then
            stats.retargets = stats.retargets + 1
            log("RETARGET", string.format("weapon=%q from=%q to=%q",
                record.name, previous, name), now)
            release(previous, now)
        end
    else
        apply(state, now)
    end
    return true
end

local function removeAt(index, now)
    local record = tracks[index]
    byWeapon[record.weapon] = nil
    release(record.groupName, now)
    tracks[index] = tracks[#tracks]
    tracks[#tracks] = nil
end

local function summary(now)
    local pending, evading = 0, 0
    for _, record in ipairs(tracks) do
        if not record.groupName then pending = pending + 1 end
    end
    for _, state in pairs(groups) do
        if state.count > 0 then evading = evading + 1 end
    end
    log("STATS", string.format(
        "tracked=%d unresolved=%d threatenedGroups=%d shots=%d ignored=%d targetReads=%d "
        .. "retargets=%d optionErrors=%d targetErrors=%d existenceErrors=%d "
        .. "evadeWrites=%d passiveWrites=%d pollErrors=%d suppressed=%d",
        #tracks, pending, evading, stats.shots, stats.ignored, stats.targetReads,
        stats.retargets, stats.optionErrors, stats.targetErrors, stats.existenceErrors,
        stats.evadeWrites, stats.passiveWrites,
        stats.pollErrors, stats.suppressed), now)
end

local function watch(_, now)
    local budget = math.min(#tracks, POLL_BUDGET)
    for _ = 1, budget do
        if cursor > #tracks then cursor = 1 end
        local record = tracks[cursor]
        local exists, live = pcall(function() return record.weapon:isExist() end)
        local keep = exists and live
        if not exists then
            stats.existenceErrors = stats.existenceErrors + 1
            record.existenceErrors = (record.existenceErrors or 0) + 1
            keep = record.existenceErrors < 4
            if record.existenceErrors == 1 or not keep then
                log(keep and "MISSILE_QUERY_FAILED" or "TRACKING_LOST",
                    string.format("weapon=%q group=%q existenceChecksFailed=%d",
                        record.name, record.groupName or "?", record.existenceErrors), now, true)
            end
        else
            record.existenceErrors = 0
        end
        if keep and exists then
            local ok, result = pcall(poll, record, now)
            if ok then
                keep = result
            else
                stats.pollErrors = stats.pollErrors + 1
                if now >= (record.nextWarning or 0) then
                    log("POLL_FAILED", tostring(result), now, true)
                    record.nextWarning = now + 10
                end
            end
        end
        if keep then cursor = cursor + 1 else removeAt(cursor, now) end
    end
    for name, state in pairs(groups) do
        local ok, live = pcall(function() return state.group:isExist() end)
        if ok and not live and state.count == 0 then
            groups[name] = nil
        elseif not ok or live then
            apply(state, now)
        end
    end
    if now >= nextSummary then
        summary(now)
        nextSummary = now + SUMMARY_INTERVAL
    end
    return now + INTERVAL
end

local function baseline(_, now)
    sweep = sweep + 1
    local reassert = sweep % REASSERT_EVERY == 0
    for _, side in ipairs({coalition.side.RED, coalition.side.BLUE}) do
        local ok, available = pcall(coalition.getGroups, side, Group.Category.AIRPLANE)
        if ok and available then
            for _, group in pairs(available) do
                local okName, name = pcall(function() return group:getName() end)
                if okName and name then
                    local state = groupState(group, name)
                    if state.count == 0 then
                        if reassert then state.applied = nil; state.nextWrite = now end
                        apply(state, now)
                    end
                end
            end
        end
    end
    return now + BASELINE_INTERVAL
end

local handler = {}
function handler:onEvent(event)
    if not event or event.id ~= world.event.S_EVENT_SHOT or not event.weapon then return end
    local weapon, now = event.weapon, timer.getTime()
    if byWeapon[weapon] then return end
    stats.shots = stats.shots + 1
    local okDesc, desc = pcall(function() return weapon:getDesc() end)
    local missile = Weapon and Weapon.Category and Weapon.Category.MISSILE or 1
    if okDesc and desc and desc.category ~= nil and desc.category ~= missile then
        stats.ignored = stats.ignored + 1
        return
    end
    local okName, name = pcall(function() return weapon:getTypeName() end)
    local record = {weapon=weapon, name=okName and name or "?"}
    local ok, keep = pcall(poll, record, now)
    if not ok then
        stats.pollErrors = stats.pollErrors + 1
        log("POLL_FAILED", tostring(keep), now, true)
        keep = true
    end
    if keep then
        tracks[#tracks + 1] = record
        byWeapon[weapon] = record
    else
        stats.ignored = stats.ignored + 1
    end
end

world.addEventHandler(handler)
timer.scheduleFunction(baseline, nil, timer.getTime() + 2)
timer.scheduleFunction(watch, nil, timer.getTime() + INTERVAL)
env.info("AIReaction| Selective missile tracking loaded (DEBUG=" .. tostring(DEBUG)
    .. ", interval=" .. INTERVAL .. ", budget=" .. POLL_BUDGET .. ")")
