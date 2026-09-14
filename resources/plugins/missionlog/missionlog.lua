-- Mission Log: a running commentary of what happens to your side.
--
-- DCS already knows everything that happens; what it will not tell you is who
-- it happened to. A kill event names a unit "STAG BARCAP|2|14|F-15C Eagle| Pilot
-- #2", which is unreadable mid-flight, and says nothing about the pilot flying
-- it. Retribution knows the pilot, so the mission generator seeds
-- RETRIBUTION_PILOTS with the name behind every unit and this script turns the
-- raw events into sentences.
--
-- Every message goes to one coalition only: the side it is news for. A kill is
-- news for the shooter's side, the same kill is a loss for the other, and each
-- side can switch its own categories off.

MISSION_LOG_DEFAULTS = {
    airkills = true,
    groundkills = true,
    damage = false,
    losses = true,
    crashes = true,
    flightstatus = false,
    intercepts = true,
    monitoring = true,
    defending = true,
    engaging = true,
    duration = 20,
    maxmessages = 12,
    goodnews = "YEAH!",
    badnews = "OH NO!",
}

local function option(name)
    local fallback = MISSION_LOG_DEFAULTS[name]
    if dcsRetribution == nil or dcsRetribution.plugins == nil then
        return fallback
    end
    local plugin = dcsRetribution.plugins.missionlog
    if plugin == nil or plugin[name] == nil then
        return fallback
    end
    return plugin[name]
end

local DURATION = tonumber(option("duration")) or MISSION_LOG_DEFAULTS.duration

-- A kill and a loss are the two lines you want to find again in a column that
-- scrolls, and by the time you look they have gone past. A word in front of each
-- is what the eye catches; the campaign chooses the words, and an empty one turns
-- the whole thing off without another switch to find.
local function cheer(good, text)
    local word = option(good and "goodnews" or "badnews")
    if word == nil then
        return text
    end
    word = tostring(word):gsub("^%s+", ""):gsub("%s+$", "")
    if word == "" then
        return text
    end
    return word .. " " .. text
end

local logger = mist and mist.Logger:new("MissionLog", "info") or nil

-- The chronicle's raw material.
--
-- Facts, not sentences: "two kills forty seconds apart by the same pilot" is a
-- statement about a list, and you cannot recover it from prose. The prose is
-- written afterwards, in Python, from these.
--
-- Two rules, both bought with pain. The table is a contiguous integer array and
-- never keyed by anything a unit might be called -- scenery getName() returns a
-- number in the tens of millions, and one numeric key makes JSON.lua encode
-- seventy-one million null holes, which is the in-mission freeze documented in
-- dcs_retribution.lua. And it is bounded: state.json is rewritten every fifteen
-- seconds on the sim thread, so an unbounded list is a frame-time bug waiting.
MISSION_LOG_MAX_EVENTS = 2000

mission_log_events = mission_log_events or {}

local recorded = 0
local truncated = false

local function record(fields)
    if recorded >= MISSION_LOG_MAX_EVENTS then
        if not truncated then
            truncated = true
            if logger then
                logger:info(string.format(
                    "Mission Log: %d events recorded, no longer recording",
                    MISSION_LOG_MAX_EVENTS))
            end
        end
        return
    end
    recorded = recorded + 1
    fields.t = timer.getTime()
    mission_log_events[recorded] = fields
end

-- A budget, per side, per minute.
--
-- One Mk-83 into a building objective hits a dozen separate scenery pieces, each
-- with its own name, and a Harrier working over a target area filled the entire
-- screen top to bottom. Coalescing helps but cannot save it: those really are
-- different targets. So the screen gets a budget and the overflow is counted,
-- not printed.
--
-- dcs.log keeps everything regardless. The limit is about what a pilot can read
-- mid-flight, not about what is worth recording.
MESSAGE_WINDOW_SECONDS = 60

local budget_state = {}

