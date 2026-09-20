---------------------------------------------------------------------------------------------------
-- GPS jamming (CLAUDE.md 85) -- runtime.
--
-- DCS exposes no GPS receiver, so a jammer cannot be made to degrade a jet's navigation or a
-- weapon's guidance through any engine API. What it CAN do is watch the weapon. This script:
--
--   1. hooks S_EVENT_SHOT and starts tracking any satellite-guided store (the emitted
--      weaponPatterns -- JDAM/JSOW/JASSM/SLAM-ER/KAB-*S; never laser, TV or IR weapons);
--   2. rolls ONCE, the first sample the store is inside a live enemy jammer's reach, whether
--      this one is degraded (the roll is remembered either way, so a long glide does not
--      re-roll itself into a certainty);
--   3. lets the degraded store fly its entire normal profile, and only in the last moments
--      before impact destroys it and detonates it a scored distance off the aimpoint.
--
-- The pilot sees the release, the fall and the bang -- just in the wrong place. Miss distance
-- grows with jamming strength (deeper inside the bubble = further off), so a weapon clipping
-- the edge of a bubble is nudged and one released over the jammer is thrown well clear.
--
-- No phantom spawns / no invented losses: the store is a REAL weapon from a REAL jet, and this
-- script owns no kills beyond producing the miss explosion. Any damage that explosion does is
-- ordinary DCS damage, recorded natively. Killing the jammer takes the site out of the site
-- list on the very next check, so accuracy returns inside the same mission.
--
-- Symmetric: a site degrades the OPPOSING coalition's weapons only. Its owner's own
-- satellite-guided stores are never touched.
--
-- Reads plugin options from dcsRetribution.plugins.gpsjamming and its world from
-- dcsRetribution.gpsJamming (emitted only when the setting is on and a live site exists, so
-- an ordinary mission loads this file and does nothing). Definition order matters (Lua 5.1):
-- helpers precede use. pcall-guarded throughout so a hiccup never takes the mission down.
---------------------------------------------------------------------------------------------------

local DEGRADE_CHANCE = 0.85 -- probability a store inside a bubble is degraded (rolled once)
local TERMINAL_AGL = 30.48 -- m (100 ft): destroy the spoofed store at/below this height
local MISS_POWER = 400 -- fallback explosion power (kg TNT eq) when the weapon reports no warhead
local MISS_POWER_SCALE = 1.0 -- multiplier on the weapon's OWN explosive mass
local CUE_SHOOTER = true -- one text cue to the firing flight on its first spoof
local GRACE = 60 -- s before any weapon can be degraded
local TRACK_STEP = 0.2 -- s: weapon-track sample step
local MAX_TRACK = 2400 -- s: give up tracking a released weapon after this
-- 2400 s is sized off the slowest thing on the list: a cruise missile at ~250 m/s
-- covers 600 km, more than the 250 nm a ship raid is planned to. At 600 s it covered
-- 150 km and every long shot was dropped before it ever reached the bubble.
local MIN_MISS_FRACTION = 0.35 -- a weapon clipping the bubble edge still misses by this much

local cfg = (dcsRetribution and dcsRetribution.gpsJamming) or nil

if dcsRetribution and dcsRetribution.plugins and dcsRetribution.plugins.gpsjamming then
    local o = dcsRetribution.plugins.gpsjamming
    if tonumber(o.degradeChancePct) then
        DEGRADE_CHANCE = tonumber(o.degradeChancePct) / 100
    end
    if tonumber(o.terminalAglFt) then
        TERMINAL_AGL = tonumber(o.terminalAglFt) * 0.3048 -- ft (UI) -> m
    end
    MISS_POWER = tonumber(o.missPower) or MISS_POWER
    if tonumber(o.missPowerScalePct) then
        MISS_POWER_SCALE = tonumber(o.missPowerScalePct) / 100
    end
    if o.cueShooter ~= nil then
        CUE_SHOOTER = o.cueShooter and true or false
    end
    GRACE = tonumber(o.startGraceS) or GRACE
    TRACK_STEP = tonumber(o.trackStepS) or TRACK_STEP
    MAX_TRACK = tonumber(o.maxTrackS) or MAX_TRACK
