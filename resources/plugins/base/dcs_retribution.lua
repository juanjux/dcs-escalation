-- the state.json file will be updated according to this schedule and on mission end
local WRITESTATE_SCHEDULE_IN_SECONDS = 15

logger = mist.Logger:new("DCSRetribution", "info")
logger:info("Check that json.lua is loaded : json = "..tostring(json))

crash_events = {} -- killed aircraft will be added via S_EVENT_CRASH event
dead_events = {} -- killed units will be added via S_EVENT_DEAD event
unit_lost_events = {} -- killed units will be added via S_EVENT_UNIT_LOST
kill_events = {} -- killed units will be added via S_EVENT_KILL
kill_details = {} -- structured S_EVENT_KILL records {target, initiator, weapon} for the UI feed
hit_details = {} -- structured S_EVENT_HIT records, one per attacking aircraft per target, for pilot experience
hit_seen = {} -- initiator -> {target -> true}, so a strafing pass is recorded once and not once per round
HIT_DETAIL_LIMIT = 2000 -- a hard stop on the table above; state.json is written every 15 s
base_capture_events = {}
destroyed_objects_positions = {} -- will be added via S_EVENT_DEAD event
took_off = {}   -- unit name -> true (S_EVENT_TAKEOFF); a ground-start unit absent here was destroyed parked
death_time = {} -- unit name -> first death-event mission time (s), for indirect-kill timing
cruise_missiles_state = {} -- cruisemissiles plugin appends/updates {group=, fired=} per ship group that launched; Python debits the campaign magazine at the turn boundary
naval_magazines_state = {} -- navalmagazines plugin appends/updates {group=, fired=} per naval group that fired ANTI-SHIP missiles (a disjoint weapon set from cruise_missiles_state); Python debits the campaign magazine at the turn boundary
mission_log_events = {} -- missionlog plugin appends one flat record per event (kill, loss, crash, intercept...); Python renders the mission chronicle from it. Contiguous integer array, capped by the plugin: see the numeric-key warning further down.
mission_ended = false
dirty_state = false -- Track if state has changed and needs writing

-- Scenery objectives: credit a map-object death to the building it belongs to.
--
-- DCS reports a scenery death with the object's numeric id rather than a name,
-- so the debriefing, which resolves scenery by trigger-zone name, discarded
-- every one. The MapObjectIsDead trigger meant to catch this cannot fire: it
-- needs EVERY map object in the zone dead, and those polygons hold scenery that
-- cannot be destroyed (WOODPILE_01 reports a life of 1e38).
--
-- Deaths are matched to the nearest objective instead. The radius is measured:
-- hits that destroyed the objective landed within 29 m of its zone, collateral
-- from 31 m out.
SCENERY_MATCH_RADIUS = 30

-- Some map objects have no damage model at all. DCS reports a life of 1e38 for
-- them and they never die, so an objective standing on one could never be
-- completed however much ordnance it absorbed. For those the direct hit is the
-- destruction, because nothing else is ever coming.
--
-- Measured on Kola: the four submarines of the CHIMAERA objective at Gadzhiyevo
-- took eight JDAM, every one matching within 2 m of its zone, without losing a
-- point of life. The piers 200 m away, which do have a damage model, lost life
-- to the same bombs.
SCENERY_INDESTRUCTIBLE_LIFE = 1e37

scenery_zone_reported = {} -- zone name -> true, so a building is only counted once
scenery_zones_primed = false