local function announce(side, category, text)
    if logger then
        logger:info(string.format("[%s] %s", category, text))
    end
    if not option(category) then
        return
    end

    local budget = tonumber(option("maxmessages")) or MISSION_LOG_DEFAULTS.maxmessages
    local now = timer.getTime()
    local state = budget_state[side]
    if state == nil then
        state = {start = now, shown = 0, held = 0}
        budget_state[side] = state
    end

    if now - state.start >= MESSAGE_WINDOW_SECONDS then
        if state.held > 0 then
            trigger.action.outTextForCoalition(side, string.format(
                "(%d more mission log messages this minute, see dcs.log)",
                state.held), DURATION, false)
        end
        state.start, state.shown, state.held = now, 0, 0
    end

    if state.shown >= budget then
        state.held = state.held + 1
        return
    end
    state.shown = state.shown + 1
    trigger.action.outTextForCoalition(side, text, DURATION, false)
end

-- Retribution names a flight's units "<target> <task>|<country>|<n>|<aircraft>|
-- Pilot #<n>", so the aircraft the player recognises is already in the name --
-- no unit-type lookup table needed, and mod aircraft come out right too.
local function fields_of(name)
    local fields = {}
    for field in string.gmatch(tostring(name) .. "|", "([^|]*)|") do
        fields[#fields + 1] = field
    end
    return fields
end

local function pilot_of(unit, name)
    if type(RETRIBUTION_PILOTS) == "table" and RETRIBUTION_PILOTS[name] then
        return RETRIBUTION_PILOTS[name]
    end
    -- A human in the seat outranks the roster: the slot may be flown by anyone.
    local player
    if pcall(function() player = unit:getPlayerName() end) and player then
        return player
    end
    return nil
end

local function name_of(unit)
    local name
    if pcall(function() name = unit:getName() end) and name ~= nil then
        return tostring(name)
    end
    return nil
end

-- What to call something in a sentence. Aircraft get their pilot, ground units
-- get the readable half of their name ("0379 | SAM SA-8 Osa 'Gecko' TEL"), and
-- anything unrecognised falls back to its DCS type. Returns the text and whether
-- it already names somebody: a crewed aircraft is "F-15C Eagle flown by X" and
-- stands alone; a tank is "T-72B", which needs an article in a sentence but must
-- stay bare to be counted ("3 T-72B").
local function describe_bare(unit)
    if unit == nil then
        return "something", true
    end
    local name, kind
    if not pcall(function() name = unit:getName() end) or name == nil then
        return "something", true
    end
    pcall(function() kind = unit:getTypeName() end)
    name = tostring(name)

    local readable = string.match(name, "^%d+%s*|%s*(.+)$")
    if readable then
        return readable, false
    end

    local fields = fields_of(name)
    local aircraft = fields[4]
    if aircraft == nil or aircraft == "" then
        aircraft = kind or "aircraft"
    end
    local pilot = pilot_of(unit, name)
    if pilot then
        return string.format("%s flown by %s", aircraft, pilot), true
    end
    return aircraft, false
end

-- Both sides fly the same airframes in some campaigns, where "the Su-27" says
-- nothing about whose it is. Anything belonging to the other coalition is named as
-- theirs -- and only then: a blue-on-blue is not an enemy.
local function describe(unit, enemy)
    local text, named = describe_bare(unit)
    if named then
        return enemy and ("enemy " .. text) or text
    end
    return (enemy and "the enemy " or "the ") .. text
end

-- The same information describe() renders, but kept apart: the chronicle needs
-- to say "Bentley's third of the day" and cannot get that out of a sentence.
local function unit_fields(unit)
    if unit == nil then
        return nil, nil
    end
    local name = name_of(unit)
    if name == nil then
        return nil, nil
    end
    local readable = string.match(name, "^%d+%s*|%s*(.+)$")
    if readable then
        return readable, nil
    end
    local kind = fields_of(name)[4]
    if kind == nil or kind == "" then
        pcall(function() kind = unit:getTypeName() end)
    end
    return kind, pilot_of(unit, name)
end

-- Which objective a piece of scenery belongs to.
--
-- A bomb into a factory damages a dozen separate map models -- BLACKGUM,
-- SILO_02, HOLE12 -- and naming those tells a pilot nothing. The objective they
-- stand in does. The base plugin already matches scenery to objectives by
-- position for scoring; this borrows the same lookup, but with a far wider
-- radius: 30 m is the right bar for *crediting* a kill, and much too tight for
-- merely saying which factory a shed was part of.
SCENERY_NAMING_RADIUS = 500

local function scenery_objective(unit)
    if type(scenery_zone_for) ~= "function" then
        return nil
    end
    local ok, zone, distance = pcall(scenery_zone_for, unit)
    if not ok or zone == nil or distance == nil or distance > SCENERY_NAMING_RADIUS then
        return nil
    end
    if zone.objective == nil or zone.objective == "" then
        return nil
    end
    if zone.category ~= nil and zone.category ~= "" then
        return string.format("%s %s", zone.category, zone.objective)
    end
    return zone.objective
end

-- A formation, not a jet. An interception is something a flight does to another
-- flight: describing it unit by unit turns one event into a wall of nine
-- identical lines, all at the same range, differing only in which enemy
-- wingman was named.
local function describe_flight(group, enemy)
    local herd = enemy and "an enemy flight" or "a flight"
    local leader, size
    if not pcall(function() leader = group:getUnit(1) end) or leader == nil then
        return herd
    end
    if not pcall(function() size = group:getSize() end) or size == nil then
        size = 1
    end
    if size <= 1 then
        return describe(leader, enemy)
    end
    local name
    if not pcall(function() name = leader:getName() end) or name == nil then
        return herd
    end
    name = tostring(name)
    local aircraft = fields_of(name)[4]
    if aircraft == nil or aircraft == "" then
        pcall(function() aircraft = leader:getTypeName() end)
    end
    local pilot = pilot_of(leader, name)
    if pilot then
        return string.format("%s of %d %s led by %s", herd, size, aircraft or "aircraft", pilot)
    end
    return string.format("%s of %d %s", herd, size, aircraft or "aircraft")
end

local function side_of(unit)
    local side
    if pcall(function() side = unit:getCoalition() end) then
        return side
    end
    return nil
end

-- DCS numbers Weapon.Category from zero just like Unit.Category, so a missile's
-- desc category is 1 -- the same value as HELICOPTER, which had every missile in
-- the air reported as an aircraft. getCategory has changed meaning between
-- builds, so probe for the launcher instead: only a weapon has one.
local function is_weapon(object)
    local launcher
    return pcall(function() launcher = object.getLauncher end) and launcher ~= nil
end

local function is_aircraft(unit)
    if is_weapon(unit) then
        return false
    end
    local category
    if not pcall(function() category = unit:getDesc().category end) then
        return false
    end
    return category == Unit.Category.AIRPLANE or category == Unit.Category.HELICOPTER
end

local function weapon_name(event)
    local name
    if event.weapon ~= nil and pcall(function() name = event.weapon:getTypeName() end)
            and name ~= nil then
        -- DCS hands back the internal id, "AGM_65D". The underscore is a hyphen
        -- everywhere a human writes it.
        return (tostring(name):gsub("_", "-"))
    end
    return nil
end

-- DCS does not always attach the weapon to S_EVENT_KILL. A ship's SAM kill
-- arrives bare, and the first version of this reported it as cannon fire --
-- the Ticonderoga shot an SM-2, not its gun. The preceding S_EVENT_HIT does
-- carry the weapon, so it is remembered per shooter-and-target and used when
-- the kill omits it.
--
-- Keys are built with concatenation, so always strings: a numeric key here
-- would be harmless (this table is never serialised) but the habit is worth
-- keeping after what one cost us in state.json.
WEAPON_MEMORY_SECONDS = 30

local weapon_memory = {}

local function engagement_key(initiator, target)
    if initiator == nil or target == nil then
        return nil
    end
    local shooter, victim = name_of(initiator), name_of(target)
    if shooter == nil or victim == nil then
        return nil
    end
    return shooter .. "\30" .. victim
end

local function remember_weapon(event)
    local weapon = weapon_name(event)
    if weapon == nil then
        return
    end
    local key = engagement_key(event.initiator, event.target)
    if key ~= nil then
        weapon_memory[key] = {weapon = weapon, t = timer.getTime()}
    end
end

local function forget_old_weapons()
    local now = timer.getTime()
    for key, entry in pairs(weapon_memory) do
        if now - entry.t > WEAPON_MEMORY_SECONDS then
            weapon_memory[key] = nil
        end
    end
end

-- No article: "with AGM-65D" sidesteps the a/an problem that "a AGM-65D" walks
-- straight into.
local function weapon_suffix(event)
    local weapon = weapon_name(event)
    if weapon == nil then
        local key = engagement_key(event.initiator, event.target)
        local remembered = key ~= nil and weapon_memory[key] or nil
        weapon = remembered ~= nil and remembered.weapon or nil
    end
    if weapon then
        return " with " .. weapon
    end
    -- Unknown stays unknown. Naming a weapon we were never told about is how
    -- an SM-2 became cannon fire.
    return ""
end

local function with_weapon(text, event)
    return text .. weapon_suffix(event)
end

local function place_name(event)
    local name
    if event.place ~= nil and pcall(function() name = event.place:getName() end) then
        return tostring(name)
    end
    return nil
end

-- A shot-down aircraft fires S_EVENT_KILL and then S_EVENT_CRASH. Without this
-- the crash would be reported a second time as if nobody had shot it.
local killed = {}

local function remember_killed(unit)
    local name
    if pcall(function() name = unit:getName() end) and name then
        killed[tostring(name)] = true
    end
end

local function was_killed(unit)
    local name
    if pcall(function() name = unit:getName() end) and name then
        return killed[tostring(name)] == true
    end
    return false
end

-- One Maverick against a tank fires S_EVENT_HIT once per fragment, and a pass
-- over a column produces a line per vehicle. Both read as spam, and the vehicles
-- are indistinguishable in text anyway -- "the T-72B" seven times tells you
-- nothing. So ground events are collected for a few seconds and reported once
-- with a count: repeated hits on the same vehicle collapse to one, and several
-- vehicles of a kind become "3 T-72B".
GROUND_FLUSH_SECONDS = 8

local pending_ground = {}

DEFENDING_QUIET_SECONDS = 20
local defending_seen = {}

-- A target that dies inside the window should read as killed, not as hit and
-- then killed: the earlier damage was on the way to this.
local function forget_damage(target_id)
    if target_id == nil then
        return
    end
    local id = tostring(target_id)
    for key, bucket in pairs(pending_ground) do
        if bucket.category == "damage" and bucket.seen[id] then
            bucket.seen[id] = nil
            bucket.count = bucket.count - 1
            if bucket.count <= 0 then
                pending_ground[key] = nil
            end
        end
    end
end

-- Takes a table: ten positional arguments was one too many to read.
local function queue_ground(e)
    if e.category == "groundkills" then
        forget_damage(e.target_id)
    end
    -- Whose the target was is part of the key: a friendly T-72 and an enemy
    -- one killed in the same window are not "3 enemy T-72".
    local key = table.concat(
        {tostring(e.side), e.category, e.actor, e.verb, e.target,
         e.weapon, tostring(e.enemy == true)}, "\30")
    local bucket = pending_ground[key]
    if bucket == nil then
        bucket = {side = e.side, category = e.category, actor = e.actor,
                  verb = e.verb, target = e.target, weapon = e.weapon,
                  enemy = e.enemy == true,
                  scenery = e.scenery == true, actor_type = e.actor_type,
                  actor_pilot = e.actor_pilot, weapon_name = e.weapon_name,
                  seen = {}, count = 0}
        pending_ground[key] = bucket
    end
    -- Counted per piece even for scenery, so "several" means several.
    local id = tostring(e.target_id or e.target)
    if not bucket.seen[id] then
        bucket.seen[id] = true
        bucket.count = bucket.count + 1
    end
end

local function flush_ground()
    for key, bucket in pairs(pending_ground) do
        local what
        if bucket.scenery then
            what = string.format("%s in the %s",
                bucket.count > 1 and "several objects" or "an object", bucket.target)
        elseif bucket.count > 1 then
            what = string.format("%d %s%s", bucket.count,
                bucket.enemy and "enemy " or "", bucket.target)
        else
            what = (bucket.enemy and "the enemy " or "the ") .. bucket.target
        end
        -- Recorded here, not at queue time: the count is the fact worth
        -- keeping, and it is only known once the window closes.
        record({kind = bucket.category, side = bucket.side, verb = bucket.verb,
                actor_type = bucket.actor_type, actor_pilot = bucket.actor_pilot,
                target_type = bucket.target, count = bucket.count,
                scenery = bucket.scenery, weapon = bucket.weapon_name})
        local line = string.format(
            "%s %s %s%s", bucket.actor, bucket.verb, what, bucket.weapon)
        if bucket.category == "groundkills" then
            -- Ours only when what died was theirs: blue blowing up blue is not a
            -- moment for a cheer.
            line = cheer(bucket.enemy, line)
        end
        announce(bucket.side, bucket.category, line)
        pending_ground[key] = nil
    end
end

-- Scenery is the one thing DCS names with a number instead of a string.
local function is_scenery(unit)
    local name
    if pcall(function() name = unit:getName() end) then
        return type(name) == "number"
    end
    return false
end

-- Text, dedup id, and whether this is scenery, for one ground target. Returns
-- nil for anything not worth a line.
--
-- The name is bare here; whether it belongs to the enemy is decided by the
-- caller, which is the only place that knows who did the shooting.
local function ground_target(unit)
    if is_scenery(unit) then
        local objective = scenery_objective(unit)
        if objective == nil then
            -- Scenery belonging to no objective: a bomb short into the woods.
            -- "hit the GREENASHFOREST" is a model name, not news, and the miss
            -- is already obvious from the target still standing.
            return nil
        end
        return objective, name_of(unit), true
    end
    return (describe_bare(unit)), name_of(unit), false
end

local handler = {}

function handler:onEvent(event)
    local id = event.id
    local e = world.event

    -- A missile in the air with one of ours on the nose. DCS puts no target on
    -- S_EVENT_SHOT, but the weapon itself knows what it is guiding on, which is
    -- the only way to say who is defending rather than merely who fired.
    if id == e.S_EVENT_SHOT and event.weapon then
        local target
        if pcall(function() target = event.weapon:getTarget() end) and target ~= nil
                and (is_aircraft(target) or is_weapon(target)) then
            local victim = side_of(target)
            local shooter = side_of(event.initiator)
            local key = engagement_key(event.initiator, target)
            local now = timer.getTime()
            -- A salvo is one moment of drama, not four.
            if key ~= nil and (defending_seen[key] == nil
                               or now - defending_seen[key] > DEFENDING_QUIET_SECONDS) then
                defending_seen[key] = now
                local shooter_type, shooter_pilot = unit_fields(event.initiator)
                local target_type, target_pilot = unit_fields(target)
                -- One launch is news to both sides, and it is a different piece
                -- of news to each: your wingman is shooting, or something is
                -- shooting at you. Reporting only the second left a player
                -- watching his own flights fire at nothing.
                -- A missile neither defends itself nor survives, so a shot
                -- at one is news only to the side taking it.
                if victim ~= nil and not is_weapon(target) then
                    record({kind = "defending", side = victim,
                            actor_type = target_type, actor_pilot = target_pilot,
                            target_type = shooter_type, target_pilot = shooter_pilot,
                            weapon = weapon_name(event)})
                    local hostile = shooter ~= nil and shooter ~= victim
                    local incoming = weapon_name(event)
                    if hostile then
                        incoming = "an enemy " .. (incoming or "missile")
                    else
                        incoming = incoming or "a missile"
                    end
                    announce(victim, "defending", string.format(
                        "%s is defending against %s from %s", describe(target),
                        incoming, describe(event.initiator, hostile)))
                end
                if shooter ~= nil then
                    record({kind = "engaging", side = shooter,
                            actor_type = shooter_type, actor_pilot = shooter_pilot,
                            target_type = target_type, target_pilot = target_pilot,
                            weapon = weapon_name(event)})
                    announce(shooter, "engaging", string.format(
                        "%s is engaging %s%s", describe(event.initiator),
                        describe(target, victim ~= nil and victim ~= shooter),
                        weapon_suffix(event)))
                end
            end
        end
        return
    end

    if id == e.S_EVENT_KILL and event.initiator and event.target then
        -- Downing a missile is neither an air kill nor a ground target.
        if is_weapon(event.target) then
            return
        end
        local shooter, victim = side_of(event.initiator), side_of(event.target)
        local killer_text = describe(event.initiator)
        local victim_text = describe(event.target)
        if is_aircraft(event.target) then
            remember_killed(event.target)
            local killer_type, killer_pilot = unit_fields(event.initiator)
            local victim_type, victim_pilot = unit_fields(event.target)
            record({kind = "airkill", side = shooter,
                    actor_type = killer_type, actor_pilot = killer_pilot,
                    target_type = victim_type, target_pilot = victim_pilot,
                    weapon = weapon_name(event)})
            local hostile = shooter ~= nil and victim ~= nil and shooter ~= victim
            if shooter then
                announce(shooter, "airkills", cheer(true, with_weapon(string.format(
                    "%s SHOT DOWN %s", killer_text,
                    describe(event.target, hostile)), event)))
            end
            if victim then
                announce(victim, "losses", cheer(false, with_weapon(string.format(
                    "%s was SHOT DOWN by %s", victim_text,
                    describe(event.initiator, hostile)), event)))
            end
        elseif shooter then
            local text, target_id, scenery = ground_target(event.target)
            if text ~= nil then
                local kind, pilot = unit_fields(event.initiator)
                local target_side = side_of(event.target)
                local hostile_ground = shooter ~= nil and target_side ~= nil
                    and shooter ~= target_side
                queue_ground({side = shooter, category = "groundkills",
                    enemy = hostile_ground,
                    actor = killer_text, verb = "DESTROYED", target = text,
                    weapon = weapon_suffix(event), weapon_name = weapon_name(event),
                    target_id = target_id, scenery = scenery,
                    actor_type = kind, actor_pilot = pilot})
            end
        end
        return
    end

    if id == e.S_EVENT_HIT and event.initiator and event.target then
        -- Recorded for every hit, aircraft included: this is where the weapon
        -- behind a bare kill event comes from.
        remember_weapon(event)
        local shooter = side_of(event.initiator)
        if shooter and not is_aircraft(event.target)
                and not is_weapon(event.target) then
            local text, target_id, scenery = ground_target(event.target)
            if text ~= nil then
                local kind, pilot = unit_fields(event.initiator)
                local damaged_side = side_of(event.target)
                queue_ground({side = shooter, category = "damage",
                    enemy = shooter ~= nil and damaged_side ~= nil
                        and shooter ~= damaged_side,
                    actor = describe(event.initiator), verb = "hit", target = text,
                    weapon = weapon_suffix(event), weapon_name = weapon_name(event),
                    target_id = target_id, scenery = scenery,
                    actor_type = kind, actor_pilot = pilot})
            end
        end
        return
    end

    if id == e.S_EVENT_EJECTION and event.initiator then
        local side = side_of(event.initiator)
        if side then
            local kind, pilot = unit_fields(event.initiator)
            record({kind = "ejection", side = side,
                    actor_type = kind, actor_pilot = pilot})
            announce(side, "losses", string.format("%s EJECTED", describe(event.initiator)))
        end
        return
    end

    if id == e.S_EVENT_CRASH and event.initiator then
        if was_killed(event.initiator) then
            return
        end
        local side = side_of(event.initiator)
        if side then
            local kind, pilot = unit_fields(event.initiator)
            record({kind = "crash", side = side,
                    actor_type = kind, actor_pilot = pilot})
            announce(side, "crashes",
                cheer(false, string.format("%s CRASHED", describe(event.initiator))))
        end
        return
    end

    if id == e.S_EVENT_TAKEOFF and event.initiator then
        local side = side_of(event.initiator)
        if side then
            local kind, pilot = unit_fields(event.initiator)
            record({kind = "takeoff", side = side, actor_type = kind,
                    actor_pilot = pilot, place = place_name(event)})
            local place = place_name(event)
            local text = string.format("%s took off", describe(event.initiator))
            if place then
                text = text .. " from " .. place
            end
            announce(side, "flightstatus", text)
        end
        return
    end

    if id == e.S_EVENT_LAND and event.initiator then
        local side = side_of(event.initiator)
        if side then
            local kind, pilot = unit_fields(event.initiator)
            record({kind = "land", side = side, actor_type = kind,
                    actor_pilot = pilot, place = place_name(event)})
            local place = place_name(event)
            local text = string.format("%s landed", describe(event.initiator))
            if place then
                text = text .. " at " .. place
            end
            announce(side, "flightstatus", text)
        end
        return
    end
end

world.addEventHandler(handler)

-- Interceptions.
--
-- DCS fires no event for "I have seen him and I am going after him", so this is
-- polled: every fighter group is asked what its radar holds and what the
-- datalink handed it, which is the same getDetectedTargets call the EWRS plugin
-- has been using all along. A contact is announced once, and only the first
-- time, so a long tail chase does not repeat itself every sweep.
INTERCEPT_POLL_SECONDS = 20
INTERCEPT_MAX_RANGE_M = 148160 -- 80 nm: past this it is a blip, not an intercept
-- Inside this a fighter plausibly commits; beyond it, a BARCAP stays on
-- station however well it can see the contact.
INTERCEPT_COMMIT_M = 74080 -- 40 nm

local announced_contacts = {}

local function detected_names(controller, method)
    local seen = {}
    local contacts
    if not pcall(function() contacts = controller:getDetectedTargets(method) end) then
        return seen
    end
    for _, contact in pairs(contacts or {}) do
        local name
        if contact.object ~= nil and pcall(function() name = contact.object:getName() end) then
            if name ~= nil then
                seen[tostring(name)] = contact.object
            end
        end
    end
    return seen
end

local function is_fighter(unit)
    local fighter = false
    pcall(function()
        fighter = unit:hasAttribute("Fighters") or unit:hasAttribute("Interceptors")
    end)
    return fighter
end

local function range_between(a, b)
    local pa, pb
    if not pcall(function() pa, pb = a:getPoint(), b:getPoint() end) then
        return nil
    end
    if pa == nil or pb == nil then
        return nil
    end
    local dx, dy, dz = pa.x - pb.x, pa.y - pb.y, pa.z - pb.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function report_contacts(hunter_group, targets, source)
    local hunter_name, leader
    if not pcall(function() hunter_name = hunter_group:getName() end)
            or hunter_name == nil then
        return
    end
    if not pcall(function() leader = hunter_group:getUnit(1) end) or leader == nil then
        return
    end
    local side = side_of(leader)
    if side == nil then
        return
    end

    -- Collapse the contacts into the formations they belong to, so a four-ship
    -- holding six bandits is one line and not six.
    local formations = {}
    for _, target in pairs(targets) do
        local target_side = side_of(target)
        if target_side ~= nil and target_side ~= side and is_aircraft(target) then
            local group, name
            if pcall(function() group = target:getGroup() end) and group ~= nil
                    and pcall(function() name = group:getName() end) and name ~= nil then
                formations[tostring(name)] = group
            end
        end
    end

    for name, group in pairs(formations) do
        local key = tostring(hunter_name) .. "->" .. name
        if not announced_contacts[key] then
            local target_leader
            pcall(function() target_leader = group:getUnit(1) end)
            local range = target_leader ~= nil
                and range_between(leader, target_leader) or nil
            if range ~= nil and range <= INTERCEPT_MAX_RANGE_M then
                announced_contacts[key] = true
                local hunter_type, hunter_pilot = unit_fields(leader)
                local bandit_type, bandit_pilot = unit_fields(target_leader)
                -- Only say "intercept" when one is plausible. A BARCAP handed a
                -- contact by datalink eighty miles away does not leave its
                -- racetrack -- knowing is not acting, and claiming otherwise
                -- had the log announcing interceptions that never happened.
                -- The watching kind is most of the traffic, so it gets its own
                -- switch rather than sharing one with the committing kind.
                local committing = range <= INTERCEPT_COMMIT_M
                local verb = committing and "is moving to intercept" or "monitors"
                record({kind = committing and "intercept" or "monitoring",
                        side = side,
                        actor_type = hunter_type, actor_pilot = hunter_pilot,
                        target_type = bandit_type, target_pilot = bandit_pilot,
                        range = math.floor(range), source = source})
                announce(side, committing and "intercepts" or "monitoring",
                    string.format(
                        "%s %s %s at %.0f nm, %s",
                        describe_flight(hunter_group), verb,
                        describe_flight(group, true), range / 1852, source))
            end
        end
    end
end

local function poll_intercepts()
    if not option("intercepts") and not option("monitoring") then
        return
    end
    for _, side in pairs({coalition.side.BLUE, coalition.side.RED}) do
        local groups
        if not pcall(function()
            groups = coalition.getGroups(side, Group.Category.AIRPLANE)
        end) then
            groups = nil
        end
        for _, group in pairs(groups or {}) do
            local unit
            if pcall(function() unit = group:getUnit(1) end) and unit ~= nil
                    and is_fighter(unit) then
                local controller
                if pcall(function() controller = group:getController() end)
                        and controller ~= nil then
                    -- Own radar wins the credit: a target held on both was not
                    -- "handed over", it was found.
                    local radar = detected_names(controller, Controller.Detection.RADAR)
                    report_contacts(group, radar, "found on its own radar")
                    local shared = detected_names(controller, Controller.Detection.DLINK)
                    for name in pairs(radar) do
                        shared[name] = nil
                    end
                    report_contacts(group, shared, "handed over by shared awareness")
                end
            end
        end
    end
end

timer.scheduleFunction(function(_, time)
    pcall(poll_intercepts)
    return time + INTERCEPT_POLL_SECONDS
end, nil, timer.getTime() + INTERCEPT_POLL_SECONDS)

timer.scheduleFunction(function(_, time)
    pcall(flush_ground)
    pcall(forget_old_weapons)
    return time + GROUND_FLUSH_SECONDS
end, nil, timer.getTime() + GROUND_FLUSH_SECONDS)

if logger then
    -- RETRIBUTION_PILOTS is keyed by unit name, so # would report 0.
    local roster = 0
    if type(RETRIBUTION_PILOTS) == "table" then
        for _ in pairs(RETRIBUTION_PILOTS) do
            roster = roster + 1
        end
    end
    logger:info(string.format(
        "Mission Log armed: roster of %d pilots, messages last %ds", roster, DURATION))
end
