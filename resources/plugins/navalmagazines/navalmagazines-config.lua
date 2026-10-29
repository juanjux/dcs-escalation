-- Finite campaign anti-ship stock, staggered release and per-mission salvo limits.
-- Adapted from BradySox/RetLab's naval magazines runtime.
-- Attacks release the target and nearby friendly groups in one hop, never a coalition.
-- Land-attack missiles remain under the separate cruise-missile accounting channel.

if not (dcsRetribution and dcsRetribution.navalMagazines) then
    return
end

local data = dcsRetribution.navalMagazines

-- ROE option id is 0 for every unit category, and the naval value table mirrors the ground one.
-- Read the enums when DCS exposes them, fall back to the documented literals otherwise.
local ROE_ID = (AI and AI.Option and AI.Option.Naval and AI.Option.Naval.id
    and AI.Option.Naval.id.ROE) or 0
local ROE_WEAPON_FREE = 0
local ROE_RETURN_FIRE = 3

-- Defaults. Overridable via the plugin options (dcsRetribution.plugins.navalmagazines).
local RELEASE_MIN = 120 -- s after mission start: the weapons-release window opens
local RELEASE_MAX = 900 -- s after mission start: the weapons-release window closes
local ANNOUNCE = true -- cue the owning coalition when a group goes winchester
-- Attacking one group frees its formation: a screen rides ~2 km off its flagship (measured),
-- the next task force was 59 km away. 0 disables (only the targeted group releases).
local FORMATION_KM = 15
-- Anti-ship missiles one group may fire in a single mission. The magazine bounds the
-- war; this bounds the mission, so a fleet fights a running battle instead of alpha-striking
-- its whole ready loadout in the first minute it is weapons-free. 0 disables.
local SALVO_CAP = 6
local PATTERNS = "HARPOON,RGM_84,AGM_84,EXOCET,MM_38,MM_40,YJ,C_802,C_602,"
    .. "P_500,P_700,P_270,P_1000,KH_35,3M24,3M54,SS_N,NSM,RBS15,OTOMAT"

if dcsRetribution.plugins and dcsRetribution.plugins.navalmagazines then
    local o = dcsRetribution.plugins.navalmagazines
    RELEASE_MIN = tonumber(o.releaseMinS) or RELEASE_MIN
    RELEASE_MAX = tonumber(o.releaseMaxS) or RELEASE_MAX
    if RELEASE_MAX < RELEASE_MIN then
        RELEASE_MAX = RELEASE_MIN
    end
    if o.announceWinchester ~= nil then
        ANNOUNCE = o.announceWinchester
    end
    FORMATION_KM = (tonumber(o.formationReleaseNm) or FORMATION_KM / 1.852) * 1.852 -- NM (UI) -> km
    SALVO_CAP = tonumber(o.salvoPerMission) or SALVO_CAP
    if SALVO_CAP < 0 then
        SALVO_CAP = 0
    end
    if type(o.ashmWeaponPatterns) == "string" and o.ashmWeaponPatterns ~= "" then
        PATTERNS = o.ashmWeaponPatterns
    end
end

-- Mirror-back channel: the base script serializes `naval_magazines_state` into the debrief and
-- Python debits each naval group's persisted magazine by its reported `fired`. One entry per
-- group, updated in place (the shared state pattern), with dirty_state flagged so write_state
-- actually flushes.
naval_magazines_state = naval_magazines_state or {}

local STAGGER = data.stagger == true or data.stagger == "true"
local METERED = data.metered == true or data.metered == "true"

local remaining = {} -- group name -> anti-ship missiles left this mission
local groupSide = {} -- group name -> coalition.side
local groupOrder = {} -- ordered group names, for the release stagger
local fired = {} -- group name -> its naval_magazines_state entry
local released = {} -- group name -> true once weapons-free (stagger or attack)
local underAttack = {} -- group name -> true once the enemy has fired at it
local salvoFired = {} -- group name -> anti-ship missiles fired THIS mission
local salvoDone = {} -- group name -> true once it has spent its per-mission salvo
local winchesterCalled = {} -- group name -> true once it has been called winchester
local overshootFired = {} -- group name -> anti-ship missiles fired past an empty magazine

local function sideOf(name)
    if name == "red" then
        return coalition.side.RED
    end
    return coalition.side.BLUE
end