-- Objectives that were already destroyed on previous turns count as reported, so
-- they are never scored twice. They stay in the list all the same: the
-- destruction zone that replays their rubble at mission start kills their
-- scenery, and those deaths have to land on them rather than on a live
-- neighbour.
local function prime_scenery_zones()
    if scenery_zones_primed or type(RETRIBUTION_SCENERY_ZONES) ~= "table" then
        return
    end
    scenery_zones_primed = true
    local dead = 0
    for _, zone in ipairs(RETRIBUTION_SCENERY_ZONES) do
        if zone.dead then
            scenery_zone_reported[zone.name] = true
            dead = dead + 1
        end
    end
    logger:info(string.format(
        "Scenery objectives: %d known, %d already destroyed, match radius %d m",
        #RETRIBUTION_SCENERY_ZONES, dead, SCENERY_MATCH_RADIUS))
end

-- Nearest objective zone to a dead scenery object, or nil if none is close
-- enough. Reads RETRIBUTION_SCENERY_ZONES lazily so it does not care whether the
-- generator seeded it before or after this script loaded.
function scenery_zone_for(obj)
    if type(RETRIBUTION_SCENERY_ZONES) ~= "table" then
        return nil, nil
    end
    prime_scenery_zones()
    local point
    if not pcall(function() point = obj:getPoint() end) or point == nil then
        return nil, nil
    end
    local best, best_distance = nil, nil
    for _, zone in ipairs(RETRIBUTION_SCENERY_ZONES) do
        local dx, dy = point.x - zone.x, point.z - zone.y
        local distance = math.sqrt(dx * dx + dy * dy)
        if best_distance == nil or distance < best_distance then
            best, best_distance = zone, distance
        end
    end
    return best, best_distance
end

-- Player-despawn loss guard (414th): a player dropping to spectator — or the
-- mission ending with players still airborne — makes DCS fire S_EVENT_CRASH/DEAD
-- for that aircraft, which would otherwise be counted as a combat loss and attrit
-- the airframe even though the pilot survived (2026-06-20: GERBIL F-14s recorded
-- lost while alive at mission end). We mark a unit when its player LEAVES the seat
-- and suppress the despawn crash/dead/lost that immediately follows. A real
-- shootdown fires the crash/dead while the player is still in the seat (BEFORE the
-- leave), so it is still recorded. Ejections are tracked separately and NEVER
-- suppressed — an ejection is a real loss of the airframe.
player_left_units = {} -- unit name -> mission time of S_EVENT_PLAYER_LEAVE_UNIT
ejected_units = {}     -- unit name -> true; ejected = real loss, never suppress
PLAYER_LEAVE_GRACE_S = 5 -- a crash within this long after a leave = the despawn

-- Credit the objective standing where this scenery object is, at most once.
-- Only the credit is logged: a mission destroys hundreds of unrelated buildings
-- and logging the misses drowns the log.
local function credit_scenery_zone(obj, note, killer, weapon)
    local zone, distance = scenery_zone_for(obj)
    if zone == nil or distance > SCENERY_MATCH_RADIUS
            or scenery_zone_reported[zone.name] then
        return false
    end
    scenery_zone_reported[zone.name] = true
    dead_events[#dead_events + 1] = zone.name
    if killer ~= nil then
        -- An indestructible objective never fires a kill of its own, so this is
        -- the only chance to record who did it.
        local detail = { ["target"] = zone.name }
        pcall(function() detail["initiator"] = killer:getName() end)
        pcall(function() detail["initiator_type"] = killer:getTypeName() end)
        pcall(function()
            local pn = killer:getPlayerName()
            if pn and pn ~= "" then detail["initiator_player"] = pn end
        end)
        if weapon ~= nil then
            pcall(function() detail["weapon"] = weapon:getTypeName() end)
        end
        kill_details[#kill_details + 1] = detail
    end
    logger:info(string.format("Objective destroyed: '%s' (%.0f m from the hit%s)",
        zone.name, distance, note or ""))
    return true
end

-- Scenery that can never die, so a hit on it has to be the destruction.
local function is_indestructible(obj)
    local life
    if not pcall(function() life = obj:getLife() end) then
        return false
    end
    return life ~= nil and life >= SCENERY_INDESTRUCTIBLE_LIFE
end

local function ends_with(str, ending)
   return ending == "" or str:sub(-#ending) == ending
end

local function messageAll(message)
    local msg = {}
    msg.text = message
    msg.displayTime = 25
    msg.msgFor = {coa = {'all'}}
    mist.message.add(msg)
end

-- ── Freeze diagnostics ──────────────────────────────────────────────────────
-- Some missions stall for minutes shortly after start, then recover. Several
-- things could be to blame (an event storm, this state export, another plugin, or
-- the engine itself), so measure instead of guessing. A heartbeat samples the wall
-- clock against mission time: while the sim is stalled no scheduled function runs,
-- so the first beat afterwards sees far more wall-clock seconds than mission
-- seconds. It then reports what THIS script did during that gap, which is what
-- tells the two cases apart: if the events/export numbers are ~0 the stall came
-- from outside these scripts. Cheap: two counters per event, one line every few
-- seconds. Set DIAG_ENABLED = false to silence it.
DIAG_ENABLED = true
DIAG_HEARTBEAT_S = 2   -- mission-time seconds between samples
DIAG_STALL_WARN_S = 5  -- wall-clock seconds in one beat that count as a stall

diag = {
    events = 0,           -- events handled since the last sample
    event_time = 0.0,     -- seconds spent inside our handler since the last sample
    events_by_id = {},    -- DCS event id -> count since the last sample
    write_calls = 0,      -- write_state calls since the last sample
    write_time = 0.0,     -- seconds spent encoding+writing since the last sample
    write_bytes = 0,      -- size of the most recent encoded payload
    stalls = 0,
    last_wall = 0,
    last_mission = 0,
}

local function diag_count(t)
    local n = 0
    for _ in pairs(t) do n = n + 1 end
    return n
end

local function diag_state_sizes()
    return string.format(
        "dead=%d kill=%d details=%d crash=%d lost=%d destroyed=%d took_off=%d death_time=%d",
        #dead_events, #kill_events, #kill_details, #hit_details, #crash_events, #unit_lost_events,
        #destroyed_objects_positions, diag_count(took_off), diag_count(death_time))
end

local function diag_top_events()
    local parts = {}
    for id, n in pairs(diag.events_by_id) do
        parts[#parts + 1] = string.format("%s:%d", tostring(id), n)
    end
    table.sort(parts)
    return table.concat(parts, " ")
end

function diag_heartbeat()
    local wall = os.time()
    local mission = timer.getTime()
    local wall_gap = wall - diag.last_wall
    local mission_gap = mission - diag.last_mission
    local summary = string.format(
        "t=%.0f wall=%ds mission=%.1fs | events=%d in %.2fs [%s] | write x%d in %.2fs (%d B) | %s",
        mission, wall_gap, mission_gap, diag.events, diag.event_time, diag_top_events(),
        diag.write_calls, diag.write_time, diag.write_bytes, diag_state_sizes())
    if wall_gap >= DIAG_STALL_WARN_S then
        -- The sim lost wall-clock time it never spent on mission time: that gap IS
        -- the freeze. Compare it against the event/write cost reported alongside.
        diag.stalls = diag.stalls + 1
        logger:warn(string.format("DIAG STALL #%d (lag %.0fs): %s",
            diag.stalls, wall_gap - mission_gap, summary))
    elseif diag.events > 0 or diag.write_calls > 0 then
        logger:info("DIAG " .. summary)
    end
    diag.last_wall = wall
    diag.last_mission = mission
    diag.events = 0
    diag.event_time = 0.0
    diag.events_by_id = {}
    diag.write_calls = 0
    diag.write_time = 0.0
    mist.scheduleFunction(diag_heartbeat, {}, timer.getTime() + DIAG_HEARTBEAT_S)
end

function write_state()
    local _debriefing_file_location = debriefing_file_location
    if not debriefing_file_location or debriefing_file_location == "" then
        error("Unable to save DCS Escalation state: debriefing file path is unavailable")
    end

    if not json then
        error("Unable to save DCS Escalation state, JSON library is not loaded")
    end

    local fp, open_error = io.open(_debriefing_file_location, 'w')
    if not fp then
        error("Unable to open state file for writing: "..tostring(_debriefing_file_location).." ("..tostring(open_error)..")")
    end
    local game_state = {
        ["crash_events"] = crash_events,
        ["dead_events"] = dead_events,
        ["base_capture_events"] = base_capture_events,
		["unit_lost_events"] = unit_lost_events,
		["kill_events"] = kill_events,
		["kill_details"] = kill_details,
		["hit_details"] = hit_details,
        ["mission_ended"] = mission_ended,
        ["destroyed_objects_positions"] = destroyed_objects_positions,
        ["model_time"] = timer.getTime(),
        ["took_off"] = took_off,
        ["death_time"] = death_time,
        ["cruise_missiles_state"] = cruise_missiles_state or {},
        ["naval_magazines_state"] = naval_magazines_state or {},
        ["mission_log_events"] = mission_log_events or {},
    }
    local t0 = os.clock()
    local ok, write_error = pcall(function()
        -- Encoded separately from the write so the diagnostics can report the
        -- payload size that this call actually cost.
        local encoded = json:encode(game_state)
        diag.write_bytes = #encoded
        fp:write(encoded)
    end)
    diag.write_time = diag.write_time + (os.clock() - t0)
    diag.write_calls = diag.write_calls + 1
    fp:close()
    if not ok then
        error(write_error)
    end
end

local function canWrite(name)
    local f = io.open(name, "a")
    if f then
        f:close()
        return true
    end
    return false
end

local function testDebriefingFilePath(folderPath, folderName, useCurrentStamping)
    if folderPath then
        local filePath = nil
        if not ends_with(folderPath, "\\") then
            folderPath = folderPath .. "\\"
        end
        if useCurrentStamping then
            filePath = string.format("%sstate-%s.json",folderPath, tostring(os.time()))
        else 
            filePath = string.format("%sstate.json",folderPath)
        end
        local isOk = canWrite(filePath)
        if isOk then 
            logger:info(string.format("The state.json file will be created in %s : (%s)",folderName, filePath))
            return filePath
        end
    end
    return nil
end

local function exportEnvironment(name)
    if os and os.getenv then
        local value = os.getenv(name)
        if value ~= "" then return value end
    end
    return nil
end

local function discoverDebriefingFilePath()
    -- Keep this order aligned with Python's _candidate_state_dirs().
    -- Retain legacy environment names for existing dedicated-server setups.
    local useCurrentStamping = exportEnvironment("ESCALATION_EXPORT_STAMPED_STATE")
        or exportEnvironment("RETRIBUTION_EXPORT_STAMPED_STATE")

    local installPath = nil
    if dcsRetribution then
        installPath = dcsRetribution.installPath
    end
    
    for _, name in ipairs({"ESCALATION_EXPORT_DIR", "RETRIBUTION_EXPORT_DIR"}) do
        local result = testDebriefingFilePath(exportEnvironment(name), name, useCurrentStamping)
        if result then
            return result
        end
    end
    local result = testDebriefingFilePath(installPath, "the DCS Escalation install folder", useCurrentStamping)
    if result then
        return result
    end
    for _, name in ipairs({"TEMP", "TMP"}) do
        result = testDebriefingFilePath(exportEnvironment(name), name, useCurrentStamping)
        if result then
            return result
        end
    end

    -- nothing worked, let's try the last resort folder : current directory.
    if lfs then
        return testDebriefingFilePath(lfs.writedir().."Missions\\", "the working directory", useCurrentStamping)
    end
    
    return nil
end

debriefing_file_location = discoverDebriefingFilePath()
local error_message_shown = false

write_state_error_handling = function()
    local _debriefing_file_location = debriefing_file_location
    if not debriefing_file_location then 
        _debriefing_file_location = "[nil]"
        logger:error("Unable to find where to write DCS Escalation state")
    end

    -- Only write if state has changed since last write
    if dirty_state then
        if pcall(write_state) then
            dirty_state = false -- Reset dirty flag after successful write
            error_message_shown = false
        else
            if not error_message_shown then
                messageAll("Unable to write DCS Escalation state to ".._debriefing_file_location..
                        "\nYou can abort the mission in DCS Escalation.\n"..
                        "\n\nCheck the DCS installation directory in Settings > General > Application preferences. Then restart DCS Escalation and DCS."..
                        "\n\nAlternatively, replace <dcs_installation_directory>/Scripts/MissionScripting.lua with <escalation_folder>/resources/scripts/MissionScripting.lua and restart DCS. This may need repeating after DCS updates."..
                        "\n\nMission progress cannot be recorded until this is fixed.")
                error_message_shown = true
            end
        end
    end

    -- Reschedule quickly if mission is over and we still have unsaved changes,
    -- otherwise use the normal cadence.
    local next_schedule_in_seconds = WRITESTATE_SCHEDULE_IN_SECONDS
    if mission_ended and dirty_state then
        next_schedule_in_seconds = 1
    end
    mist.scheduleFunction(write_state_error_handling, {}, timer.getTime() + next_schedule_in_seconds)
end

activeWeapons = {}

-- True if `name` is a player jet that just LEFT the seat (and did not eject) — i.e.
-- this crash/dead/lost is the despawn after the player went to spectator or the
-- mission ended, not a kill. The mark is NOT consumed: a single despawn can fire
-- CRASH *and* DEAD *and* UNIT_LOST for the same unit, and all three must be
-- suppressed, so we gate purely on the time window (a leave+re-occupy+real-loss
-- inside PLAYER_LEAVE_GRACE_S seconds is not physically possible).
local function is_player_despawn(name)
    if name == nil or ejected_units[name] then
        return false
    end
    local left_at = player_left_units[name]
    return left_at ~= nil and (timer.getTime() - left_at) <= PLAYER_LEAVE_GRACE_S
end

local function onEvent(event)
    -- Indirect-kill attribution data (consumed by the debriefing): which units
    -- took off, and the first death-event time of each unit. pcall-guarded so a
    -- missing accessor never breaks the mission.
    --
    -- The type(n) == "string" guards are load-bearing, not defensive fluff. For
    -- scenery/map objects getName() returns a NUMBER (an object id in the tens of
    -- millions), and a Hercules clipping an airfield fence fires S_EVENT_DEAD with
    -- exactly such an initiator. One numeric key like death_time[71610370] makes
    -- JSON.lua encode the table as an array with 71M null holes: ~100 s of CPU on
    -- the sim thread per write_state and a "table overflow" abort, retried every
    -- 15 s because the failed write never clears dirty_state -- the recurring
    -- in-mission freeze. Scenery deaths carry no debriefing value; drop them.
    if event.id == world.event.S_EVENT_TAKEOFF and event.initiator then
        pcall(function()
            local n = event.initiator:getName()
            if type(n) == "string" and not took_off[n] then took_off[n] = true; dirty_state = true end
        end)
    end
    if event.id == world.event.S_EVENT_KILL and event.target then
        pcall(function()
            local n = event.target:getName()
            if type(n) == "string" and death_time[n] == nil then death_time[n] = timer.getTime(); dirty_state = true end
        end)
    end
    if event.initiator and (event.id == world.event.S_EVENT_CRASH
        or event.id == world.event.S_EVENT_DEAD
        or event.id == world.event.S_EVENT_UNIT_LOST) then
        pcall(function()
            local n = event.initiator:getName()
            -- Skip player-despawns (same guard as the loss lists) so death_time
            -- only holds genuine deaths.
            if type(n) == "string" and death_time[n] == nil and not is_player_despawn(n) then
                death_time[n] = timer.getTime(); dirty_state = true
            end
        end)
    end

    -- Track player seat-leaves and ejections first so the loss handlers below can
    -- tell a despawn (player left, survived) from a real shootdown.
    if event.id == world.event.S_EVENT_EJECTION and event.initiator
       and event.initiator.getName then
        ejected_units[event.initiator.getName(event.initiator)] = true
    end

    if event.id == world.event.S_EVENT_PLAYER_LEAVE_UNIT and event.initiator
       and event.initiator.getName then
        player_left_units[event.initiator.getName(event.initiator)] = timer.getTime()
    end

    if event.id == world.event.S_EVENT_CRASH and event.initiator then
        local name = event.initiator.getName(event.initiator)
        if not is_player_despawn(name) then
            crash_events[#crash_events + 1] = name
            dirty_state = true
        end
    end

    if event.id == world.event.S_EVENT_UNIT_LOST and event.initiator then
        local name = event.initiator.getName(event.initiator)
        if not is_player_despawn(name) then
            unit_lost_events[#unit_lost_events + 1] = name
            dirty_state = true
        end
    end
	
	if event.id == world.event.S_EVENT_KILL and event.target then
        local target_name = event.target.getName(event.target)
        kill_events[#kill_events + 1] = target_name
        -- Also record who killed it and with what, for the UI event feed. All
        -- accessors are pcall-guarded so a missing field never breaks the mission.
        local detail = { ["target"] = target_name }
        if type(target_name) == "number" then
            -- Scenery: the id means nothing downstream, and a kill recorded
            -- against it can never be resolved, so the pilot who levelled a
            -- refinery went uncredited. Name the objective standing on that spot,
            -- which is the key the scenery map is built on.
            local zone, distance = scenery_zone_for(event.target)
            if zone ~= nil and distance <= SCENERY_MATCH_RADIUS then
                detail["target"] = zone.name
            end
        end
        if event.initiator then
            pcall(function() detail["initiator"] = event.initiator:getName() end)
            pcall(function() detail["initiator_type"] = event.initiator:getTypeName() end)
            pcall(function()
                local pn = event.initiator:getPlayerName()
                if pn and pn ~= "" then detail["initiator_player"] = pn end
            end)
        end
        if event.weapon then
            pcall(function() detail["weapon"] = event.weapon:getTypeName() end)
        end
        kill_details[#kill_details + 1] = detail
        dirty_state = true
    end

    if event.id == world.event.S_EVENT_HIT and event.target and event.target.getName then
        -- Only scenery gets this far, and only the kind that cannot be damaged:
        -- anything with a damage model is left to die on its own and be counted
        -- by S_EVENT_DEAD below. The numeric name is the cheapest of the three
        -- tests, so it goes first and keeps strafing runs off the zone search.
        local name = event.target.getName(event.target)
        if type(name) == "number" and is_indestructible(event.target) then
            if credit_scenery_zone(event.target, ", indestructible: credited on impact",
                    event.initiator, event.weapon) then
                dirty_state = true
            end
        end
    end

    -- A hit is not a kill, but it is work: a pilot who leaves a destroyer burning
    -- and does not finish it off has earned something. Only an aircraft's hits are
    -- recorded, and only the first one it lands on each target: a front line trading
    -- cannon fire would fill the save, and a strafing pass would otherwise pay by the
    -- round. The string guard is the scenery lesson again -- getName() returns a
    -- number for scenery, and a number here would poison the lookup table.
    if event.id == world.event.S_EVENT_HIT and event.initiator and event.target then
        pcall(function()
            if #hit_details >= HIT_DETAIL_LIMIT then return end
            local category = event.initiator:getDesc().category
            if category ~= Unit.Category.AIRPLANE and category ~= Unit.Category.HELICOPTER then
                return
            end
            local initiator_name = event.initiator:getName()
            local target_name = event.target:getName()
            if type(initiator_name) ~= "string" or type(target_name) ~= "string" then return end
            local seen = hit_seen[initiator_name]
            if seen == nil then seen = {}; hit_seen[initiator_name] = seen end
            if seen[target_name] then return end
            seen[target_name] = true
            local detail = { ["target"] = target_name, ["initiator"] = initiator_name }
            pcall(function() detail["initiator_type"] = event.initiator:getTypeName() end)
            pcall(function()
                local pn = event.initiator:getPlayerName()
                if pn and pn ~= "" then detail["initiator_player"] = pn end
            end)
            if event.weapon then
                pcall(function() detail["weapon"] = event.weapon:getTypeName() end)
            end
            hit_details[#hit_details + 1] = detail
            dirty_state = true
        end)
    end

    if event.id == world.event.S_EVENT_DEAD and event.initiator and event.initiator.getName then
        local name = event.initiator.getName(event.initiator)
        if not is_player_despawn(name) then
            if type(name) == "number" then
                -- Scenery. The id is meaningless downstream, so credit the
                -- objective standing on that spot instead, or drop it.
                credit_scenery_zone(event.initiator)
            else
                dead_events[#dead_events + 1] = name
            end
            local position = event.initiator.getPosition(event.initiator)
            local destruction = {}
            destruction.x = position.p.x
            destruction.y = position.p.y
            destruction.z = position.p.z
            destruction.type = event.initiator:getTypeName()
            destruction.orientation = mist.getHeading(event.initiator) * 57.3
            -- Only track actual units/buildings, not debris/crash models
            if destruction.type ~= nil and
               string.find(destruction.type, "GENERIC_CRASH_MODEL") == nil and
               string.find(destruction.type, "_CRASH") == nil then
                destroyed_objects_positions[#destroyed_objects_positions + 1] = destruction
            end
            dirty_state = true
        end
    end

    if event.id == world.event.S_EVENT_MISSION_END then
        mission_ended = true
        dirty_state = true
        if pcall(write_state) then
            dirty_state = false
        end
    end

end

if DIAG_ENABLED then
    -- Same handler, wrapped so a stall report can say how many events arrived in
    -- the gap and how long they cost us (an event storm is one of the suspects).
    mist.addEventHandler(function(event)
        local t0 = os.clock()
        diag.events = diag.events + 1
        local id = event and event.id or -1
        diag.events_by_id[id] = (diag.events_by_id[id] or 0) + 1
        onEvent(event)
        diag.event_time = diag.event_time + (os.clock() - t0)
    end)
    diag.last_wall = os.time()
    diag.last_mission = timer.getTime()
    mist.scheduleFunction(diag_heartbeat, {}, timer.getTime() + DIAG_HEARTBEAT_S)
    logger:info(string.format(
        "DIAG enabled: heartbeat every %ds, stall threshold %ds wall clock",
        DIAG_HEARTBEAT_S, DIAG_STALL_WARN_S))
else
    mist.addEventHandler(onEvent)
end

dirty_state = true
write_state_error_handling()

-- Escort leash
-- Escorts are kept within their engagement range relative to the escorted group.
-- This is driven by the mission-injected dcsRetribution.Escorts table.

local function escort_leash_get_group(id)
    local group_id = tonumber(id)
    if not group_id or group_id <= 0 then
        return nil
    end
    -- DCS has no Group.getByID; resolve the mission group id to a name via mist.
    local data = mist.DBs.groupsById and mist.DBs.groupsById[group_id]
    return data and Group.getByName(data.groupName) or nil
end

local function escort_leash_set_roe(group, roe)
    if not group then
        return
    end
    local controller = group:getController()
    if controller then
        controller:setOption(AI.Option.Air.id.ROE, roe)
    end
end

local function escort_leash_update()
    -- Keep running even if dcsRetribution data isn't available yet (trigger ordering)
    if not dcsRetribution or type(dcsRetribution.Escorts) ~= "table" then
        return timer.getTime() + 10
    end

    for _, pair in pairs(dcsRetribution.Escorts) do
        local escort_group = escort_leash_get_group(pair.escortGroupId)
        local escorted_group = escort_leash_get_group(pair.escortedGroupId)

        -- If the escorted group no longer exists (dead/despawned), ensure escort isn't stuck.
        if escort_group and not escorted_group then
            escort_leash_set_roe(escort_group, AI.Option.Air.val.ROE.OPEN_FIRE)
        elseif escort_group and escorted_group then
            local escort_unit = escort_group:getUnit(1)
            local escorted_unit = escorted_group:getUnit(1)
            if escort_unit and escorted_unit then
                local escort_pos = escort_unit:getPoint()
                local escorted_pos = escorted_unit:getPoint()
                local dx = escort_pos.x - escorted_pos.x
                local dz = escort_pos.z - escorted_pos.z
                local distance = math.sqrt(dx * dx + dz * dz)

                local max_dist = tonumber(pair.engagementRangeMeters) or 0
                if max_dist > 0 and distance > max_dist then
                    escort_leash_set_roe(escort_group, AI.Option.Air.val.ROE.RETURN_FIRE)
                else
                    escort_leash_set_roe(escort_group, AI.Option.Air.val.ROE.OPEN_FIRE)
                end
            end
        end
    end

    return timer.getTime() + 10
end

timer.scheduleFunction(escort_leash_update, nil, timer.getTime() + 1)