end

local function log(msg)
    env.info("DCSRetribution|GPSJamming: " .. tostring(msg))
end

---------------------------------------------------------------------------------------------------
-- Sites.
---------------------------------------------------------------------------------------------------

-- Emitted site records -> { x, z, reach, miss, side, units }. The emitter frame is the pydcs
-- Point (x north, y east); the DCS world frame calls the second axis z, hence y -> z here.
local sites = {}

local function buildSites()
    if not (cfg and type(cfg.sites) == "table") then
        return
    end
    for _, rec in ipairs(cfg.sites) do
        local units = {}
        if type(rec.units) == "table" then
            for _, u in ipairs(rec.units) do
                units[#units + 1] = u
            end
        end
        local reach = tonumber(rec.reachM) or 0
        if reach > 0 and #units > 0 then
            sites[#sites + 1] = {
                name = rec.name or "GPS jammer",
                -- The OWNER's side. A weapon is degraded only if its shooter is on
                -- the other one.
                side = (rec.coalition == "blue") and coalition.side.BLUE or coalition.side.RED,
                x = tonumber(rec.x) or 0,
                z = tonumber(rec.y) or 0,
                reach = reach,
                miss = tonumber(rec.missRadiusM) or 200,
                units = units,
            }
        end
    end
end

-- A site jams only while a JAMMER VEHICLE is still alive. Re-checked (cheaply, and only when a
-- tracked weapon is actually in the air) so a jammer killed mid-mission stops denying GPS on
-- the very next weapon -- the reward for finding and striking it.
--
-- Deliberately per-UNIT, not per-group: a jammer shares its DCS group with the rest of its site
-- (its escort, and -- in the intended laydown -- the radar that puts the site on RWR), so a
-- group-level check would keep jamming on the strength of a surviving truck beside the wreck of
-- the actual jammer. The player must be able to kill the thing that is jamming them.
local function siteAlive(site)
    for i = 1, #site.units do
        local ok, u = pcall(Unit.getByName, site.units[i])
        if ok and u and u:isExist() then
            -- getLife is not on every fake/mod object; a unit that exists but cannot
            -- report health counts as alive (fail toward "the jammer still works",
            -- never toward a silent feature-off).
            local okLife, life = pcall(function()
                return u:getLife()
            end)
            if not okLife or life == nil or life > 0 then
                return true
            end
        end
    end
    return false
end

-- The strongest live enemy jammer covering `pos`, as a 0..1 strength (1 at the emitter, 0 at
-- the edge of its reach). Returns nil when the point is clear of every live enemy bubble.
local function jammingAt(pos, shooterSide)
    local best, bestSite = nil, nil
    for i = 1, #sites do
        local site = sites[i]
        if site.side ~= shooterSide then
            local dx, dz = pos.x - site.x, pos.z - site.z
            local dist = math.sqrt(dx * dx + dz * dz)
            if dist <= site.reach and siteAlive(site) then
                local strength = 1 - (dist / site.reach)
                if best == nil or strength > best then
                    best, bestSite = strength, site
                end
            end
        end
    end
    if best == nil then
        return nil
    end
    return best, bestSite
end

---------------------------------------------------------------------------------------------------
-- Weapon matching.
---------------------------------------------------------------------------------------------------

-- Plain, case-insensitive substring finds against the weapon type name. NEVER a Lua pattern:
-- weapon names carry "-" and "(", which a pattern match reads as magic (the rednet lesson).
local patterns = {}
local function buildPatterns()
    if not (cfg and type(cfg.weaponPatterns) == "table") then
        return
    end
    for _, pat in ipairs(cfg.weaponPatterns) do
        if type(pat) == "string" and pat ~= "" then
            patterns[#patterns + 1] = string.lower(pat)
        end
    end
end

-- The miss detonation is the store's OWN warhead, so a 2000 lb JDAM craters like one
-- and a 500 lb JDAM does not. DCS reports this on the weapon descriptor
-- (`desc.warhead.explosiveMass`, kg TNT equivalent -- exactly the unit
-- trigger.action.explosion wants); `mass` is the whole warhead and is the next best
-- thing. A store that reports neither -- a mod weapon with a thin descriptor -- falls
-- back to the configured flat power, which is precisely the pre-scaling behaviour, so
-- this can only ever add fidelity.
local function warheadPower(wpn)
    local ok, desc = pcall(function()
        return wpn:getDesc()
    end)
    if ok and type(desc) == "table" and type(desc.warhead) == "table" then
        local kg = tonumber(desc.warhead.explosiveMass) or tonumber(desc.warhead.mass)
        if kg and kg > 0 then
            return kg * MISS_POWER_SCALE, true
        end
    end
    return MISS_POWER, false
end

local function isSatelliteGuided(typeName)
    local t = string.lower(typeName or "")
    if t == "" then
        return false
    end
    for i = 1, #patterns do
        if string.find(t, patterns[i], 1, true) then
            return true
        end
    end
    return false
end

---------------------------------------------------------------------------------------------------
-- Tracking.
---------------------------------------------------------------------------------------------------

local tracked = {} -- { wpn, side, groupName, shotTime, pos, vel, decided, degraded, miss }
local trackerArmed = false
local cued = {} -- group names already told once

local function cueShooter(track, site)
    if not CUE_SHOOTER or not track.groupName or cued[track.groupName] then
        return
    end
    cued[track.groupName] = true
    local ok, g = pcall(Group.getByName, track.groupName)
    if not (ok and g and g:isExist()) then
        return
    end
    pcall(
        trigger.action.outTextForGroup,
        g:getID(),
        "GPS DENIED -- weapon guidance degraded near "
            .. tostring(site and site.name or "the target")
            .. ". Expect misses; laser/TV deliveries are unaffected.",
        20
    )
end

-- The scored miss: a random bearing at a distance scaled by jamming strength, so a store
-- clipping the bubble edge is nudged and one released over the emitter is thrown well clear.
-- Rolled ONCE, when the weapon is first degraded, so the aimpoint error is a property of that
-- release rather than something that wanders every tick.
local function rollMiss(site, strength)
    local span = MIN_MISS_FRACTION + (1 - MIN_MISS_FRACTION) * strength
    local dist = site.miss * span
    local bearing = math.random() * 2 * math.pi
    return { dx = math.cos(bearing) * dist, dz = math.sin(bearing) * dist }
end

-- Put the store down off the aimpoint: remove the real weapon, detonate at the offset point.
local function detonateOffTarget(track)
    local p = track.pos
    if not p then
        return
    end
    local x = p.x + track.miss.dx
    local z = p.z + track.miss.dz
    local okH, h = pcall(land.getHeight, { x = x, y = z })
    if not okH or not h then
        h = 0
    end
    -- Order matters: destroy FIRST so the real store can never also detonate on the aimpoint
    -- (a double bang would read as the weapon working AND being spoofed).
    pcall(function()
        track.wpn:destroy()
    end)
    pcall(trigger.action.explosion, { x = x, y = h, z = z }, track.power or MISS_POWER)
end

local function sample(track)
    local okExist, exists = pcall(function()
        return track.wpn:isExist()
    end)
    if not (okExist and exists) then
        return false
    end
    local okPos, p = pcall(function()
        return track.wpn:getPoint()
    end)
    if okPos and p then
        track.pos = p
    end
    local okVel, v = pcall(function()
        return track.wpn:getVelocity()
    end)
    if okVel and v then
        track.vel = v
    end
    return true
end

-- Height above ground at the weapon's current position.
local function aglOf(pos)
    local ok, h = pcall(land.getHeight, { x = pos.x, y = pos.z })
    if not ok or not h then
        h = 0
    end
    return pos.y - h
end

-- The terminal gate is PREDICTIVE: fire when the store would already be through the floor by
-- the next sample. A fast weapon can cover 200+ m in one step, so a plain "agl <= floor" test
-- would let it detonate on the aimpoint between samples and the jamming would silently fail.
local function inTerminalPhase(track)
    if not track.pos then
        return false
    end
    local agl = aglOf(track.pos)
    local floor = TERMINAL_AGL
    if track.vel then
        local descent = -(track.vel.y or 0)
        if descent > 0 then
            local reach = descent * TRACK_STEP * 2
            if reach > floor then
                floor = reach
            end
        end
    end
    return agl <= floor
end

local function trackTick()
    local now = timer.getTime()
    local i = 1
    while i <= #tracked do
        local track = tracked[i]
        local drop = false

        if not sample(track) then
            -- Gone: it impacted (or was shot down) before the terminal gate. A degraded store
            -- that gets here simply hit normally -- deliberately NOT re-detonated, because we
            -- cannot know it did not already do its damage, and inventing a second explosion
            -- would be a phantom effect.
            drop = true
        elseif (now - track.shotTime) > MAX_TRACK then
            drop = true
        elseif now >= GRACE then
            -- (Inside the startup grace a store is tracked but never degraded.)
            if not track.decided and track.pos then
                local strength, site = jammingAt(track.pos, track.side)
                if strength then
                    track.decided = true
                    if math.random() < DEGRADE_CHANCE then
                        track.degraded = true
                        track.miss = rollMiss(site, strength)
                        cueShooter(track, site)
                    end
                end
            end
            if track.degraded and inTerminalPhase(track) then
                detonateOffTarget(track)
                drop = true
            end
        end

        if drop then
            table.remove(tracked, i)
        else
            i = i + 1
        end
    end
    if #tracked == 0 then
        trackerArmed = false
        return nil -- nothing in the air; re-armed by the next qualifying release
    end
    return now + TRACK_STEP
end

local function trackLoop()
    local ok, nextT = pcall(trackTick)
    if not ok then
        env.warning("gpsjamming: track error (continuing): " .. tostring(nextT))
        trackerArmed = false
        return nil
    end
    return nextT
end

---------------------------------------------------------------------------------------------------
-- Release detection.
---------------------------------------------------------------------------------------------------

local function onShot(event)
    if event.id ~= world.event.S_EVENT_SHOT then
        return
    end
    local wpn, shooter = event.weapon, event.initiator
    if not (wpn and shooter) then
        return
    end
    local okName, typeName = pcall(function()
        return wpn:getTypeName()
    end)
    if not (okName and isSatelliteGuided(typeName)) then
        return
    end
    local okSide, side = pcall(function()
        return shooter:getCoalition()
    end)
    if not okSide then
        return
    end
    local groupName = nil
    pcall(function()
        local g = shooter:getGroup()
        if g then
            groupName = g:getName()
        end
    end)
    local power, fromWarhead = warheadPower(wpn)
    tracked[#tracked + 1] = {
        wpn = wpn,
        side = side,
        groupName = groupName,
        shotTime = timer.getTime(),
        decided = false,
        degraded = false,
        -- Resolved at RELEASE, not at impact: the weapon object may already be gone
        -- by the time we detonate the miss.
        power = power,
    }
    if not fromWarhead then
        log(
            string.format(
                "%s reports no warhead mass -- miss uses the fallback %d kg",
                tostring(typeName),
                MISS_POWER
            )
        )
    end
    if not trackerArmed then
        trackerArmed = true
        timer.scheduleFunction(trackLoop, {}, timer.getTime() + TRACK_STEP)
    end
end

---------------------------------------------------------------------------------------------------
-- Arm.
---------------------------------------------------------------------------------------------------

if cfg then
    buildSites()
    buildPatterns()
end

if #sites > 0 and #patterns > 0 then
    world.addEventHandler({
        onEvent = function(self, event)
            local ok, err = pcall(onShot, event)
            if not ok then
                env.warning("gpsjamming: shot handler error (continuing): " .. tostring(err))
            end
        end,
    })
    log(
        string.format(
            "armed -- %d jamming site(s), %d weapon pattern(s), %.0f%% degrade, "
                .. "terminal %.0fm AGL, grace %ds",
            #sites,
            #patterns,
            DEGRADE_CHANCE * 100,
            TERMINAL_AGL,
            GRACE
        )
    )
else
    log("no GPS jamming data this mission -- inert")
end