for _, m in ipairs(data.magazines or {}) do
    if m.group then
        remaining[m.group] = tonumber(m.remaining) or 0
        groupSide[m.group] = sideOf(m.coalition)
        groupOrder[#groupOrder + 1] = m.group
    end
end

-- Split the pattern list once. Matching is plain substring on the upper-cased weapon type name
-- (string.find with plain=true) -- never a Lua pattern, since weapon ids carry magic characters.
local weaponPatterns = {}
for token in string.gmatch(PATTERNS, "[^,]+") do
    local trimmed = token:match("^%s*(.-)%s*$")
    if trimmed ~= "" then
        weaponPatterns[#weaponPatterns + 1] = trimmed:upper()
    end
end

local function isAntiShipWeapon(typeName)
    if type(typeName) ~= "string" then
        return false
    end
    local upper = typeName:upper()
    for _, p in ipairs(weaponPatterns) do
        if string.find(upper, p, 1, true) then
            return true
        end
    end
    return false
end

local function setRoe(groupName, value)
    pcall(function()
        local grp = Group.getByName(groupName)
        if grp and grp:isExist() then
            grp:getController():setOption(ROE_ID, value)
        end
    end)
end

local function navMsg(side, text)
    pcall(trigger.action.outTextForCoalition, side, text, 15)
end

local function recordFired(groupName, count)
    local entry = fired[groupName]
    if not entry then
        entry = { group = groupName, fired = 0 }
        fired[groupName] = entry
        naval_magazines_state[#naval_magazines_state + 1] = entry
    end
    entry.fired = entry.fired + count
    dirty_state = true
end

-- N1: release one group to weapons-free. A group whose magazine is already dry is deliberately
-- left at ReturnFire -- there is nothing to release it for. Idempotent: an attack release
-- earlier makes the scheduled release a no-op.
local function releaseGroup(groupName)
    if released[groupName] or salvoDone[groupName] then
        return nil
    end
    if METERED and (remaining[groupName] or 0) <= 0 then
        env.info(string.format(
            "NAVALMAGAZINES|: %s stays ReturnFire at release (magazine dry)", groupName))
        return nil
    end
    released[groupName] = true
    setRoe(groupName, ROE_WEAPON_FREE)
    env.info(string.format("NAVALMAGAZINES|: %s released weapons-free", groupName))
    return nil
end

-- Release-on-attack keeps held and winchester groups able to defend. A dry group
-- released this way may overshoot its magazine defending itself, which stays counted.
-- Returns true when this call is what freed the group (never cascades on its own).
local function freeGroup(groupName, reason)
    if underAttack[groupName] then
        return false
    end
    underAttack[groupName] = true
    released[groupName] = true
    setRoe(groupName, ROE_WEAPON_FREE)
    env.info(string.format(
        "NAVALMAGAZINES|: %s %s -- released weapons-free", groupName, reason))
    return true
end

-- A managed group's position (its first alive unit), or nil if it is gone.
local function groupPoint(groupName)
    local ok, point = pcall(function()
        local grp = Group.getByName(groupName)
        if not (grp and grp:isExist()) then
            return nil
        end
        for _, unit in ipairs(grp:getUnits() or {}) do
            if unit and unit:isExist() then
                return unit:getPoint()
            end
        end
        return nil
    end)
    if ok then
        return point
    end
    return nil
end

-- The escort screen fights for its flagship: free every managed friendly group within
-- FORMATION_KM of the attacked one. ONE HOP -- these are freed via freeGroup, which does not
-- call back into here, so an attack can never ripple across the map.
local function releaseFormationAround(groupName)
    if FORMATION_KM <= 0 then
        return
    end
    local origin = groupPoint(groupName)
    if not origin then
        return
    end
    local limit = FORMATION_KM * 1000
    for _, other in ipairs(groupOrder) do
        if other ~= groupName
            and not underAttack[other]
            and groupSide[other] == groupSide[groupName]
        then
            local point = groupPoint(other)
            if point then
                local dx = point.x - origin.x
                local dz = point.z - origin.z
                if math.sqrt(dx * dx + dz * dz) <= limit then
                    freeGroup(other, "in the attacked formation")
                end
            end
        end
    end
end

local function releaseUnderAttack(groupName)
    if freeGroup(groupName, "under attack") then
        releaseFormationAround(groupName)
    end
end

-- Spread the releases evenly across the window rather than rolling each independently, so a
-- small fleet cannot randomly land every release in the same few seconds (the release stagger
-- lesson -- everything firing in one frame was itself a measured problem).
local function releaseTime(index, total)
    if total <= 1 or RELEASE_MAX <= RELEASE_MIN then
        return RELEASE_MIN
    end
    return RELEASE_MIN + (RELEASE_MAX - RELEASE_MIN) * (index - 1) / (total - 1)
end

-- Count one real anti-ship release: against the per-mission salvo (both tiers) and,
-- with N2 on, against the campaign magazine. A group that reaches either limit is held
-- at ReturnFire -- unless the enemy is shooting at it, in which case it keeps its
-- weapons-free and the overshoot is still counted.
local function chargeShot(groupName)
    if remaining[groupName] == nil then
        return -- not a managed group
    end
    local salvo = (salvoFired[groupName] or 0) + 1
    salvoFired[groupName] = salvo
    -- Read before the decrement: this shot came out of an ALREADY-empty magazine,
    -- which is the overshoot the cap below bounds.
    local wasDry = METERED and (remaining[groupName] or 0) <= 0
    local dry = false
    if METERED then
        recordFired(groupName, 1)
        local left = remaining[groupName] - 1
        if left < 0 then
            left = 0
        end
        remaining[groupName] = left
        dry = left <= 0
    end
    if dry then
        if not underAttack[groupName] then
            setRoe(groupName, ROE_RETURN_FIRE)
        elseif wasDry then
            -- A dry group may exceed its campaign stock to defend itself, but
            -- no more than one extra salvo. Every real shot remains charged.
            local over = (overshootFired[groupName] or 0) + 1
            overshootFired[groupName] = over
            if SALVO_CAP > 0 and over == SALVO_CAP then
                setRoe(groupName, ROE_RETURN_FIRE)
                env.info(string.format(
                    "NAVALMAGAZINES|: %s overshoot cap (%d past empty) -- holding",
                    groupName, over))
            end
        end
        -- Announce once even when defensive overshoot produces more SHOT events.
        if not winchesterCalled[groupName] then
            winchesterCalled[groupName] = true
            env.info(string.format(
                "NAVALMAGAZINES|: %s WINCHESTER anti-ship", groupName))
            if ANNOUNCE then
                navMsg(groupSide[groupName] or coalition.side.BLUE, string.format(
                    "WINCHESTER -- %s has expended its anti-ship missiles. "
                    .. "No rearm this war.", groupName))
            end
        end
        return
    end
    -- Salvo spent: quiet for the rest of the mission, still loaded for the war. Log only --
    -- a group falling silent mid-mission is routine, unlike going winchester for good.
    if SALVO_CAP > 0 and not salvoDone[groupName] and salvo >= SALVO_CAP then
        salvoDone[groupName] = true
        if not underAttack[groupName] then
            setRoe(groupName, ROE_RETURN_FIRE)
        end
        env.info(string.format(
            "NAVALMAGAZINES|: %s salvo complete (%d this mission) -- holding", groupName,
            salvo))
    end
end

-- The managed group a world object belongs to, or nil. pcall-guarded: a weapon's target
-- can be scenery/a static with no getGroup.
local function managedGroupOfUnit(obj)
    if not obj then
        return nil
    end
    local ok, name = pcall(function()
        local grp = obj.getGroup and obj:getGroup() or nil
        return grp and grp:getName() or nil
    end)
    if ok and name and groupSide[name] ~= nil then
        return name
    end
    return nil
end

-- Friendly-fire guard: only enemy fire releases a held group.
local function isEnemyOf(initiator, groupName)
    local ok, side = pcall(function()
        return initiator:getCoalition()
    end)
    if not ok or side == nil then
        return false
    end
    return side ~= groupSide[groupName]
end

local handler = {}

function handler:onEvent(event)
    if not event then
        return
    end
    local ok, err = pcall(function()
        if event.id == world.event.S_EVENT_SHOT then
            local initiator, weapon = event.initiator, event.weapon
            if not weapon then
                return
            end
            -- Charge a real anti-ship release against the shooter's salvo and magazine.
            if initiator and isAntiShipWeapon(weapon:getTypeName()) then
                local name = managedGroupOfUnit(initiator)
                if name then
                    chargeShot(name)
                end
            end
            -- Release-on-attack: ANY enemy weapon aimed at a managed group frees it to
            -- defend -- not just anti-ship ordnance (a Maverick or an LGB is an attack too).
            local tOk, target = pcall(function()
                return weapon.getTarget and weapon:getTarget() or nil
            end)
            if tOk and target then
                local name = managedGroupOfUnit(target)
                if name and initiator and isEnemyOf(initiator, name) then
                    releaseUnderAttack(name)
                end
            end
        elseif event.id == world.event.S_EVENT_HIT then
            -- The backstop for weapons that carry no SHOT target (dumb bombs, guns). A nil
            -- initiator (debris, an unknown shooter) still releases -- being hit is reason
            -- enough to defend; a known FRIENDLY hit never does.
            local name = managedGroupOfUnit(event.target)
            if name and (not event.initiator or isEnemyOf(event.initiator, name)) then
                releaseUnderAttack(name)
            end
        end
    end)
    if not ok then
        env.warning("navalmagazines: shot handler error (continuing): " .. tostring(err))
    end
end

local ok, err = pcall(function()
    -- The handler always runs: N2 needs the shot metering, and release-on-attack must
    -- free a held group under either tier.
    world.addEventHandler(handler)
    if METERED then
        -- A group that starts the mission dry never gets to open fire with missiles it does not
        -- have. With the stagger on it is simply never released; without it, the generator left
        -- every ship weapons-free, so pull the dry ones back now.
        if not STAGGER then
            for _, name in ipairs(groupOrder) do
                if (remaining[name] or 0) <= 0 then
                    setRoe(name, ROE_RETURN_FIRE)
                end
            end
        end
    end
    if STAGGER then
        for index, name in ipairs(groupOrder) do
            timer.scheduleFunction(
                releaseGroup, name,
                timer.getTime() + releaseTime(index, #groupOrder)
            )
        end
    end
    env.info(string.format(
        "NAVALMAGAZINES|: armed -- %d naval group(s), stagger %s (%ds-%ds), metered %s, "
        .. "salvo cap %s",
        #groupOrder, tostring(STAGGER), RELEASE_MIN, RELEASE_MAX, tostring(METERED),
        SALVO_CAP > 0 and tostring(SALVO_CAP) or "off"))
end)
if not ok then
    env.error("NAVALMAGAZINES|: setup error: " .. tostring(err))
end
