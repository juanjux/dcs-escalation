--[[
Troops in Contact (TIC)

Formerly known as Grendel's Large Scale Combat Operations (GLSCO)

A script designed to transform your ground battles into dynamic, believable engagements. TIC helps mission creators 
quickly set up ground fights that look and feel like real combat, where both sides are exchanging fire, and there’s 
still plenty of action left for players to engage with.

For more info, read pdf included with this script.


--------------------------------------------------------------------------------
MIT License
--------------------------------------------------------------------------------

Copyright (c) 2025 Grendel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

================================================================================
Version Changes
================================================================================

v1.0 - 2025-05-09

   * Initial release

v1.1 - 2025-05-21

   * Fixed an issue where air defense units would not engage airborne threats.

   * Added a new waypoint command: "direct" – allows a formation to skip all intermediate 
     waypoints and move straight to this one.

   * Improved unit behavior during movement: units will now open fire while en route if 
     their ROE is set to KILL. Previously, they would wait until reaching their destination.

   * Added a new waypoint command: "strength" – defines a combat effectiveness threshold for 
	 the formation. If the formation’s strength drops below the specified value, it will proceed 
	 to this waypoint. When used with "direct", this enables retreat logic for formations 
	 under heavy losses.
	 
   * Fixed a minor bug that caused nil errors in the log when a unit was destroyed 
     under certain conditions.
	 
   * Fixed bug where units "riding" inside an IFV that is destroyed would not reach
     Dead state.

--]]

local version = "v1.1"

env.info("TIC Script BEGIN " .. version)

if GLSCO == nil then GLSCO = {} end

-- Prefix
GLSCO.Keyword = "TIC"
GLSCO.Bookend = "#"

-- Commands for custom maneuvers
GLSCO.MarkSourceLabel = "from"
GLSCO.MarkDestinationLabel = "to"

-- Global settings
GLSCO.Settings = 
{
   -- Have to constantly poll for status updates, but instead
   -- of making poll interval a fixed number, it can fluxuate
   -- between these two min and max values.  That way, 
   -- as number of units increases, we don't get fps spike due
   -- to everything polling at the same time.
   ARRIVAL_MIN_INTERVAL = 10,
   ARRIVAL_MAX_INTERVAL = 20,
   
   -- Units are issued commands to move to a coordinate, but due to the 
   -- potential for pathing problems, a unit is considered "arrived" at 
   -- coordinate if it is within this many meters of the destination.
   ARRIVAL_RADIUS_METERS = 10,
   
   -- When unit "shifting" is enabled, units will move around near their
   -- "home" coordinate (which is another name for the coordinate near their current waypoint).
   -- To ensure units don't stray too far, they will remain within this many meters.
   HOME_MAX_RADIUS_METERS = 100,
   
   -- Troop carriers will only wait for this max number of seconds while infantry is mounting.
   DEPLOY_WAIT_SECONDS = 60,
}

-- Settings that can be overriden per unit type.
GLSCO.GENERIC_PROFILE = 
{
   ["default"] = 
   {
      -- Number ammo expended per turn.
      SalvoQty = 6, 
	  
	  -- Top speed of unit
      TopSpeedKMH = 60, 
	  
	  -- What percentage of the time is this unit shifting vs doing something else?
      ShiftChance = 0.50, 
	  
	  -- Defines accuracy (in meters) of rounds fired near enemy
      InnerAimRadius = 2,
      OuterAimRadius = 30,
	  
	  -- Most of the time we don't want to allow unit to be controlled by DCS AI targeting logic,
	  -- however there are exceptions.
      WeaponFree = false,
      
      --KillRange = UTILS.NMToMeters(0.5),
   },
   
   -- IFV
   ["IFV BMP-3"] = 
   {
      -- These are more like tanks, so need to decrease.
      SalvoQty = 1, 
   },
   
   -- APC
   ["APC BTR-80"] = 
   {
      SalvoQty = 15,
   },
   ["APC BTR-82A"] = 
   {
      SalvoQty = 15,
   },
   ["APC M113"] = 
   {
      SalvoQty = 15,
   },
}

GLSCO.INFANTRY_PROFILE = 
{
   ["default"] = 
   {
      SalvoQty = 5,
	  
	  -- Seems to be a good value for a soldier at running speed.
      TopSpeedKMH = 13,
	  
	  -- Small ammo belt, so shouldn't shoot as often.
      ShiftChance = 0.75,
	  
      InnerAimRadius = 2,
      OuterAimRadius = 10,
      WeaponFree = false,
      --KillRange = 500,
   },
}

GLSCO.TANK_PROFILE = 
{
   ["default"] = 
   {
      -- Tanks have small amount of ammo, so must preserve
      SalvoQty = 1,
      TopSpeedKMH = 60,
      ShiftChance = 0.60,
      InnerAimRadius = 2,
      OuterAimRadius = 50,
      WeaponFree = false,
      --KillRange = UTILS.NMToMeters(0.5),
   },
}

-- Profile for Air Defense Units
GLSCO.AD_PROFILE = 
{
   ["default"] = 
   {
      SalvoQty = 0,
      TopSpeedKMH = 60,
      ShiftChance = 0.25,
      InnerAimRadius = 0,
      OuterAimRadius = 0,
	  
	  -- Let the DCS AI engage air threats
      WeaponFree = true,
      --KillRange = UTILS.NMToMeters(0.5),
   },
   
   --[[
   ["SAM SA-9 Strela 1 \"Gaskin\" TEL"] = 
   {
      ShiftChance = 0.75,
      WeaponFree = true,
   },
   ["SAM SA-19 Tunguska \"Grison\" "] = 
   {
      ShiftChance = 0.75,
      WeaponFree = true,
   },
   ["SPAAA ZSU-23-4 Shilka \"Gun Dish\""] = 
   {
      ShiftChance = 0.75,
      WeaponFree = true,
   },
   ["SAM Avenger (Stinger)"] = 
   {
      ShiftChance = 0.75,
      WeaponFree = true,
   },
   --]]
}

GLSCO.Deployment = 
{
   LOAD = 1,
   UNLOAD = 2,
}

function GLSCO.GetRGB(_coalition)

   local rgb = {0.5, 0.5, 0.5}

   if (_coalition == coalition.side.BLUE) then
      rgb = {0, 0, 1}
   elseif (_coalition == coalition.side.RED) then
      rgb = {1, 0, 0}
   end

   return rgb
   
end

function GLSCO.IsSameCoordinate(coord1, coord2)

   if coord1 == nil or coord2 == nil then return false end
   
   return coord1:IsAtCoordinate2D(coord2, 0.5)

end

-- ========================================================================================================================
-- GLSCO_STOPWATCH
-- ========================================================================================================================
-- Simple stopwatch object that can start a timer and report how much time has elapsed.
-- 
GLSCO_STOPWATCH = {}

function GLSCO_STOPWATCH:GetElapsedSeconds()

   if self.start == nil then return nil end
   
   return timer.getTime() - self.start

end

function GLSCO_STOPWATCH:New()

   local inst = 
   {
      start = nil
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

function GLSCO_STOPWATCH:Start()

   self.start = timer.getTime()

end

-- ========================================================================================================================
-- GLSCO_SPAWN
-- ========================================================================================================================
-- Utility object used to break apart DCS groups into multiple groups with a single unit in each.
-- 
GLSCO_SPAWN = 
{
   index = 1
}

function GLSCO_SPAWN.getNextIndex()

   local next = GLSCO_SPAWN.index
   GLSCO_SPAWN.index = GLSCO_SPAWN.index+1
   return next

end

function GLSCO_SPAWN:CreateSpawnTemplate(group)

   if group == nil then
      return nil
   end
   
   local groupTemplate = group:GetTemplate()
   local newTemplate = UTILS.DeepCopy(groupTemplate)
   local groupPoints = UTILS.DeepCopy(groupTemplate.route.points[1])

   newTemplate.groupId = 1
   newTemplate.tasks = {}
   newTemplate.route.points = 
   {
      groupPoints
   }
   newTemplate.lateActivation = true
   
   return newTemplate
   
end

function GLSCO_SPAWN:CreateSpawn(template, name)

   local newName = name.."-"..GLSCO_SPAWN.getNextIndex()
   local spawn = SPAWN:NewFromTemplate(template, newName, nil, false)
                      --:InitGrouping(1)
                      :InitSkill("Excellent")
                      --:InitCountry(country.id.USA)
                      --:InitCategory(Group.Category.GROUND)
                      --:InitCoalition(coalition.side.BLUE)

   return spawn

end

--[[
function GLSCO_SPAWN.JoinGroups(groups)

end
--]]

function GLSCO_SPAWN.DisjoinGroup(group)

   if group == nil then
      return nil
   end
   
   local spawns = {}
   local groupTemplate = group:GetTemplate()
   
   for index, unit in ipairs(group:GetUnits()) do
   
      local unitTemplate = unit:GetTemplate()

      local newTemplate = UTILS.DeepCopy(groupTemplate)
      newTemplate.x = unitTemplate.x
      newTemplate.y = unitTemplate.y

      local groupPoints = UTILS.DeepCopy(groupTemplate.route.points[1])
      groupPoints.x = unitTemplate.x
      groupPoints.y = unitTemplate.y
      
      newTemplate.groupId = 1
      newTemplate.tasks = {}
      newTemplate.route.points = 
      {
         groupPoints
      }
      newTemplate.units = 
      {
         unitTemplate
      }
      newTemplate.lateActivation = true
      
      
      local newName = groupTemplate.name.."-"..GLSCO_SPAWN.getNextIndex()
      local spawn = SPAWN:NewFromTemplate(newTemplate, newName, nil, false)
                         --:InitGrouping(1)
                         :InitSkill("Excellent")

      table.insert(spawns, spawn)
   
   end
   
   return spawns

end

function GLSCO_SPAWN.DisjoinGroupAndSpawn(group)

   local spawns = GLSCO_SPAWN.DisjoinGroup(group)
   if spawns == nil then
      return nil
   end
   
   if group:IsActive() and group:IsAlive() then
      group:Destroy()
   end
   
   local groups = {}
   for _, spawn in ipairs(spawns) do
      local group = spawn:Spawn()
      table.insert(groups, group)
   end
   
   return groups

end

-- ========================================================================================================================
-- GLSCO_COMBATANT
-- ========================================================================================================================
-- The smallest scale ground unit controlled by this scripting.  A combatant essentially controls a 
-- DCS Group.  However, it is recommended that this object controls a DCS Group that contains only one 
-- DCS Unit.  Formations are better maintained and less likely to get stuck on terrain if each unit 
-- acts independently.
-- 
-- Each combatant is controlled by a state machine (MOOSE FSM) so that each combatant can act
-- autonomously from one other.  Though they "act" independently, they still attempt to maintain
-- their formation shape as the move across the map.
GLSCO_COMBATANT = {}

-- Rules of Engagement
GLSCO_COMBATANT.ROE = 
{
   -- Hold fire
   HOLD = "Hold",
   
   -- Create a convincing battle, but poor accuracy rarely kills enemy
   SIMULATE = "Simulate",
   
   -- Use DCS AI logic to find and destroy enemy targets
   KILL = "Kill"
}

-- Dummy object that represents an IFV carrier that is assigned to a combatant that isn't 
-- associated with a real carrier.  Used simply to make the code easier to read.
GLSCO_COMBATANT_DUMMY = {}

-- Since this carrier is fake, will always return false
function GLSCO_COMBATANT_DUMMY:IsAlive()

   return false

end

function GLSCO_COMBATANT:GetID()

   if not self.group then return nil end

   return self.group:GetTemplate().groupId

end

function GLSCO_COMBATANT:GetName()

   -- I need to cache names since dismounted infantry may get a slightly different name.
   if self.cache.name ~= nil then return self.cache.name end

   if self.group then
      self.cache.name = self.group:GetName()
   end

   return self.cache.name or ""

end

function GLSCO_COMBATANT:GetCoalition()

   if self.cache.coalition ~= nil then return self.cache.coalition end

   if self.group then
      self.cache.coalition = self.group:GetCoalition()
   end

   return self.cache.coalition or coalition.side.NEUTRAL

end

-- Used as key into unit profiles
function GLSCO_COMBATANT:GetDisplayName()

  if not self.group then return "" end

  if not self.displayName then
     local units = self.group:GetUnits()

     if units and units[1] then
        self.displayName = units[1]:GetDesc().displayName or ""
     end
  end

  return self.displayName or ""

end

function GLSCO_COMBATANT:GetCoordinate()

   -- If infantry is inside a carrier, it doesn't have a coordinate, so we'll return
   -- the coordinate of the carrier.
   if self:IsRiding() and self.carrier:IsAlive() then 
      return self.carrier:GetCoordinate() 
   end
   
   if not self.group then return nil end

   -- A combatant killed between an IsAlive() check and now has a gone DCS object; MOOSE
   -- GROUP:GetCoordinate() then logs a GetVec3 error and returns nil (the log flood plus
   -- the caught SCHEDULER crash when a unit dies mid-move -- see :isNear). Test existence
   -- with the non-logging IsAlive() first and return nil quietly.
   if not self.group:IsAlive() then return nil end

   return self.group:GetCoordinate()

end

function GLSCO_COMBATANT:GetHeading()

   if not self.group then return nil end

   return self.group:GetHeading()

end

-- Home is simply this units position near the current formation's waypoint
function GLSCO_COMBATANT:GetHomeHeading()

   if not self.homeWP then return nil end
   
   return self.homeWP:GetHeading()

end

-- Home is simply this units position near the current formation's waypoint
function GLSCO_COMBATANT:GetHomeCoordinate()

   if not self.homeWP then return nil end
   
   return self.homeWP:GetCoordinate(self:GetName())

end

function GLSCO_COMBATANT:GetSpeedKMH()

   if not self.group then return 0 end

   return self.group:GetVelocityKMH()

   --return UTILS.MpsToKnots(self.group:GetGroundSpeed())

end

function GLSCO_COMBATANT:IsAlive()

   if self.fsm:GetState() == "Dead" then
      return false
   end

   if self:IsInfantry() then
      return true
   end
   
   return self.group:IsAlive()

end

function GLSCO_COMBATANT:IsLeader()

   return self.leader

end

function GLSCO_COMBATANT:IsInfantry()

   if self.cache.infantry ~= nil then return self.cache.infantry end

   if self.group then
      self.cache.infantry = self.group:HasAttribute("Infantry", false)
   end

   return self.cache.infantry or false
   
end

function GLSCO_COMBATANT:IsIFV()

   if self.cache.ifv ~= nil then return self.cache.ifv end

   if self.group then
      self.cache.ifv = self.group:HasAttribute("Infantry carriers", false)
   end

   return self.cache.ifv or false

end

function GLSCO_COMBATANT:IsTank()

   if not self.group then return false end

   return self.group:HasAttribute("Tanks", false) or false

end

function GLSCO_COMBATANT:IsAirDefense()

   if not self.group then return false end

   return self.group:HasAttribute("Air Defence", false) or false

end

function GLSCO_COMBATANT:IsWeaponFree()

   if GLSCO.EnableWeaponFree then
      return true
   end
   
   return self.profile.WeaponFree

end

function GLSCO_COMBATANT:IsLeading()

   return self.fsm:GetState() == "Leading"

end

function GLSCO_COMBATANT:IsMoving()

   return self.fsm:GetState() == "Moving"

end

-- Indicates this is an infantry unit currently inside a IFV carrier vehicle.
function GLSCO_COMBATANT:IsRiding()

   return self.fsm:GetState() == "Riding"
   
end

-- Infantry unit is in the process of unloading from its IFV carrier.
function GLSCO_COMBATANT:IsUnloading()

   return self.fsm:GetState() == "Unloading"
   
end

-- IFV vehicle is ready to take troops onboard.
function GLSCO_COMBATANT:ReadyToLoad()

   if not self:IsAlive() then return false end

   return self.fsm:GetState() == "Loading"

end

function GLSCO_COMBATANT:GetStrength()

   local strength = 
   {
      alive = 0,
      total = self.unitCount
   }
   
   if not self:IsAlive() then
      return strength
   end
   
   if self:IsInfantry() then
      strength.alive = self.unitCount
      return strength
   end
   
   for _, unit in ipairs(self.group:GetUnits()) do
   
      if unit:IsAlive() then
         strength.alive = strength.alive + 1
      end
   end
   
   return strength

end

-- Constructor
-- Defines initial state and sets up internal FSM.
function GLSCO_COMBATANT:New(group)

   if group == nil then
      env.error("TODO: group is nil")
   end

   --group:OptionROEHoldFire()
   group:OptionDisperseOnAttack(10)
   
   -- Finite State Machine
   local fsm = FSM:New()
   fsm:SetStartState("Idle")
   fsm:AddTransition("Idle", "Activate", "Ready")
   fsm:AddTransition("Ready", "Deactivate", "Idle")
   
   fsm:AddTransition("Ready", "Move", "Moving") -- unit has begun moving to next waypoint
   fsm:AddTransition("Moving", "Arrived", "Ready") -- unit has arrived at destination
   
   fsm:AddTransition("Moving", "Halt", "Halted") -- human player has halted forward progress of this unit
   fsm:AddTransition("Halted", "Resume", "Moving") -- human player wants unit to continue progress
   
   fsm:AddTransition("Moving", "Move", "Moving")
   
   fsm:AddTransition("Ready", "Shift", "Shifting") -- unit is repositioning to a random location nearby
   fsm:AddTransition("Shifting", "Shifted", "Ready") -- unit completed reposition
   
   fsm:AddTransition("Ready", "Wait", "Ready") -- unit will wait here and do nothing
   fsm:AddTransition("Halted", "Wait", "Halted") -- human player has halted forward progress of this unit
   
   fsm:AddTransition("Ready", "Delay", "Ready") -- human player has halted unit so that it doesn't move
   fsm:AddTransition("Ready", "Continue", "Ready") -- human player wants unit to resume normal behavior
   
   -- These are specific to infantry and troop carrier vehicles
   fsm:AddTransition("Ready", "Load", "Loading") -- infantry are moving to get inside carrier
   fsm:AddTransition("Loading", "Mounted", "Riding") -- infantry are now riding inside carrier
   fsm:AddTransition("Loading", "Orphaned", "Ready") -- carrier is destroyed, so this infantry is orphaned
   fsm:AddTransition("Loading", "Loaded", "Ready") -- carrier has completed loading procedure
   
   fsm:AddTransition("Ready", "Unload", "Unloading") -- infantry are unloading from carrier
   fsm:AddTransition("Riding", "Unload", "Unloading") -- infantry are unloading from carrier
   fsm:AddTransition("Unloading", "Unloaded", "Ready") -- infantry have completed unloading process
      
   fsm:AddTransition("Ready", "OpenFire", "Firing") -- unit is firing at enemy target
   fsm:AddTransition("Firing", "CeaseFire", "Ready") -- unit has stopped firing
   
   fsm:AddTransition("Ready", "Lead", "Leading") -- SetPath command has been issued to this unit by a human from the F10 map
   fsm:AddTransition("Leading", "Follow", "Ready") -- unit has reached destination of SetPath command
   
   fsm:AddTransition("*", "Died", "Dead") -- unit is destroyed
   
   --[FROM] OnLeave<state> --> OnBefore<event> --> [EVENT] --> OnAfter<event> --> OnEnter<state> [TO] 
   
   function fsm:OnAfterActivate(from, event, to, combatant)
   
      combatant:logDebug("OnAfterActivate")
   
      if combatant:IsWeaponFree() then
         env.warning("GLSCO_COMBATANT: weapon free! name=["..combatant:GetName().."]")
         combatant.group:OptionROEOpenFire()
      else
         combatant.group:OptionROEHoldFire()
      end
   end
      
   -- Main loop, units spend most of their time in this state.
   function fsm:OnEnterReady(from, event, to, combatant)
   
      combatant:logDebug("OnEnterReady")
   
      -- Ready => Deactivate => Idle
      if not combatant.activated then
         local delay = math.random(1, 3)
         env.error("deactivated")
         self:__Deactivate(delay)
         return
      end
      
      -- * => Died => Dead
      if not combatant.group:IsAlive() then
         env.warning("combatant died!!!")
         self:Died(combatant)
         return
      end
      
      combatant:updateVisibility()
      
      -- Ready => Delay => Ready
      if combatant.requestHalt then
         combatant.requestHalt = false -- request acknowledged
         local delay = math.random(2, 5)
         self:__Delay(delay, combatant)
         return
      end
      
      -- Ready => Continue => Ready
      if combatant.requestResume then
         combatant.requestResume = false -- request acknowledged
         local delay = math.random(2, 5)
         self:__Continue(delay, combatant)
         return
      end

      -- Ready => Lead => Leading
      if combatant.requestLead then
         combatant.requestLead = false -- request acknowledged
         self:__Lead(1, combatant)
         return
      end
      
      -- Ready => Load => Loading
      if combatant.requestLoad then
         combatant.requestLoad = false -- request acknowledged
         
         if combatant:IsIFV() or combatant:IsInfantry() then
            local delay = math.random(2, 5)
            self:__Load(delay, combatant)
            return
         end
      end
      
      -- Ready => Unload => Unloading
      if combatant.requestUnload then
         combatant.requestUnload = false -- request acknowledged
         
         if combatant:IsIFV() or combatant:IsInfantry() then
            local delay = math.random(15, 20)
            self:__Unload(delay, combatant)
            return
         end
      end
         
      if combatant.moveNow and not combatant.leader then
         combatant:logDebug("OnEnterReady: move now!")
         combatant.moves = {}
         table.insert(combatant.moves, combatant.moveNow)
         combatant.moveNow = nil
      end
   
      -- Ready => Move => Moving
      if not combatant.delayMission and #combatant.moves > 0 then
      
         local delay = math.random(2, 10)
         self:__Move(delay, combatant)
         return
      end
      
      -- No more moves, time to do something else
      -- We either shift or open fire or wait.
      local diceRoll = math.random()
      local chance = combatant.profile.ShiftChance
      
      if combatant.leader then
         -- leaders don't shift or open fire, because we don't want to interrupt
         -- custom movements initiated by CA or GM.
         local delay = math.random(5, 10)
         self:__Wait(delay, combatant)   
      elseif diceRoll <= chance then
         if chance > 0.0 and combatant.allowShift and combatant.unitCount == 1 then
            -- Ready => Shift => Shifting
            local delay = math.random(1, 2)
            self:__Shift(delay, combatant)
         else
            local delay = math.random(15, 25)
            self:__Wait(delay, combatant)   
         end  
      else
         --[[
         if #combatant.targets == 0 then
            local delay = math.random(15, 25)
            self:__Wait(delay, combatant)   
         else
            -- Ready => OpenFire => Firing
            local delay = math.random(5, 10)
            self:__OpenFire(delay, combatant)
         end
         --]]
         
         -- Ready => OpenFire => Firing
         local delay = math.random(5, 10)
         self:__OpenFire(delay, combatant)
      end
      
   end
   
   -- ====================================================================================================
   -- Moving
   -- ====================================================================================================
   function fsm:OnAfterMove(from, event, to, combatant)
      
      combatant:logDebug("OnAfterMove")

      local curWaypoint = combatant.moves[1]
      combatant.homeWP = nil
      
      combatant.allowShift = curWaypoint:GetOptions():ShouldShift()
      
      local newROE = curWaypoint:GetOptions():GetROE()
      if newROE ~= nil then
         combatant.roe = newROE
      end
      
      local speed = curWaypoint:GetOptions():GetSpeedKMH() or combatant.profile.TopSpeedKMH
      
      -- Carrier should only move as fast as infantry on foot so that formation geometry 
	  -- is maintained.
      if combatant:IsIFV() and not combatant:allPassengersOnBoard() then
         speed = GLSCO.INFANTRY_PROFILE.default.TopSpeedKMH
      end
      
      combatant:moveToCoord(curWaypoint:GetCoordinate(combatant:GetName()), 
                            speed, 
                            curWaypoint:GetOptions():ShouldUseRoads())

   end
   
   function fsm:OnEnterMoving(from, event, to, combatant) 
   
      combatant:logDebug("OnEnterMoving")
   
      local delay = math.random(GLSCO.Settings.ARRIVAL_MIN_INTERVAL, GLSCO.Settings.ARRIVAL_MAX_INTERVAL)
      self:__Arrived(delay, combatant, nil, combatant.moves[1]:GetCoordinate(combatant:GetName()), GLSCO.Settings.HOME_MAX_RADIUS_METERS)
   
   end
   
   function fsm:OnBeforeArrived(from, event, to, combatant, prevCoord, destCoord, arrivalRadius)
   
      combatant:logDebug("OnBeforeArrived")
   
      if #combatant.moves == 0 then
         combatant:logDebug("OnBeforeArrived: no moves")
         return true
      end
      
      if combatant.moveNow then
          combatant:logDebug("OnBeforeArrived: need to move to different coord immediately!")
         -- Need to leave this state, so we can immediately move to a different coord.
         return true
      end
      
      if not combatant:IsAlive() then
         -- Allow event to transition to ARRIVED since the unit is dead.
         return true
      end
      
      if not combatant:isNear(destCoord, arrivalRadius) then
      
         combatant:logDebug("OnBeforeArrived: not close enough")

         -- Moving => Halt => Halted
         if combatant.requestHalt then
            combatant:logDebug("OnBeforeArrived: need to halt")
            combatant.requestHalt = false -- request acknowledged
            local delay = math.random(2, 5)
            self:__Halt(delay, combatant)
            -- Cancel transition
            return false
         end
         
		 local curCoord = combatant:GetCoordinate()
		 if GLSCO.IsSameCoordinate(prevCoord, curCoord) then
		    -- Some how we are stuck, we are not going to make progress, so
			-- let's retry the move task.
			env.warning("OnBeforeArrived: unit is stuck!")

			-- Using roads is very buggy, so let's disable their usage to help
			-- get unstuck.
			local curWaypoint = combatant.moves[1]
			curWaypoint:GetOptions():ProhibitRoads()
			self:__Move(2, combatant)
			
		    return false
		 end
		 
		 if combatant.roe == GLSCO_COMBATANT.ROE.KILL then
		    -- A combatants FSM has a state for opening fire, but this state can
		    -- only be entered when the unit is no longer on the move.  Normally this is fine,
		    -- however, if the ROE is kill, then combatants won't shoot anything while on the move.
		    -- To solve this, when combatants are moving, they have a percent chance to decloak
		    -- enemies in their vicinity which will allow the AI logic to open fire while moving.
		    combatant:kill()
		 end
		 
         local delay = math.random(GLSCO.Settings.ARRIVAL_MIN_INTERVAL, GLSCO.Settings.ARRIVAL_MAX_INTERVAL)
         
         local coord = COORDINATE:NewFromCoordinate(destCoord)
         self:__Arrived(delay, combatant, curCoord, coord, arrivalRadius)
          
         -- Cancel transition
         return false
      end
      
      combatant:logDebug("OnBeforeArrived: have arrived")
      
   end
   
   function fsm:OnAfterArrived(from, event, to, combatant)
   
      combatant:logDebug("OnAfterArrived")
      combatant:ceaseFire()
   
      if #combatant.moves > 0 then
      
         combatant:logDebug("OnAfterArrived: dequeue move")
         combatant.homeWP = combatant.moves[1]
         table.remove(combatant.moves, 1)
         
		 -- We've arrived at waypoint, check if we need to set a flag.
         local flagToSet = combatant.homeWP:GetOptions():GetFlagToSet()
         if flagToSet then
            env.info("GLSCO: flag ["..flagToSet.."] turned on via waypoint option.")
            USERFLAG:New(flagToSet):Set(1)
         end
         
         local deploy = combatant.homeWP:GetOptions():GetDeployment()
         if deploy == GLSCO.Deployment.LOAD then
            combatant:Load()
         elseif deploy == GLSCO.Deployment.UNLOAD then
            combatant:Unload()
         end
      end
      
   end
  
   -- ====================================================================================================
   -- Load
   -- ====================================================================================================
   function fsm:OnBeforeLoad(from, event, to, combatant)
   
      combatant:logDebug("OnBeforeLoad")
   
      if combatant:IsInfantry() then
         if combatant.carrier:IsAlive() and not combatant.carrier:ReadyToLoad() then
            self:__Load(5, combatant)
            return false
         end
      end
   
   end
   
   function fsm:OnAfterLoad(from, event, to, combatant)
      
      combatant:logDebug("OnAfterLoad")

   end
   
   function fsm:OnEnterLoading(from, event, to, combatant) 
   
      combatant:logDebug("OnEnterLoading")
   
      -- Need a stopwatch so loading process doesn't last forever.
      local watch = GLSCO_STOPWATCH:New()
      watch:Start()
   
      local delay = math.random(5, 10)

      if combatant:IsIFV() then
         self:__Loaded(delay, combatant, watch)
      elseif combatant:IsInfantry() then
         combatant:moveNearCarrier()
         self:__Mounted(delay, combatant, watch)
      else
         env.error("OnEnterLoading: expected infantry or IFV!")
      end
   
   end
   
   function fsm:OnBeforeLoaded(from, event, to, combatant, watch)
   
      combatant:logDebug("OnBeforeLoaded")
      
      if combatant:allPassengersOnBoard() or watch:GetElapsedSeconds() > GLSCO.Settings.DEPLOY_WAIT_SECONDS then
	     -- Either all troops are onboard or stop watch has expired.
         return true
      end
      
      local delay = math.random(5, 10)
      self:__Loaded(delay, combatant, watch)
	  
	  -- Cancel transition and try again
      return false
   
   end
   
   function fsm:OnAfterLoaded(from, event, to, combatant, watch)
   
      combatant:logDebug("OnAfterLoaded")
   
   end
   
   function fsm:OnBeforeMounted(from, event, to, combatant, watch)
   
      combatant:logDebug("OnBeforeMounted")
      
      if not combatant.carrier:IsAlive() then
         -- Infantry unit no longer has a ride, it has been orphaned.  Its state will return to READY.
         self:__Orphaned(5, combatant)
         return false
      end
      
      if combatant:isNearCarrier() or watch:GetElapsedSeconds() > GLSCO.Settings.DEPLOY_WAIT_SECONDS then
         return true
      end

      local delay = math.random(5, 10)
      self:__Mounted(delay, combatant, watch)
      return false
      
   end
   
   function fsm:OnAfterMounted(from, event, to, combatant, watch)
   
      combatant:logDebug("OnAfterMounted")
	  -- Mounted infantry don't really enter a vehicle, they are just despawned from the world
	  -- to pretend they got inside.
      combatant:despawn()
   
   end
   
   -- ====================================================================================================
   -- Unload
   -- ====================================================================================================
   function fsm:OnAfterUnload(from, event, to, combatant)
      
      combatant:logDebug("OnAfterUnload")

   end
   
   function fsm:OnEnterUnloading(from, event, to, combatant) 
   
      combatant:logDebug("OnEnterUnloading")
      
      if combatant:IsIFV() and combatant:IsAlive() then
         local watch = GLSCO_STOPWATCH:New()
         watch:Start()
         combatant:unloadPassengers(GLSCO.Settings.DEPLOY_WAIT_SECONDS)
         local delay = math.random(10, 15)
         self:__Unloaded(delay, combatant, watch)
      elseif combatant:IsInfantry() then
         local watch = nil
         local destCoord = nil      
         self:__Unloaded(1, combatant, watch, destCoord)
      else
         env.error("OnEnterUnloading: expected infantry or IFV!")
      end
   
   end

   function fsm:OnBeforeUnloaded(from, event, to, combatant, watch, destCoord)
   
      combatant:logDebug("OnBeforeUnloaded")
      
      if combatant:IsInfantry() and combatant.carrier:IsAlive() and combatant:IsAlive() then

         local delay = math.random(GLSCO.Settings.ARRIVAL_MIN_INTERVAL, GLSCO.Settings.ARRIVAL_MAX_INTERVAL)
         
         if destCoord == nil then

            -- Find location about 15m behind carrier
            local coordNearCarrier = combatant.carrier:GetCoordinate():Translate(15, 180):GetRandomCoordinateInRadius(10, 2)
            local carrierHdg = combatant.carrier:GetHeading()
            combatant:respawn(coordNearCarrier, carrierHdg)

            destCoord = combatant:GetHomeCoordinate()
            combatant:moveToCoord(destCoord, GLSCO.INFANTRY_PROFILE.default.TopSpeedKMH, false)
            self:__Unloaded(delay, combatant, watch, destCoord)
            return false
         else
         
            if not combatant:isNear(destCoord, GLSCO.Settings.HOME_MAX_RADIUS_METERS) then
               self:__Unloaded(delay, combatant, watch, destCoord)
               return false
            end
            
            return true
         end
      elseif combatant:IsIFV() and combatant:IsAlive() then
      
         if watch:GetElapsedSeconds() > GLSCO.Settings.DEPLOY_WAIT_SECONDS then
            return true
         elseif combatant:numberRidingPassengers() > 0 then
            local delay = math.random(5, 8)
            self:__Unloaded(delay, combatant, watch)
            return false
         end
      
         return true   
      end
      
   end
   
   function fsm:OnAfterUnloaded(from, event, to, combatant)
   
      combatant:logDebug("OnAfterUnloaded")

   end

   -- ====================================================================================================
   -- Shifting
   -- ====================================================================================================
   function fsm:OnAfterShift(from, event, to, combatant)
   
      combatant:logDebug("OnAfterShift")
   
      local destCoord = combatant:shift()
      
      -- Shifting => Shifted => (Shifting OR Ready)
      local delay = math.random(5, 10)
      local initialRadius = 2
      self:__Shifted(delay, combatant, destCoord, initialRadius)

   end
   
   function fsm:OnBeforeShifted(from, event, to, combatant, destCoord, shiftRadius)
   
      combatant:logDebug("OnBeforeShifted")
   
      if not combatant:isNear(destCoord, shiftRadius) then
      
         combatant:logDebug("OnBeforeShifted: not close enough")
      
         if not combatant:IsAlive() then
         
            -- Allow event to transition to SHIFTED since the unit is dead.
            return true
         end
          
         -- I need to know when the unit arrives at the new shifted coordinate.
         -- However, units sometimes get stuck when shifting short distances.  To
         -- prevent FSM from never leaving the Shifting state, I gradually 
         -- increase the shift radius between attempts so eventually the FSM
         -- will consider the unit shifted, even if they are still far away.
         shiftRadius = math.min(shiftRadius + 2, GLSCO.Settings.ARRIVAL_RADIUS_METERS + 20)
         
         local delay = math.random(5, 10)
         self:__Shifted(delay, combatant, destCoord, shiftRadius)
         
         -- Cancel transition
         return false
      end
      
      combatant:logDebug("OnBeforeShifted: have shifted")
      
   end
   
   function fsm:OnAfterShifted(from, event, to, combatant)
    
      combatant:logDebug("OnAfterShifted")
    
   end
   
   --[FROM] OnLeave<state> --> OnBefore<event> --> [EVENT] --> OnAfter<event> --> OnEnter<state> [TO] 
   -- ====================================================================================================
   -- Lead & Follow
   -- ====================================================================================================
   function fsm:OnAfterLead(from, event, to, combatant)
   
      combatant:logDebug("OnAfterLead")
      combatant:lead()
   
      self:__Follow(5, combatant)  
   
   end
   
   function fsm:OnBeforeFollow(from, event, to, combatant)
   
      combatant:logDebug("OnBeforeFollow")
   
      if combatant.requestFollow then
         combatant.requestFollow = false -- request acknowledged
         return true
      end
      
      self:__Follow(5, combatant) 
      return false
   
   end
   
   function fsm:OnAfterFollow(from, event, to, combatant)
   
      combatant:logDebug("OnAfterFollow")
      combatant:follow()
   
   end
   
   -- ====================================================================================================
   -- Halt & Resume
   -- ====================================================================================================
   function fsm:OnAfterHalt(from, event, to, combatant)
   
      combatant:logDebug("OnAfterHalt: => "..to)
      combatant:halt()
   
   end
   
   function fsm:OnEnterHalted(from, event, to, combatant)
   
      combatant:logDebug("OnEnterHalted")
   
      -- Halted => Resume => Moving
      if combatant.requestResume then
         combatant:logDebug("OnEnterHalted: need to resume")
         combatant.requestResume = false -- request acknowledged
         local delay = math.random(2, 5)
         self:__Resume(delay, combatant)
         return
      end
   
      -- Halted => Wait => Halted
      local delay = math.random(5, 10)
      self:__Wait(delay, combatant)  
   
   end
      
   function fsm:OnAfterResume(from, event, to, combatant)
   
      combatant:logDebug("OnAfterResume: => "..to)
      combatant:resume()
   
   end
   
   function fsm:OnAfterDelay(from, event, to, combatant)
   
      combatant:logDebug("OnAfterDelay")
      combatant.delayMission = true
   
   end
   
   function fsm:OnAfterContinue(from, event, to, combatant)
   
      combatant:logDebug("OnAfterContinue")
      combatant.delayMission = false
   
   end

   -- ====================================================================================================
   -- Open Fire
   -- ====================================================================================================
   function fsm:OnAfterOpenFire(from, event, to, combatant)
      
      combatant:logDebug("OnAfterOpenFire")
      local target = combatant:openFire()
      
      local delay = math.random(8, 15)
      self:__CeaseFire(delay, combatant, target)
      
   end
   
   function fsm:OnAfterCeaseFire(from, event, to, combatant, target)
   
      combatant:logDebug("OnAfterCeaseFire")
      combatant:ceaseFire(target)
      
   end
   
   function fsm:OnEnterDead(from, event, to, combatant)
      
      if combatant:IsIFV() then
         for i = 1, #combatant.passengers do
            if combatant.passengers[i]:IsRiding() then
               combatant.passengers[i].fsm:Died(combatant.passengers[i])
            end
         end
      end
	  
   end  
        
   local inst = 
   {
      cache = {}, -- some properties of the group needs to be cached since mounted units are created and destroyed
      group = group,
      leader = false,
      unitCount = #group:GetUnits(),
      template = GLSCO_SPAWN:CreateSpawnTemplate(group),
      fsm = fsm,
      profile = nil,
      initWP = nil,
      homeWP = nil,
      carrier = GLSCO_COMBATANT_DUMMY,
      passengers = {},
      activated = false,
      allowShift = true,
      requestHalt = false,
      requestResume = false,
      requestLead = false,
      requestFollow = false,
      delayMission = false,
      requestLoad = false,
      requestUnload = false,
      moves = {},
      moveNow = nil,
      targets = {},
      visibleWindow = {},
      roe = GLSCO_COMBATANT.ROE.SIMULATE,
      debug = false,
      draw = false,
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   group:HandleEvent(EVENTS.Dead)
   
   function group:OnEventDead(EventData)
   
      if group:GetName() == EventData.IniGroupName then
         if not group:IsAlive() then
            fsm:Died(inst)
         end
      end
   end
   
   inst.profile = inst:mergeProfiles()
   inst:cloak()
   inst:ceaseFire()
   inst:logState()
   
   -- Enable these lines of code if you want a label placed above every combatant indicating
   -- their current FSM state.  For troubleshooting ONLY, drawing hundreds of labels can have
   -- a performance impact.
   --[[
   local loop = function() 
      inst:drawState()
   end
   
   inst.timer = TIMER:New(loop)
   inst.timer:Start(1, 3)
   --]]
   
   return inst

end

function GLSCO_COMBATANT:SetAsLeader()
   
   if self.leader then
      return
   end
   
   env.info("Combatant designated as leader. name=["..self:GetName().."]")
   self.leader = true
   
end

function GLSCO_COMBATANT:Initialize(waypoint)

   self.initWP = waypoint
   self.homeWP = waypoint
   
   local shift = waypoint:GetOptions():ShouldShift()
   if not shift then
      self:DisableShift()
   end
   
   local roe = waypoint:GetOptions():GetROE()
   if roe == GLSCO_COMBATANT.ROE.SIMULATE then
      self:SimulateFire()
   elseif roe == GLSCO_COMBATANT.ROE.KILL then
      self:ShootToKill()
   elseif roe == GLSCO_COMBATANT.ROE.HOLD then
      self:HoldFire()
   end

   if waypoint:GetOptions():GetDeployment() == GLSCO.Deployment.LOAD then
      self:Load()
   end

end

-- Assigns the provided combatant as a passenger.  Assumes this combatant is a IFV carrier and
-- the parameter is infantry combatant.
function GLSCO_COMBATANT:AssignPassenger(combatant)

   if combatant == nil then
      return
   end

   if not combatant:IsInfantry() then
      env.error("Passenger must be infantry!")
      return
   end

   table.insert(self.passengers, combatant)

end

-- Associates this combatant with the provided IFV carrier.  Assumes this combatant is an
-- infantry unit and the parameter is an IFV carrier.
function GLSCO_COMBATANT:AssignCarrier(combatant)

   if combatant == nil then
      return
   end

   if not self:IsInfantry() then
      env.error("Combatant assigned to carrier must be infantry!")
      return
   end

   if not combatant:IsIFV() then
      env.error("Carrier must be IFV!")
      return
   end
   
   self.carrier = combatant
   self.carrier:AssignPassenger(self)

end

-- Starts the FSM
function GLSCO_COMBATANT:Activate()

   if not self.activated then
      -- Start FSM once first move command is submitted
      self.activated = true
      local delay = math.random(3, 5)
      self.fsm:__Activate(delay, self)
   end

end

function GLSCO_COMBATANT:Deactivate()

   self.activated = false

end

function GLSCO_COMBATANT:Lead()

   if not self:IsLeading() then
      self.requestLead = true
   end

end

function GLSCO_COMBATANT:Follow()

   self.requestFollow = true

end

function GLSCO_COMBATANT:EnableShift()

   self.allowShift = true

end

function GLSCO_COMBATANT:DisableShift()

   self.allowShift = false

end

function GLSCO_COMBATANT:Halt()

   self.requestHalt = true

end

function GLSCO_COMBATANT:Resume()

   self.requestResume = true

end

function GLSCO_COMBATANT:Destroy()

   local raiseEvent = true
   self.group:Destroy(raiseEvent)

end

function GLSCO_COMBATANT:Load()

   self.requestLoad = true

end

function GLSCO_COMBATANT:Unload()

   self.requestUnload = true

end

function GLSCO_COMBATANT:Move(waypoint)

   if waypoint == nil then
      env.error("Unable to move.  Waypoint is nil.")
      return
   end
   
   -- Queue up move to be processed by FSM
   table.insert(self.moves, #self.moves + 1, waypoint)
   self:Activate()

end

function GLSCO_COMBATANT:MoveNow(waypoint)

   if waypoint == nil then
      env.error("Unable to move now.  Waypoint is nil.")
      return
   end

   self.moveNow = waypoint
   self:Activate()

end

function GLSCO_COMBATANT:SetTargetList(combatants)

   self.targets = combatants or {}

end

function GLSCO_COMBATANT:HoldFire()

   -- set ROE weapon hold
   self.roe = GLSCO_COMBATANT.ROE.HOLD

end

function GLSCO_COMBATANT:SimulateFire()

   -- make enemy units invisible
   self.roe = GLSCO_COMBATANT.ROE.SIMULATE

end

function GLSCO_COMBATANT:ShootToKill()

   self.roe = GLSCO_COMBATANT.ROE.KILL

end

function GLSCO_COMBATANT:Smoke()

   if not self:IsAlive() and not self:IsRiding() then
      return
   end
   
   local c = self:GetCoalition()
   local color = SMOKECOLOR.White
   if (c == coalition.side.BLUE) then
      color = SMOKECOLOR.Blue
   elseif (c == coalition.side.RED) then
      color = SMOKECOLOR.Red
   end
   
   if self.group:IsAlive() then
      self.group:Smoke(color, nil, 0)
   end

end

function GLSCO_COMBATANT:Draw()

   self.draw = true

end

function GLSCO_COMBATANT:Erase()

   self.draw = false

end

--[[
-- Hides combatant from being targeted by other combatants
function GLSCO_COMBATANT:Cloak()

   if self:IsAlive() then
      self.group:SetCommandInvisible(true)
      self.visible = false
   end

end

-- Exposes combatant so other combatants can detect and target this unit.
function GLSCO_COMBATANT:Decloak(delay, duration)

   local funcDecloak = function(combatant, duration)  
      if combatant:IsAlive() then
         combatant.group:SetCommandInvisible(false)
         combatant.visible = true
      end
   end

   local funcCloak = function(combatant)  
      if combatant:IsAlive() then
         combatant.group:SetCommandInvisible(true)
         combatant.visible = false
      end
   end

   if self:IsAlive() and not self:IsLeader() then
 
      self.group:ScheduleOnce(delay or 1, funcDecloak, self, duration)
   
      if duration ~= nil then
         self.group:ScheduleOnce(duration+1, funcCloak, self)
      end
   
      --self.group:SetCommandInvisible(false)
      --self.visible = true
   end

end
--]]

function GLSCO_COMBATANT:Cloak(delay, duration)

   delay = delay or 0
   duration = duration or 3600*24*10 -- 10 days is basically infinite

   local stamp = GLSCO_SCHEDULER.getSecondsFromMissionStart()
   
   local newStart = stamp + delay
   local curStart = self.visibleWindow.cloakStart or newStart
   newStart = math.min(curStart, newStart)
   self.visibleWindow.cloakStart = newStart

   local newEnd = stamp + delay + duration
   local curEnd = self.visibleWindow.cloakEnd or newEnd
   newEnd = math.max(curEnd, newEnd)
   self.visibleWindow.cloakEnd = newEnd

   self.visibleWindow.decloakStart = nil
   self.visibleWindow.decloakEnd = nil
   
end

function GLSCO_COMBATANT:Decloak(delay, duration)

   delay = delay or 0
   duration = duration or 3600*24*10 -- 10 days is basically infinite

   local stamp = GLSCO_SCHEDULER.getSecondsFromMissionStart()
   
   local newStart = stamp + delay
   local curStart = self.visibleWindow.decloakStart or newStart
   newStart = math.min(curStart, newStart)
   self.visibleWindow.decloakStart = newStart

   local newEnd = stamp + delay + duration
   local curEnd = self.visibleWindow.decloakEnd or newEnd
   newEnd = math.max(curEnd, newEnd)
   self.visibleWindow.decloakEnd = newEnd

   self.visibleWindow.cloakStart = nil
   self.visibleWindow.cloakEnd = nil
   
   --env.info("GLSCO_COMBATANT:Decloak stamp="..stamp.." dStart="..self.visibleWindow.decloakStart.." dEnd="..self.visibleWindow.decloakEnd)

end

function GLSCO_COMBATANT:updateVisibility()

   if not self:IsAlive() then
      return
   end
   
   local stamp = GLSCO_SCHEDULER.getSecondsFromMissionStart()
   if self.visibleWindow.cloakStart ~= nil then
      if self.visibleWindow.cloakStart <= stamp then
         self.visibleWindow.cloakStart = nil
         self:cloak()
      end
   end
   
   if self.visibleWindow.cloakEnd ~= nil then
      if self.visibleWindow.cloakEnd <= stamp then
         self.visibleWindow.cloakEnd = nil
         self:decloak()
      end
   end
   
   if self.visibleWindow.decloakStart ~= nil then
      if self.visibleWindow.decloakStart <= stamp then
         self.visibleWindow.decloakStart = nil
         self:decloak()
      end
   end
   
   if self.visibleWindow.decloakEnd ~= nil then
      if self.visibleWindow.decloakEnd <= stamp then
         self.visibleWindow.decloakEnd = nil
         self:cloak()
      end
   end


end

function GLSCO_COMBATANT:cloak()

   if self:IsAlive() and not GLSCO.DisableCloaking then
      self.group:SetCommandInvisible(true)
      self.visible = false
   end

end

function GLSCO_COMBATANT:decloak()

   if self:IsAlive() then
      self.group:SetCommandInvisible(false)
      self.visible = true
   end

end

function GLSCO_COMBATANT:lead()

   if self:IsAlive() then
      self.group:SetCommandInvisible(true)
      self.group:SetCommandImmortal(true)
   end

end

function GLSCO_COMBATANT:follow()

   if self:IsAlive() then
      self.group:SetCommandImmortal(false)
   end

end

function GLSCO_COMBATANT:shift()

   if not self:IsAlive() then
      return
   end
   
   local homeCoord = self:GetHomeCoordinate()
   local homeHdg = self:GetHomeHeading()
   
   local curCoord = self:GetCoordinate()
   if curCoord == nil then
      return nil
   end
   
   local distance = curCoord:Get2DDistance(homeCoord) + math.random(10, 15)
   
   --env.info("Distance from home=" .. distance)
   if distance > GLSCO.Settings.HOME_MAX_RADIUS_METERS then
      return self:moveHome()
   end
   
   local newHdg = (homeHdg + math.random(-20, 20)) % 360
   local fwdCoord = COORDINATE:NewFromVec2(UTILS.Vec2Translate(homeCoord:GetVec2(), distance, newHdg))
   local newCoord = COORDINATE:NewFromVec2(fwdCoord:GetRandomVec2InRadius(15))
   
   --if (self.debug) then
   --   fwdCoord:CircleToAll(2, coalition.side.RED, {0,1,0},1,{0,1,0},1)
   --   newCoord:CircleToAll(2, coalition.side.RED, {1,0,1},1,{1,0,1},1)
   --end
   
   self.group:RouteGroundTo(newCoord, self.profile.TopSpeedKMH)
   
   return newCoord

end

function GLSCO_COMBATANT:openFire()

   if not self:IsAlive() then
      return
   end
   
   -- No restriction on targets.
   self.group:SetOption(28, 0)

   if self.roe == GLSCO_COMBATANT.ROE.HOLD then
      return nil
   elseif self.roe == GLSCO_COMBATANT.ROE.SIMULATE then
      return self:simulate()
   elseif self.roe == GLSCO_COMBATANT.ROE.KILL then
      return self:kill()
   end

end

function GLSCO_COMBATANT:ceaseFire(target)

   if not self:IsAlive() then
      return
   end
   
   -- Restrict targets to ground units only.
   if not self:IsAirDefense() then
      self.group:SetOption(28, 2)
   end
   
   if self:IsWeaponFree() then
      -- We are allowing AI to target enemy units
      return
   end

   -- This is the key line of code that makes the battlefield more survivable for
   -- helo pilots.  When a combatant is in a "OpenFire" state, helos are vulnerable, but
   -- once the combatant ceases fire, helos will no longer be targeted.  Therefore, since
   -- combatants are rarely (relatively speaking) in the OpenFire state, helos are not
   -- bombarded with enemy fire.
   -- NOTE: even if you order a DCS Group to FireAtPoint on the ground, it still prioritizes firing
   -- on units it can detect (like helos in this case).  
   self.group:OptionROEHoldFire()
   
end

function GLSCO_COMBATANT:simulate()

   if not self:IsAlive() then
      return
   end
   
   if self:IsWeaponFree() then
      -- We are allowing AI to target enemy units.  Useful for Air Defense type units.
      return
   end
   
   self.group:OptionROEOpenFire()
   
   if #self.targets == 0 then
      return
   end
   
   local target = self:selectRandomTarget()
   
   if target == nil then 
      -- All targets are dead
      return nil 
   end
   
   local vec2 = target:GetCoordinate():GetRandomVec2InRadius(self.profile.OuterAimRadius, self.profile.InnerAimRadius)
   local altitude = math.random(1, 5)
   local task = self.group:TaskFireAtPoint(vec2, 1, self.profile.SalvoQty, nil, altitude)
   self.group:PushTask(task, 0)

   return target

end

function GLSCO_COMBATANT:kill()

   if not self:IsAlive() then
      return
   end
   
   if self:IsWeaponFree() then
      -- We are allowing AI to target enemy units
      return
   end
   
   -- ROE MUST be set to OpenFire.  For whatever reason, setting to WeaponFree does NOT WORK!!!
   --self.group:ClearTasks()
   --self.group:OptionROEOpenFireWeaponFree()
   self.group:OptionROEOpenFire()
   
   if #self.targets == 0 then
      return
   end

   local target = self:decloakRandomTarget(1.0)
   return target

end

function GLSCO_COMBATANT:selectRandomTarget()

   if #self.targets == 0 then
      return nil
   end

   for i = 1, 10 do
      -- Randomly select one of the enemy units to target.
      local target = self.targets[math.random(1, #self.targets)]
   
      if target:IsAlive() then
         return target
      end
   end
   
   return nil

end

function GLSCO_COMBATANT:decloakRandomTarget(chance)

   chance = chance or 1.0

   local target = nil
   local diceRoll = math.random()
   if diceRoll <= chance then
   
      target = self:selectRandomTarget()
      if target ~= nil then
         target:decloak()
      end
   end
   
   return target

end

function GLSCO_COMBATANT:halt()

   if not self:IsAlive() then
      return
   end

   self.group:RouteStop()

end

function GLSCO_COMBATANT:resume()

   if not self:IsAlive() then
      return
   end

   self.group:RouteResume()

end

function GLSCO_COMBATANT:despawn()

   if not self:IsAlive() then
      return
   end

   local raiseEvent = false
   self.group:Destroy(raiseEvent)

end

-- Helper function to simulate infantry unit dismounting.
function GLSCO_COMBATANT:respawn(coordNearCarrier, hdg)

   local spawn = GLSCO_SPAWN:CreateSpawn(self.template, self:GetName())
                            :InitHeading(hdg)
   
   
   self.group = spawn:SpawnFromCoordinate(coordNearCarrier)

   --[[
   local inst = 
   {
      cache = {}, -- some properties of the group needs to be cached since mounted units are created and destroyed
      group = group,
      template = GLSCO_SPAWN:CreateSpawnTemplate(group),
      fsm = fsm,
      profile = nil,
      homeWP = nil,
      carrier = nil,
      passengers = {},
      activated = false,
      allowShift = true,
      requestHalt = false,
      requestResume = false,
      delayMission = false,
      requestLoad = false,
      requestUnload = false,
      moves = {},
      moveNow = nil,
      targets = {},
      roe = GLSCO_COMBATANT.ROE.SIMULATE,
      debug = false,
   }
   --]]


   -- Object state may have changed while this unit was riding.  The infantry that just dismounted
   -- will "inherit" the state of the carrier they were riding in.
   self.homeWP = self.carrier.homeWP
   self.allowShift = self.carrier.allowShift
   self.requestHalt = self.carrier.requestHalt
   self.requestResume = self.carrier.requestResume
   self.delayMission = self.carrier.delayMission
   self.requestLoad = self.carrier.requestLoad
   self.requestUnload = self.carrier.requestUnload
   self.moves = UTILS.DeepCopy(self.carrier.moves) -- that was a hard bug to find :(
   self.moveNow = self.carrier.moveNow
   self.roe = self.carrier.roe

end

function GLSCO_COMBATANT:unloadPassengers(maxTime)

   local carrierAlive = self:IsAlive()
   local delay = math.random(2, 4)
   for i = 1, #self.passengers do
       
      if not self.passengers[i]:IsAlive() then
         -- nothing do do
      elseif carrierAlive then
         delay = delay + math.random(2, 3)
         delay = math.min(delay, maxTime)
         self.passengers[i].fsm:__Unload(delay, self.passengers[i])
      else
         self.passengers[i].fsm:Died(self.passengers[i])
      end
   end

end

function GLSCO_COMBATANT:moveToCoord(coord, speed, useRoad)

   if not self:IsAlive() then
      return
   end
   
   if useRoad then
   
      -- For whatever reason I had to start passing in formation
	  -- to force unit to use a road.
      self.group:RouteGroundOnRoad(coord, speed, nil, "On Road")
	  --self.group:RouteGroundOnRoad(coord, speed)
   else
      self.group:RouteGroundTo(coord, speed)
   end

end

function GLSCO_COMBATANT:moveHome()

   if not self:IsAlive() then
      return
   end
   
   local homeHdg = self:GetHomeHeading()
   local homeCoord = self:GetHomeCoordinate()

   local startCoord = self.group:GetCoordinate()
   local distance = math.random(GLSCO.Settings.ARRIVAL_RADIUS_METERS + 15, GLSCO.Settings.ARRIVAL_RADIUS_METERS + 20)
   local recipHdg = homeHdg - math.random(170, 190)
   local recipCoord = COORDINATE:NewFromVec2(UTILS.Vec2Translate(startCoord:GetVec2(), distance, recipHdg))

   local speed = self.profile.TopSpeedKMH
   local newCoord = COORDINATE:NewFromVec2(homeCoord:GetRandomVec2InRadius(15))
   
   local route = {}
   table.insert(route, startCoord:WaypointGround(speed))
   
   if not self:isNear(homeCoord, GLSCO.Settings.ARRIVAL_RADIUS_METERS + 10) then
      table.insert(route, homeCoord:WaypointGround(speed))
   end
   
   table.insert(route, recipCoord:WaypointGround(speed))
   table.insert(route, newCoord:WaypointGround(speed))
   
   self.group:Route(route)
   
   return newCoord

end

function GLSCO_COMBATANT:moveNearCarrier()

   if not self.carrier:IsAlive() then
      return
   end

   local coordNearCarrier = COORDINATE:NewFromVec2(self.carrier:GetCoordinate():GetRandomVec2InRadius(5))
   self:moveToCoord(coordNearCarrier, self.profile.TopSpeedKMH, false)
   
end

function GLSCO_COMBATANT:isNearCarrier()

   if not self.carrier:IsAlive() then
      return true
   end

   return self:isNear(self.carrier:GetCoordinate(), GLSCO.Settings.ARRIVAL_RADIUS_METERS)

end

function GLSCO_COMBATANT:isInKillRange(target)

   --TODO: Kill range logic deprecated
   --[[
   if self:IsAlive() and target:IsAlive() then
      local distance = self:GetCoordinate():Get2DDistance(target:GetCoordinate())
      if distance <= self.profile.KillRange then
         return true
      end
   end
   --]]
   
   return false

end

function GLSCO_COMBATANT:isNear(coord, radius)

   if not self:IsAlive() then
      return true
   end

   local here = self:GetCoordinate()
   if not coord or not here then
      -- The combatant despawned between the alive-check above and now (GetCoordinate
      -- returns nil for a dead group), or no destination was passed. Treat as "arrived"
      -- rather than indexing a nil Coordinate inside MOOSE (the caught SCHEDULER crash
      -- and GetVec3 log flood seen when a combatant is killed mid-move).
      return true
   end

   return coord:IsInRadius(here, radius)

end

function GLSCO_COMBATANT:numberAlivePassengers()

   local cnt = 0
   for i = 1, #self.passengers do
      if self.passengers[i]:IsAlive() then
         cnt = cnt+1
      end
   end
   
   return cnt

end

function GLSCO_COMBATANT:numberRidingPassengers()

   if not self:IsIFV() then
      return -1
   end
   
   local cnt = 0
   for i = 1, #self.passengers do
      if self.passengers[i]:IsRiding() then
         cnt = cnt+1
      end
   end
   
   return cnt

end

function GLSCO_COMBATANT:allPassengersOnBoard()

   if not self:IsIFV() then
      return true
   end
   
   for i = 1, #self.passengers do
      if self.passengers[i]:IsAlive() and not self.passengers[i]:IsRiding() then
         return false
      end
   end
   
   return true

end

function GLSCO_COMBATANT:mergeProfiles()

   if self:IsIFV() then
      env.info("IFV: "..self:GetName())
   end

   local profile = GLSCO.GENERIC_PROFILE

   if self:IsInfantry() then
      profile = GLSCO.INFANTRY_PROFILE
   end
   
   if self:IsTank() then
      profile = GLSCO.TANK_PROFILE
   end
   
   if self:IsAirDefense() then
      profile = GLSCO.AD_PROFILE
   end
   
   local copy = UTILS.DeepCopy(profile.default)
   
   if not self.group then
      return copy
   end

   -- DCS 2.9.29 folded the CurrentHill pack into core: those units keep the
   -- vanilla id but their DisplayName gains a " [CH]" suffix, and the vanilla
   -- file is gone. "IFV BMP-3" is now "IFV BMP-3 [CH]", which missed this table
   -- and cost the BMP-3 its SalvoQty. Fall back to the bare name.
   local displayName = self:GetDisplayName()
   local override = profile[displayName]
      or profile[(displayName:gsub("%s*%[%u+%]$", ""))]
      or {}
   for key, val in pairs(override) do
      copy[key] = val
   end
   
   local cnt = #self.group:GetUnits()
   if cnt > 1 then
      local qty = math.floor((tonumber(copy["SalvoQty"]) * cnt * 0.75) + 0.5)
      env.warning("GLSCO_COMBATANT: Increasing SalvoQty since group contains more than 1 unit. name=["..self:GetName().."] unitCount="..cnt.." newQty="..qty)
      copy["SalvoQty"] = qty
   end

   return copy

end

function GLSCO_COMBATANT:drawState()

   if self.mark ~= nil then
      COORDINATE:RemoveMark(self.mark)
   end
   
   if not self.draw then
      return
   end
   
   if self:IsRiding() then
      return
   end
   
   local state = self.fsm:GetState()
   
   if self.visible then
      state = state.."*"
   end
   
   if self:IsIFV() and self:IsAlive() then
      local riding = self:numberRidingPassengers()
      local alive = self:numberAlivePassengers()
      state = state.." ("..riding.." of "..alive..")"
   end
   
   local strength = self:GetStrength()
   state = state.." "..(strength.alive/strength.total*100).."%"
   
   if self.group:IsAlive() then
      self.mark = self.group:GetCoordinate():TextToAll(state, -1, {0,0,0}, 1.0, nil, 0.0, 16, true)
   else
      self.mark = self.initWP:GetCoordinate(self:GetName()):TextToAll(state, -1, {0,0,0}, 1.0, nil, 0.0, 16, true)
   end

end

function GLSCO_COMBATANT:logState()

   local state =
   {
      NAME = self:GetName(),
      TYPE = self:GetDisplayName(),
      PROFILE = self.profile,
   }

   env.info("GLSCO_COMBATANT: "..UTILS.OneLineSerialize(state))

end

function GLSCO_COMBATANT:logDebug(msg)

   if self and self.debug then
      if self.group then
         env.info("GLSCO_COMBATANT [" .. self.group:GetName() .."]: " .. msg)
      else
         env.info("GLSCO_COMBATANT: " .. msg)
      end
   end

end

-- ========================================================================================================================
-- GLSCO_WP_OPTIONS
-- ========================================================================================================================
-- Commands associated with a waypoint.
-- 
GLSCO_WP_OPTIONS = {}

-- DEPRECATED
function GLSCO_WP_OPTIONS:GetStartTime()

   return self.start

end

function GLSCO_WP_OPTIONS:GetOffsetTime()

   return self.offset

end

function GLSCO_WP_OPTIONS:GetFlag()

   return self.flag

end

function GLSCO_WP_OPTIONS:GetFlagToSet()

   return self.setflag

end

function GLSCO_WP_OPTIONS:GetPhaseName()

   return self.phase

end

function GLSCO_WP_OPTIONS:GetSpeedKMH()

   return self.speed

end

function GLSCO_WP_OPTIONS:GetROE()

   return self.roe

end

function GLSCO_WP_OPTIONS:GetDeployment()

   return self.deployment

end

function GLSCO_WP_OPTIONS:ShouldUseRoads()

   return self.useRoads

end

function GLSCO_WP_OPTIONS:ShouldShift()

   return self.shift

end

function GLSCO_WP_OPTIONS:ShouldGoDirect()

   return self.direct

end

function GLSCO_WP_OPTIONS:GetStrength()

   return self.strength

end

function GLSCO_WP_OPTIONS:ProhibitRoads()

   self.useRoads = false

end

function GLSCO_WP_OPTIONS:New(startTime, offsetTime, phaseName, useRoads, shift, deployment, speed, roe, flag, setflag, direct, strength)

   if useRoads == nil then
      useRoads = false
   end
   
   if shift == nil then
      shift = true
   end
   
   if direct == nil then
      direct = false
   end
   
   local inst = 
   {
      start = startTime,
      offset = offsetTime,
      phase = phaseName,
      useRoads = useRoads,
      shift = shift,
      deployment = deployment,
      speed = speed,
      roe = roe,
      flag = flag,
      setflag = setflag,
      direct = direct,
      strength = strength,
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

-- ========================================================================================================================
-- GLSCO_WAYPOINT
-- ========================================================================================================================
-- Similar to a DCS waypoint, but is tailored for formations.  A formation is a collection
-- of combatants and every combatant has their own coordinate.  A GLSCO_WAYPOINT's coordinate
-- is the centroid of all combatants in this formation.
-- 
GLSCO_WAYPOINT = {}

-- Which way is the formation pointing
function GLSCO_WAYPOINT:GetHeading()

   return self.hdg

end

-- Has the formation been scaled up or down.
function GLSCO_WAYPOINT:GetScale()

   return self.scale

end

-- Get the coordinate of the combatant with the provide name.
function GLSCO_WAYPOINT:GetCoordinate(combatantName)

   return self.coords[combatantName]

end

--[[
function GLSCO_WAYPOINT:GetCentroid(combatantName, combatantCoord)

end
--]]

-- Get commands assocated with this waypoint.
function GLSCO_WAYPOINT:GetOptions()

   return self.options

end

-- Constructor used to create zeroeth waypoint.  All subsequent waypoints are
-- constructed relative to this one.
function GLSCO_WAYPOINT:NewInitial(combatants, hdg, options)

   local inst = GLSCO_WAYPOINT:new(0, hdg, 1.0, options)
   
   for i = 1, #combatants do
   
      if i == 1 then
         inst.coalition = combatants[i]:GetCoalition()
      end
   
      inst.coords[combatants[i]:GetName()] = combatants[i]:GetCoordinate()
   end
   
   return inst

end

-- Constructor to create a waypoint based on the zeroeth waypoint.
function GLSCO_WAYPOINT:CloneAndTranslate(num, newCoord, newHdg, newScale, newOptions)

   local clone = GLSCO_WAYPOINT:new(num, newHdg, newScale, newOptions)
   clone.coalition = self.coalition
   
   local centroid = self:CalcCentroid()
   local theta = self:calcTheta(self.hdg, newHdg or 0)
   local vec_trans = self:coordSubtract(centroid, newCoord)
   
   for key, value in pairs(self.coords) do
   
      local srcCoord = value
      local vec_vi = self:coordSubtract(centroid, srcCoord)
      local vec_vsi = self:coordScale(vec_vi, newScale or 1)
      local vec_vri = self:coordRotate(vec_vsi, theta)
      local vec_rot = self:coordSubtract(vec_vi, vec_vri)
      local destCoord = self:coordAdd(srcCoord, self:coordAdd(vec_trans, vec_rot))
      clone.coords[key] = destCoord
   
   end
   
   return clone

end

-- Internal contructor
function GLSCO_WAYPOINT:new(num, newHdg, newScale, newOptions)

   local deploy = "nil"
   if newOptions:GetDeployment() == GLSCO.Deployment.LOAD then
      deploy = "mount"
   elseif newOptions:GetDeployment() == GLSCO.Deployment.UNLOAD then
      deploy = "dismount"
   end
   
   local roe = "nil"
   if newOptions:GetROE() == GLSCO_COMBATANT.ROE.SIMULATE then
      roe = "sim"
   elseif newOptions:GetROE() == GLSCO_COMBATANT.ROE.KILL then
      roe = "kill"
   elseif newOptions:GetROE() == GLSCO_COMBATANT.ROE.HOLD then
      roe = "hold"
   end

   --[[
   env.info(string.format("GLSCO_WAYPOINT: num=%d; start=%s; offset=%s; phase=%s; hdg=%s; scale=%s; roads=%s; shift=%s; deploy=%s; speed=%s roe=%s flag=%s setflag=%s", 
                          num, newOptions:GetStartTime() or "nil", newOptions:GetOffsetTime() or "nil", 
                          newOptions:GetPhaseName() or "nil", newHdg or "nil", newScale or "nil", 
                          tostring(newOptions:ShouldUseRoads()) or "nil", tostring(newOptions:ShouldShift()) or "nil", deploy,
                          newOptions:GetSpeedKMH() or "nil", roe, newOptions:GetFlag() or "nil", newOptions:GetFlagToSet() or "nil"))
   --]]

   local inst = 
   {
      num = num,
      hdg = newHdg or 0,
      scale = newScale or 1.0,
      coords = {},
      options = newOptions,
      drawings = {},
      coalition = nil,
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

function GLSCO_WAYPOINT:Draw(isActive)

   self:Erase()
   
   if isActive then
      self:drawCentroid({0,1,0}, 30)
   else
      self:drawCentroid({0,0,0}, 10)
   end
   
   local rgb = GLSCO.GetRGB(self.coalition)
   for _, value in pairs(self.coords) do
      local mark = value:CircleToAll(10, -1, rgb, 0.8, rgb, 0.5, 1, true)
      table.insert(self.drawings, #self.drawings + 1, mark)
   end

end

function GLSCO_WAYPOINT:drawCentroid(rgb, size)

   local centroid = self:CalcCentroid()
   local mark = centroid:CircleToAll(size, -1, rgb, 0.8, rgb, 0.5, 1, true)
   table.insert(self.drawings, #self.drawings + 1, mark)

end

function GLSCO_WAYPOINT:Erase()

   for i = 1, #self.drawings do
      COORDINATE:RemoveMark(self.drawings[i])
   end
   
   self.drawings = {}

end

function GLSCO_WAYPOINT:CalcCentroid()

   local x = 0
   local z = 0
   local cnt = 0
   
   -- Centroid is avg of Xs and Zs
   for key, value in pairs(self.coords) do
      x = x + value.x
      z = z + value.z
      cnt = cnt + 1
   end
  
   if (cnt == 0) then
      return nil
   end
   
   return COORDINATE:New(x / cnt, 0, z / cnt)

end

function GLSCO_WAYPOINT:calcTheta(origHdg, newHdg)

   return newHdg - origHdg

end

function GLSCO_WAYPOINT:coordAdd(a, b)

   return COORDINATE:New(a.x + b.x, 0, a.z + b.z)

end

function GLSCO_WAYPOINT:coordSubtract(src, dest)

   return COORDINATE:New(dest.x - src.x, 0, dest.z - src.z)

end

function GLSCO_WAYPOINT:coordScale(coord, factor)

   return COORDINATE:New(coord.x*factor, 0, coord.z*factor)

end

function GLSCO_WAYPOINT:coordRotate(coord, theta)

   local rad = math.rad(theta)
   
   local x = coord.x*math.cos(rad) - coord.z*math.sin(rad)
   local z = coord.x*math.sin(rad) + coord.z*math.cos(rad)

   return COORDINATE:New(x, 0, z)

end

-- ========================================================================================================================
-- GLSCO_ROUTE
-- ========================================================================================================================
-- Similar to a DCS route, but is tailored for formations.
-- 
GLSCO_ROUTE = {}

-- Used to know if route has changed over time.  Represents timestamp of last known change.
function GLSCO_ROUTE:GetTimeStamp()

   return self.stamp

end

-- Function needed to help build menu items.
function GLSCO_ROUTE:GetPhaseNames()

   return self.phaseNames

end

function GLSCO_ROUTE:New(points, formation)

   local inst = 
   {
      stamp = timer.getTime0(),
      coalition = formation:GetCoalition(),
      initial = nil,
      waypoints = {},
      phaseNames = {},
      drawings = {},
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   inst:buildWPs(points, formation)
   inst:setTimeStamp()
   
   return inst

end

function GLSCO_ROUTE:setTimeStamp()

   self.stamp = timer.getAbsTime()

end

function GLSCO_ROUTE:buildWPs(points, formation)

   local prevHdg = formation:GetInitialHeading()
   local prevScale = 1
   local prevRoads = false
   local prevShift = true
   local prevSpeed = nil -- profile will be used if nil
   local prevROE = GLSCO_COMBATANT.ROE.SIMULATE
   
   -- Loop thru waypoints in order and parse any commands defined.
   -- If a waypoint doesn't define a particular command, then use value from
   -- previous waypoint(s)
   for index, point in ipairs(points) do
   
      local name = point.name or ""
      local hdg = self:extractHeading(name) or prevHdg
      local scale = self:extractScale(name) or prevScale
      local roads = self:extractRoads(name, prevRoads)
      local shift = self:extractShift(name, prevShift)
      local speed = self:extractSpeed(name) or prevSpeed
      local roe = self:extractROE(name) or prevROE

      local start = self:extractStartTime(name)
      local offset = self:extractOffsetTime(name)
      local phase = self:extractPhase(name)
      local deploy = self:extractDeployment(name)
      local flag = self:extractFlag(name)
      local setflag = self:extractFlagToSet(name)
      local direct = self:extractDirect(name, false)
      local strength = self:extractStrength(name)

      local options = GLSCO_WP_OPTIONS:New(start, offset, phase, roads, shift, deploy, speed, roe, flag, setflag, direct, strength)

      if index == 1 then
         self.initial = GLSCO_WAYPOINT:NewInitial(formation:GetCombatants(), hdg, options)
      else
         local coord = COORDINATE:New(point.x, 0, point.y)
         local waypoint = self.initial:CloneAndTranslate(index-1, coord, hdg, scale, options)
         table.insert(self.waypoints, waypoint)
         
         if phase ~= nil then
            self.phaseNames[phase] = phase
         end
      end
      
      prevHdg = hdg
      prevScale = scale
      prevRoads = roads
      prevShift = shift
      prevSpeed = speed
      prevROE = roe
      
   end
   
end

function GLSCO_ROUTE:GetWP(num)

   if num == 0 then
      return self.initial
   end

   return self.waypoints[num]

end

function GLSCO_ROUTE:GetWPs(min, max)
  
   if min == nil and max == nil then
      return self.waypoints
   end
   
   min = min or 1
   max = max or #self.waypoints
  
   local wps = {}
   for i = min, max do
      if i > #self.waypoints then
         return wps
      end
   
      table.insert(wps, self.waypoints[i])
   end
  
   return wps

end

-- Used in conjunction with custom maneuvers.
function GLSCO_ROUTE:OverrideRoute(newCoord, newHdg, newScale, options)

   self:setTimeStamp() -- change timestamp so that any scheduled waypoint movements are invalidated
   self:Erase()
   self.waypoints = {}
   
   local waypoint = self.initial:CloneAndTranslate(1, newCoord, newHdg, newScale, options)
   table.insert(self.waypoints, waypoint)

end

function GLSCO_ROUTE:Draw(destNum, text)

   self:Erase()

   local rgb = GLSCO.GetRGB(self.coalition)
   self.initial:Draw(destNum == 0)

   local prevCoord = self.initial:CalcCentroid()
   local mark = prevCoord:TextToAll(text, -1, {0,0,0}, 0.8, rgb, 0.15, 16, true)
   table.insert(self.drawings, #self.drawings + 1, mark)
   for i = 1, #self.waypoints do
   
      local curWp = self.waypoints[i]
      curWp:Draw(i == destNum)
      
      local curCoord = curWp:CalcCentroid()
      local mark = prevCoord:LineToAll(curCoord, -1, rgb, 0.8, 2, true)
      table.insert(self.drawings, #self.drawings + 1, mark)
      prevCoord = curCoord
   end

end

function GLSCO_ROUTE:Erase()

   for i = 1, #self.drawings do
      COORDINATE:RemoveMark(self.drawings[i])
   end
   
   self.initial:Erase()
   for i = 1, #self.waypoints do
      self.waypoints[i]:Erase()
   end
   
   self.drawings = {}

end

-- DEPRECATED
function GLSCO_ROUTE:extractStartTime(str)

   -- TODO: for now, don't wanna support

   return nil

   --[[
   if str == nil or str == "" then return nil end
   
   local time = nil
   for s in string.gmatch(string.lower(str), "t=(%d+)") do
      time = s + 0 --Add zero to remove leading zeroes, ex: 012 -> 12
      break
   end
   
   return time
   --]]

end

-- Parse offset from provided string.
function GLSCO_ROUTE:extractOffsetTime(str)

   if str == nil or str == "" then return nil end
   
   local time = nil
   for s in string.gmatch(string.lower(str), "t%+(%d+)") do
      time = s + 0 --Add zero to remove leading zeroes, ex: 012 -> 12
      break
   end
   
   return time

end

-- Parse phase name from provided string.
function GLSCO_ROUTE:extractPhase(str)

   if str == nil or str == "" then return nil end
   
   local phase = nil
   for s in string.gmatch(string.lower(str), "\"([^\"]+)\"") do
      phase = s
      break
   end
   
   return phase

end

-- Parse heading from provided string.
function GLSCO_ROUTE:extractHeading(str)

   if str == nil or str == "" then return nil end
   
   local hdg = nil
   for s in string.gmatch(string.lower(str), "hdg=(%d+)") do
      hdg = s + 0   --Add zero to remove leading zeroes, ex: 012 -> 12
      break
   end
   
   return hdg
   
end

-- Parse scale from provided string.
function GLSCO_ROUTE:extractScale(str)

   if str == nil or str == "" then return nil end
   
   local scale = nil
   for s in string.gmatch(string.lower(str), "scale=(%d?\.%d?)") do
      if (s ~= ".") then
         scale = s
         break
      end
   end
   
   return scale

end

-- Parse roads boolean from provided string.
function GLSCO_ROUTE:extractRoads(str, default)

   for s in string.gmatch(string.lower(str), "roads?=(%w+)") do
      if s == "y" or s == "yes" then
         return true
      elseif s == "n" or s == "no" then
         return false
      end
   end

   return default
   
end

-- Parse shift boolean from provided string.
function GLSCO_ROUTE:extractShift(str, default)

   for s in string.gmatch(string.lower(str), "shift=(%w+)") do
      if s == "y" or s == "yes" then
         return true
      elseif s == "n" or s == "no" then
         return false
      end
   end

   return default
   
end

-- Parse mount/dismount from provided string.
function GLSCO_ROUTE:extractDeployment(str)

   if str == nil or str == "" then return nil end
   
   for s in string.gmatch(string.lower(str), "(%w+)") do
      if s == "dismount" then
         return GLSCO.Deployment.UNLOAD
      elseif s == "mount" then
         return GLSCO.Deployment.LOAD
      end
   end
   
   return nil

end

-- Parse unit speed from provided string.
function GLSCO_ROUTE:extractSpeed(str)

   if str == nil or str == "" then return nil end
   
   local speed = nil
   for s in string.gmatch(string.lower(str), "speed=(%d+)") do
      speed = s + 0   --Add zero to remove leading zeroes, ex: 012 -> 12
      break
   end
   
   return speed
   
end

-- Parse ROE from provided string.
function GLSCO_ROUTE:extractROE(str)

   if str == nil or str == "" then return nil end
   
   for s in string.gmatch(string.lower(str), "roe=(%w+)") do
      if s == "simulate" then
         return GLSCO_COMBATANT.ROE.SIMULATE
      elseif s == "kill" then
         return GLSCO_COMBATANT.ROE.KILL
      elseif s == "hold" then
         return GLSCO_COMBATANT.ROE.HOLD
      end
   end
   
   return nil

end

-- Parse flag from provided string.
function GLSCO_ROUTE:extractFlag(str)

   if str == nil or str == "" then return nil end

   local flag = nil
   for s in string.gmatch(string.lower(str), "flag=(%w+)") do
      flag = s
      break
   end

   return flag
   
end

-- Parse flag to set from provided string.
function GLSCO_ROUTE:extractFlagToSet(str)

   if str == nil or str == "" then return nil end

   local flag = nil
   for s in string.gmatch(string.lower(str), "flag%+(%w+)") do
      flag = s
      break
   end

   return flag
   
end

-- Parse direct boolean from provided string.
function GLSCO_ROUTE:extractDirect(str, default)

   for s in string.gmatch(string.lower(str), "direct=(%w+)") do
      if s == "y" or s == "yes" then
         return true
      elseif s == "n" or s == "no" then
         return false
      end
   end

   return default
   
end

-- Parse strength from provided string.
function GLSCO_ROUTE:extractStrength(str)

   if str == nil or str == "" then return nil end
   
   local strength = nil
   for s in string.gmatch(string.lower(str), "strength=(%d?\.%d?)") do
      if (s ~= ".") then
         strength = tonumber(s)
         break
      end
   end
   
   return strength

end

-- ========================================================================================================================
-- GLSCO_PATH_PREDICTION
-- ========================================================================================================================
--
GLSCO_PATH_PREDICTION = {}

function GLSCO_PATH_PREDICTION:New(minNumCoords, maxNumCoords, maxAgeSecs, minDistanceTraveled)

   local inst = 
   {
      minCoords = minNumCoords or 3,
      maxCoords = maxNumCoords or 10,
      maxAge = maxAgeSecs or 120,
      minDistance = minDistanceTraveled or 100,
      coords = {},
      drawings = {},
   } 
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

function GLSCO_PATH_PREDICTION:GetMostRecentNCoordinates(n)

   local coords = {}
   for i = #self.coords, 1, -1 do
      table.insert(coords, self.coords[i].coord)
      
      if #coords >= n then
         return coords
      end
   end
   
   return coords

end

function GLSCO_PATH_PREDICTION:AddCoordinate(coord, t)

   --env.info("GLSCO_PATH_PREDICTION: ADD Coordinate")
   table.insert(self.coords, {coord=coord, t=t})
   self:invalidate()
   --self:draw()

end

function GLSCO_PATH_PREDICTION:PredictCoordinate(tFutureSecs)

   --env.info("GLSCO_PATH_PREDICTION: PREDICT Coordinate")

   -- Must have min coords required to predict.
   if #self.coords < self.minCoords then 
      --env.info("GLSCO_PATH_PREDICTION: not enough coords")
      return nil 
   end
   
   -- Must travel min distance to predict.
   if self:calcDistance() < self.minDistance then
      --env.info("GLSCO_PATH_PREDICTION: distance too short")
      return nil
   end
   
   --TODO: implement linear regression
   return self.coords[#self.coords].coord

end

function GLSCO_PATH_PREDICTION:ClearCoordinates()

   self.coords = {}

end

function GLSCO_PATH_PREDICTION:invalidate()

   --UTILS.PrintTableToLog(self.coords)

   if #self.coords == 0 then 
      return 
   end

   -- Remove any entries over max capacity
   while #self.coords > self.maxCoords do
      table.remove(self.coords, 1)
   end

   -- Remove entries that are too old.
   local t0 = self.coords[#self.coords].t
   --env.info("GLSCO_PATH_PREDICTION: t0="..t0)

   for i = #self.coords, 1, -1 do
      local ti = self.coords[i].t
      
      if (t0 - ti) > self.maxAge then
         env.info("GLSCO_PATH_PREDICTION: age="..(t0-ti))
         table.remove(self.coords, i)
      end
   end

end

function GLSCO_PATH_PREDICTION:calcDistance()

   if #self.coords <= 1 then
      return 0
   end
   
   local oldestCoord = self.coords[1].coord
   local newestCoord = self.coords[#self.coords].coord
   local distance = newestCoord:Get2DDistance(oldestCoord)
   
   --env.info("GLSCO_PATH_PREDICTION: distance="..distance)
   
   return distance

end

function GLSCO_PATH_PREDICTION:draw()

   -- draw text on most recent coord
   -- draw circles for each coord w/ time t
   -- draw circle prediction
   self:erase()
   
   for i = 1, #self.coords do
      --COORDINATE:CircleToAll(Radius,Coalition,Color,Alpha,FillColor,FillAlpha,LineType,ReadOnly,Text)
      --local circleMark = self.coords[i].coord:CircleToAll(5, nil, {0.5,0.5,0.5}, 0.8, {0.5,0.5,0.5}, 0.5)
      --table.insert(self.drawings, circleMark)
      
      --COORDINATE:TextToAll(Text,Coalition,Color,Alpha,FillColor,FillAlpha,FontSize,ReadOnly)
      local textMark = self.coords[i].coord:TextToAll(self.coords[i].t.."secs", nil, {1,1,1})
      table.insert(self.drawings, textMark)
   end
   
end

function GLSCO_PATH_PREDICTION:erase()

   for i = 1, #self.drawings do
      COORDINATE:RemoveMark(self.drawings[i])
   end

   self.drawings = {}

end

-- ========================================================================================================================
-- GLSCO_MOVEMENT_TRACKER
-- ========================================================================================================================
--
GLSCO_MOVEMENT_TRACKER = {}

GLSCO_MOVEMENT_TRACKER.POLL_INTERVAL_SECS = 6
GLSCO_MOVEMENT_TRACKER.FUTURE_T_OFFSET_SECS = 60
GLSCO_MOVEMENT_TRACKER.IDLE_THRESHOLD_NUM_POLLS = 3

function GLSCO_MOVEMENT_TRACKER:New(combatant)

   local inst = 
   {
      combatant = combatant,
      prediction = GLSCO_PATH_PREDICTION:New(2, 10, 120, 100),
      timer = nil,
      moving = false,
      courseChange = nil,
      destReached = nil,
      mark = nil,
   } 
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

function GLSCO_MOVEMENT_TRACKER:Start()

   self.timer = TIMER:New(GLSCO_MOVEMENT_TRACKER.poll, self)
   self.timer:Start(math.random(1, 3), GLSCO_MOVEMENT_TRACKER.POLL_INTERVAL_SECS + math.random(0, 4))
   
end

function GLSCO_MOVEMENT_TRACKER:OnCourseChange(callback)

   self.courseChange = callback

end

function GLSCO_MOVEMENT_TRACKER:OnDestinationReached(callback)

   self.destReached = callback

end

function GLSCO_MOVEMENT_TRACKER:raiseCourseChange(newCoordinate, newHeading, newSpeed)

   if self.courseChange ~= nil then
      self.courseChange(newCoordinate, newHeading, newSpeed)
   end

end

function GLSCO_MOVEMENT_TRACKER:raiseDestinationReached(coordinate, heading)

   if self.destReached ~= nil then
      self.destReached(coordinate, heading)
   end

end

function GLSCO_MOVEMENT_TRACKER:poll()

   --env.info("GLSCO_FOLLOW_LEADER: polling...")

   if not self.combatant:IsAlive() then
      env.warning("GLSCO_MOVEMENT_TRACKER: leader died")
      self.timer:Stop(1)
      return
   end
   
   self:draw()
   
   if self.combatant:IsMoving() then
      self.prediction:ClearCoordinates()
      return
   end
   
   local currentTSecs = self:getTSecs()
   self.prediction:AddCoordinate(self.combatant:GetCoordinate(), currentTSecs)
   
   if self.moving and self:isIdle() then
      --env.info("GLSCO_MOVEMENT_TRACKER: destination reached")
      self.prediction:ClearCoordinates()
      self:raiseDestinationReached(self.combatant:GetCoordinate(), self.combatant:GetHeading())
      self.moving = false
      return
   end

   local futureTSecs = currentTSecs + GLSCO_MOVEMENT_TRACKER.FUTURE_T_OFFSET_SECS
   local predictCoord = self.prediction:PredictCoordinate(futureTSecs)
   
   if predictCoord ~= nil then
      --env.info("GLSCO_MOVEMENT_TRACKER: course change")
      local kmh = self.combatant:GetSpeedKMH()
      --local kph = UTILS.MpsToKmph(mps)
      local speed = UTILS.Clamp(kmh, 40, 72) -- 25 to 45 mph
      self:raiseCourseChange(predictCoord, self.combatant:GetHeading(), speed)
      self.moving = true
      return
   end

end

function GLSCO_MOVEMENT_TRACKER:isIdle()

   local coords = self.prediction:GetMostRecentNCoordinates(GLSCO_MOVEMENT_TRACKER.IDLE_THRESHOLD_NUM_POLLS)
   
   if coords == nil or #coords == 0 then 
      return false 
   end
   
   --UTILS.PrintTableToLog(coords)
   
   local prevX = nil
   local prevY = nil
   for _, coord in ipairs(coords) do
      local vec2 = coord:GetVec2()
      
      if prevX == nil then
         prevX = math.floor(vec2.x)
         prevY = math.floor(vec2.y)
      elseif prevX ~= math.floor(vec2.x) or prevY ~= math.floor(vec2.y) then
         --env.warning("GLSCO_MOVEMENT_TRACKER: coords don't match")
         return false
      end
   end
   
   --env.info("GLSCO_MOVEMENT_TRACKER: coords match")
   return true

end

function GLSCO_MOVEMENT_TRACKER:getTSecs()

   return math.floor(timer.getAbsTime() - timer.getTime0())

end

function GLSCO_MOVEMENT_TRACKER:draw()

   self:erase()

   local coal = self.combatant:GetCoalition()
   --local rgb = GLSCO.GetRGB()
   local coord = self.combatant:GetCoordinate()
   self.mark = coord:TextToAll("LEAD", coal, {1,1,1}, 0.8, nil, 0, 12, true)

end

function GLSCO_MOVEMENT_TRACKER:erase()

   if self.mark ~= nil then
      COORDINATE:RemoveMark(self.mark)
   end

end

-- ========================================================================================================================
-- GLSCO_FORMATION
-- ========================================================================================================================
-- Generic name for a grouping of combatants that maintain formation while moving across the map.
-- The ideal size of the formation is probably the size of a US Army Company.
-- The main purpose of a formation is to associate units together as a single fighting unit 
-- (aka a combatant), but each unit moves independently from one another.  This allows formation
-- to move across the map and still make forward progress if any individual unit gets stuck on
-- terrain features.
-- 
GLSCO_FORMATION = {}

function GLSCO_FORMATION:GetName()

   return self.name

end

-- Rotations of the formation are based on this initial heading.  If a formation is line abreast and
-- you want it to face due east, you can change its heading to 090.  However, if the initial heading
-- is not correct, the formation may appear to be facing some other direction other than east.
-- It's up to the mission maker to set the initial heading when placing late-activated units on the map
-- The heading can of course be any direction, but should represent what the miz maker considers which
-- way the formation is pointing on mission start.
function GLSCO_FORMATION:GetInitialHeading()

   return self.hdg or 0

end

function GLSCO_FORMATION:GetCoalition()

   return self.coalition or coalition.side.NEUTRAL

end

function GLSCO_FORMATION:GetCombatants()

   return self.combatants

end

function GLSCO_FORMATION:GetRoute()

   return self.route

end

function GLSCO_FORMATION:GetPercentAlive()

   local alive = 0
   local total = 0.0
   for _, combatant in ipairs(self.combatants) do
   
      local strength = combatant:GetStrength()   
      alive = alive + strength.alive
      total = total + strength.total  
      --env.info("tuba: comb="..combatant:GetName().." alive="..strength.alive.." total="..strength.total)
   end
   --env.info("tuba2: alive="..alive.." total="..total)
   
   if total == 0 then 
      return 0 
   end
   
   return alive / total

end

function GLSCO_FORMATION:New(name, initialHdg)

   local inst = 
   {
      name = name,
      hdg = initialHdg,
      coalition = nil,
      route = nil,
      combatants = {},
      leadTracker = nil,
      curWpNum = 0,
      draw = false,
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

-- NOTE: Must be populated with all combatants before route is initialized!
function GLSCO_FORMATION:InitRoute(points)

   if #self.combatants == 0 then
      env.warning("GLSCO_FORMATION: initializing route without combatants!")
   end

   self.route = GLSCO_ROUTE:New(points, self)
   local homeWP = self.route:GetWP(0)
  
   for i = 1, #self.combatants do
   
      local carrier = nil
      if self.combatants[i]:IsInfantry() then
         carrier = self:findNearestCarrier(self.combatants[i]:GetCoordinate())
         self.combatants[i]:AssignCarrier(carrier)
      end
   
      self.combatants[i]:Initialize(homeWP)
      
   end

   env.info("GLSCO_FORMATION: Formation ["..self.name.."] route initialized.")

end

function GLSCO_FORMATION:AddCombatant(combatant)

   if combatant.group == nil then
      env.error("GLSCO_FORMATION: group is nil")
      return
   end
   
   if #combatant.group:GetUnits() > 1 then
      env.warning("GLSCO_FORMATION: combatant contains more than 1 unit!")
   end

   -- look for coalition mismatch
   if self.coalition == nil then
      self.coalition = combatant.group:GetCoalition()
   elseif self.coalition ~= combatant.group:GetCoalition() then
      env.error("GLSCO_FORMATION: attempt to add combatant from a different coalition.")
      return
   end
   
   table.insert(self.combatants, #self.combatants + 1, combatant)

end

function GLSCO_FORMATION:Activate()

   for i = 1, #self.combatants do
      self.combatants[i]:Activate()
      
      if self.combatants[i]:IsLeader() and self.leadTracker == nil then
         self.leadTracker = GLSCO_MOVEMENT_TRACKER:New(self.combatants[i])
         self.leadTracker:Start()
         
         local formation = self
         local combatant = self.combatants[i]
         
         self.leadTracker:OnCourseChange(function(coord, hdg, speed) 
            combatant:Lead()
            local centroid = formation:calcCentroidRelativeToCombatant(combatant)
            formation:FollowLeader(centroid, hdg, speed) 
         end)

         self.leadTracker:OnDestinationReached(function(coord, hdg)
            combatant:Follow()
            local centroid = formation:calcCentroidRelativeToCombatant(combatant)
            formation:MoveToCustomWP(centroid, hdg) 
         end)
      end
   end

end

function GLSCO_FORMATION:calcCentroidRelativeToCombatant(combatant)

   --env.info("GLSCO_FORMATION: calcCentroidRelativeToCombatant")

   --return combatant:GetCoordinate()

   local wp0 = self.route:GetWP(0)
   
   if wp0 == nil then 
      return combatant:GetCoordinate() 
   end

   local unitCoord = wp0:GetCoordinate(combatant:GetName())
   local centroid = wp0:CalcCentroid()
   local origHdg = wp0:GetHeading()
   local newHdg = combatant:GetHeading()
   local dirVec3 = unitCoord:GetDirectionVec3(centroid)
   local angle = unitCoord:GetAngleDegrees(dirVec3) + (newHdg - origHdg)
   local distance = unitCoord:Get2DDistance(centroid)
   
   return combatant:GetCoordinate():Translate(distance, angle)

   --COORDINATE:GetDirectionVec3(TargetCoordinate)
   --COORDINATE:GetAngleDegrees(DirectionVec3)
   --POINT_VEC3:Translate(Distance,Angle,Keepalt,Overwrite)

end

function GLSCO_FORMATION:Deactivate()

   for i = 1, #self.combatants do
      self.combatants[i]:Deactivate()
   end

end

function GLSCO_FORMATION:Destroy()

   for i = 1, #self.combatants do
      self.combatants[i]:Destroy()
   end

end

function GLSCO_FORMATION:Halt()

   for i = 1, #self.combatants do
      self.combatants[i]:Halt()
   end

end

function GLSCO_FORMATION:Resume()

   for i = 1, #self.combatants do
      self.combatants[i]:Resume()
   end

end

--[[
function GLSCO_FORMATION:Load()

   for i = 1, #self.combatants do
      self.combatants[i]:Load()
   end

end

function GLSCO_FORMATION:Unload()

   for i = 1, #self.combatants do
      self.combatants[i]:Unload()
   end

end
--]]

function GLSCO_FORMATION:MoveToWP(num, now)

   if num <= 0 then
      return
   end
   
   if self.curWpNum >= num then
      -- We've already moved to this waypoint
      return
   end

   local wps = self.route:GetWPs(self.curWpNum+1, num)
   
   if self:shouldGoDirectlyToLastWaypoint(wps) then
      -- We need to move directly to last waypoint, skipping all intermediate.
      local lastWp = wps[#wps]
      wps = {lastWp}
      now = true
   end

   for _, wp in ipairs(wps) do
   
      for i = 1, #self.combatants do

         if now == true then
            self.combatants[i]:MoveNow(wp)
         else
            self.combatants[i]:Move(wp)
         end
      end
   end

   -- TODO: protect against trying to move to num greater than # of waypoints
   self.curWpNum = num
   
   if self.draw then
      self:Draw()
   end

end

function GLSCO_FORMATION:MoveToPhase(phaseName)

   if phaseName == nil or phaseName == "" then
      return
   end
   
   local phase = string.lower(phaseName)
   env.info("GLSCO_FORMATION: phase="..phase)
   
   local wps = self.route:GetWPs()
   local wpNum = 0
   
   for num, wp in ipairs(wps) do
   
      if string.lower(wp:GetOptions():GetPhaseName() or "") == phase then
         wpNum = num
         -- keep searching in case there are more wps with this phase name.
      end
   end
   
   if wpNum > 0 then
      self:MoveToWP(wpNum)
   end

end

function GLSCO_FORMATION:FollowLeader(coord, hdg, speed)

   local curWp = self.route:GetWP(self.curWpNum)
   
   if curWp == nil then
      env.error("how did I get here wp="..(self.curWpNum or "nil"))
      return
   end
   
   local curOptions = curWp:GetOptions()
   local newOptions = GLSCO_WP_OPTIONS:New(nil, nil, nil, false, curOptions:ShouldShift(), nil, speed, nil, nil, nil, nil, nil)
   
   self:MoveToCustomWP(coord, hdg, nil, newOptions)

end

function GLSCO_FORMATION:MoveToCustomWP(coord, hdg, scale, options)

   local curWp = self.route:GetWP(self.curWpNum)
   
   if curWp == nil then
      env.error("how did I get here wp="..(self.curWpNum or "nil"))
      return
   end
   
   if options == nil then
      options = curWp:GetOptions()
   end
   
   -- Use newest values if available, otherwise continue to use
   -- values of current current waypoint we are about to move away from.
   hdg = hdg or curWp:GetHeading()
   scale = scale or curWp:GetScale()
   local useRoads = options:ShouldUseRoads() or curWp:GetOptions():ShouldUseRoads()
   local shift = options:ShouldShift() or curWp:GetOptions():ShouldShift()
   local deploy = options:GetDeployment()
   local speed = options:GetSpeedKMH() or curWp:GetOptions():GetSpeedKMH()
   local roe = options:GetROE() or curWp:GetOptions():GetROE()
   local flag = options:GetFlag()
   local setflag = options:GetFlagToSet()
   local direct = nil
   local strength = nil
   
   local mergedOptions = GLSCO_WP_OPTIONS:New(nil, nil, nil, useRoads, shift, deploy, speed, roe, flag, setflag, direct, strength)
   self.route:OverrideRoute(coord, hdg, scale, mergedOptions)
   self.curWpNum = 0
   self:MoveToWP(1, true)

end

function GLSCO_FORMATION:Smoke()

   for i = 1, #self.combatants do
      self.combatants[i]:Smoke()
   end

end

function GLSCO_FORMATION:Draw()

   self.draw = true
   self.route:Draw(self.curWpNum, self.name)
   
   for i = 1, #self.combatants do
      self.combatants[i]:Draw()
   end

end

function GLSCO_FORMATION:Erase()

   self.draw = false
   self.route:Erase()
   
   for i = 1, #self.combatants do
      self.combatants[i]:Erase()
   end

end

function GLSCO_FORMATION:HoldFire()

   for i = 1, #self.combatants do
      self.combatants[i]:HoldFire()
   end

end

function GLSCO_FORMATION:SimulateFire()

   for i = 1, #self.combatants do
      self.combatants[i]:SimulateFire()
   end

end

function GLSCO_FORMATION:ShootToKill()

   for i = 1, #self.combatants do
      self.combatants[i]:ShootToKill()
   end

end

function GLSCO_FORMATION:Cloak()

   for i = 1, #self.combatants do
      self.combatants[i]:Cloak()
   end

end

function GLSCO_FORMATION:Decloak(duration)

   for i = 1, #self.combatants do
      self.combatants[i]:Decloak(1, duration)
   end

end

function GLSCO_FORMATION:findNearestCarrier(coord)

   -- must be IFV
   -- must be within 2000m

   local nearest = nil
   local minDistance = 10000
   for i = 1, #self.combatants do
   
      if self.combatants[i]:IsIFV() then
         local distance = coord:Get2DDistance(self.combatants[i]:GetCoordinate())
         if distance < minDistance then
            nearest = self.combatants[i]
            minDistance = distance
         end
      end
   
   end

   if minDistance > 2000 then
      return nil
   else
      env.info("Nearest: "..nearest:GetName().." dist="..minDistance)
      return nearest
   end

end

function GLSCO_FORMATION:shouldGoDirectlyToLastWaypoint(wps)

   local lastWp = wps[#wps]
   return lastWp:GetOptions():ShouldGoDirect()

end

-- ========================================================================================================================
-- GLSCO_SPOTTER
-- ========================================================================================================================
-- 
--
GLSCO_SPOTTER = {}

function GLSCO_SPOTTER:New(group, battlefield)

   if group == nil then
      env.error("GLSCO_SPOTTER: group is nil")
   end

   local t = 
   {
      group = group,
      battle = battlefield,
      enemyCoalition = GLSCO_SPOTTER.getEnemyCoalition(group:GetCoalition()),
      timer = nil,
      radiusMeters = nil,
      durationSecs = nil,
      chance = 1.0,
   } 
   
   local mt = {}
   mt.__index = self
   setmetatable(t, mt)
   
   return t

end

function GLSCO_SPOTTER:StartSpotting(intervalSecs, radiusNm, detectedDurationSecs, detectionChance)

   if not self.group:IsAlive() or self.timer ~= nil then
      return
   end

   self.radiusMeters = UTILS.NMToMeters(radiusNm or 1)
   self.durationSecs = detectedDurationSecs or 60
   self.chance = detectionChance or 1.0
   self.timer = TIMER:New(GLSCO_SPOTTER.poll, self)
   self.timer:Start(1, intervalSecs)

end

function GLSCO_SPOTTER:StopSpotting()

   if timer ~= nil then
      self.timer:Stop(1)
      self.timer = nil
   end

end

function GLSCO_SPOTTER:poll()

   env.info("GLSCO_SPOTTER: polling...")

   if not self.group:IsAlive() then
      self:StopSpotting()
      return
   end
   
   local coord = self.group:GetCoordinate()
   local formations = self.battle:GetFormations()
   
   for _, formation in ipairs(formations) do
      self:pollCombatants(coord, formation)
   end
   
   --self:draw()
      
end

function GLSCO_SPOTTER:pollCombatants(coord, formation)

   local combatants = formation:GetCombatants()
      
   -- We are only interested in spotting enemy forces
   if formation:GetCoalition() ~= self.enemyCoalition then
      return
   end
      
   for _, combatant in ipairs(combatants) do
      -- See if combatant in range of spotter
      if combatant:IsAlive() and coord:Get2DDistance(combatant:GetCoordinate()) <= self.radiusMeters then
         
         local diceRoll = 1.0 - math.random()
         if self.chance >= diceRoll and coord:IsLOS(combatant:GetCoordinate()) then
            local delay = math.random(1, 15)
            combatant:Decloak(delay, self.durationSecs)
            env.info("GLSCO_SPOTTER: decloaking name="..combatant:GetName())
         end
      end
   end

end

function GLSCO_SPOTTER:draw()

   if self.mark ~= nil then
      COORDINATE:RemoveMark(self.mark)
   end
   
   local coord = self.group:GetCoordinate()
   self.mark = coord:CircleToAll(self.radiusMeters, nil, {0,0,0}, 1.0, {1,1,1}, 0.0)

end

function GLSCO_SPOTTER.getEnemyCoalition(_coalition)

   if _coalition == coalition.side.NEUTRAL then
      return _coalition
   elseif _coalition == coalition.side.RED then
      return coalition.side.BLUE
   else
      return coalition.side.RED
   end   

end

--[[
function GLSCO_SPOTTER:getEnemyCoalitionName(_coalition)
   
   return self:getCoalitionName(self:getEnemyCoalition(_coalition))
end



function GLSCO_SPOTTER:getCoalitionName(_coalition)

   if _coalition == coalition.side.NEUTRAL then
      return "neutral"
   elseif _coalition == coalition.side.RED then
      return "red"
   else
      return "blue"
   end   

end
--]]


-- ========================================================================================================================
-- GLSCO_TARGETS
-- ========================================================================================================================
-- Internally used to choose targets for all combatants.
--
GLSCO_TARGETS = {}

function GLSCO_TARGETS:New()

   local t = 
   {
      units = {}
   } 
   
   local mt = {}
   mt.__index = self
   setmetatable(t, mt)
   
   return t

end

function GLSCO_TARGETS:AddTargetInLOS(unitName, distance, combatant)

   if self.units[unitName] == nil then
      self.units[unitName] = {}
   end
   
   table.insert(self.units[unitName], #self.units[unitName] + 1, {distance = distance, target = combatant})

end

function GLSCO_TARGETS:GetTopN(unitName, n)

   if not self.units[unitName] then
      return {}
   end

   local ordered = {}
   for key, value in pairs(self.units[unitName]) do
      table.insert(ordered, #ordered + 1, value)
   end
   table.sort(ordered, function(a, b) return a.distance < b.distance end)

   local topN = {}
   for i = 1, n do
      
      if i > #ordered then
         break
      end
      
      table.insert(topN, #topN + 1, ordered[i].target)
      
   end
   
   return topN

end

-- ========================================================================================================================
-- GLSCO_TRACKER
-- ========================================================================================================================
-- Automatically broadcasts targeting information to all combatants.  This is necessary since all units are invisible.
-- 
GLSCO_TRACKER = {}

function GLSCO_TRACKER:New()

   local inst = 
   {
      blue = {},
      red = {},
      scheduler = SCHEDULER:New()
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

function GLSCO_TRACKER:RegisterFormation(formation)

   local combatants = formation:GetCombatants()
   self:register(combatants)

end

function GLSCO_TRACKER:Start(interval)

   self.schedId = self.scheduler:Schedule(self, self.BroadcastNow, nil, 5, interval, 0.2)

end

function GLSCO_TRACKER:Stop()

   self.scheduler:Stop(self.schedId)
   self.schedId = nil

end

function GLSCO_TRACKER:BroadcastNow()

   self:broadcast()

end

function GLSCO_TRACKER:register(combatants)

   for i = 1, #combatants do
      if (combatants[i]:GetCoalition() == coalition.side.BLUE) then
         table.insert(self.blue, #self.blue + 1, combatants[i])
      elseif (combatants[i]:GetCoalition() == coalition.side.RED) then
         table.insert(self.red, #self.red + 1, combatants[i])
      end
   end

end

function GLSCO_TRACKER:broadcast()

   -- THIS IS A CRITICAL FUNCTION, ALL EFFORT MUST BE MADE TO RUN PERFORMANT
   -- This function contains a O(n^2) loop, so as the number of units scales on the battlefield, 
   -- this function will slow down. 

   env.info("GLSCO_TRACKER: Providing targeting info to all combatants...")

   local targets = GLSCO_TARGETS:New()

--[[

  LOOP1
     remove dead
     get coords
  
  LOOP2
     get distance
     exclude distance over max distance
     check los
     
--]] 

   -- Remove any blue units that are dead
   local blue = {}
   for i = #self.blue, 1, -1 do
      if self.blue[i].group:IsAlive() then
         table.insert(blue, #blue + 1, {name = self.blue[i]:GetName(), coord = self.blue[i]:GetCoordinate(), combatant = self.blue[i]})
      else
         table.remove(self.blue, i)
      end
   end
   
   -- Remove any red units that are dead
   local red = {}
   for i = #self.red, 1, -1 do
      if self.red[i].group:IsAlive() then
         table.insert(red, #red + 1, {name = self.red[i]:GetName(), coord = self.red[i]:GetCoordinate(), combatant = self.red[i]})
      else
         table.remove(self.red, i)
      end
   end
   
   -- Compare each blue unit to each red units, except if beyond 2nm and not in LOS.
   -- Checking distance first made a huge impact on performance, since distance calculating
   -- is way more performant then invoking DCS API to calculate LOS.
   local maxDistance = UTILS.NMToMeters(2)
   for i = 1, #blue do
      for j = 1, #red do
         local distance = blue[i].coord:Get2DDistance(red[j].coord)
         if distance < maxDistance then
            if blue[i].coord:IsLOS(red[j].coord, 4) then
               targets:AddTargetInLOS(blue[i].name, distance, red[j].combatant)
               targets:AddTargetInLOS(red[j].name, distance, blue[i].combatant)
            end
         end  
      end
   end
   
   -- Update all blue units with their 10 closest targets.
   for i = 1, #self.blue do
      local combatants = targets:GetTopN(self.blue[i]:GetName(), 10)
      self.blue[i]:SetTargetList(combatants)
   end
   
   -- Update all red units with their 10 closest targets.
   for i = 1, #self.red do
      local combatants = targets:GetTopN(self.red[i]:GetName(), 10)
      self.red[i]:SetTargetList(combatants)
   end
  
   env.info("GLSCO_TRACKER: done")

end

-- ========================================================================================================================
-- GLSCO_SCHEDULER
-- ========================================================================================================================
-- Ensures formations automatically move to waypoints under these 3 conditions...
-- 1. An offset waypoint command has triggered
-- 2. A flag waypoint command has triggered
-- 3. A strength waypoint command went below a threshold
-- 
GLSCO_SCHEDULER = {}

function GLSCO_SCHEDULER:New()

   local inst = 
   {
      scheduler = SCHEDULER:New(),
      schedules = 
      {
         index = 0,
         list = {},
      },
      offset = 0,
      disabled = false,
      formations = {},
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

function GLSCO_SCHEDULER:RegisterFormation(formation)

   if formation == nil then
      env.error("TODO: formation is nil")
      return
   end
   
   table.insert(self.formations, formation)

end

function GLSCO_SCHEDULER:Start()

   self.offset = GLSCO_SCHEDULER.getSecondsFromMissionStart()
   env.info("GLSCO_SCHEDULER: Mission Started at t="..self.offset.." seconds")

   for _, formation in ipairs(self.formations) do
      self:schedule(formation)
   end

end

function GLSCO_SCHEDULER:Stop()

end

function GLSCO_SCHEDULER:DisableSchedules(_coalition)

   self.disabled = true

   --[[
   for _, formation in ipairs(self.formations) do
      if formation:GetCoalition() == _coalition then
         self:disable(formation)
      end
   end
   --]]

end

function GLSCO_SCHEDULER:schedule(formation)

   if self.disabled then
      env.warning("GLSCO_SCHEDULER: schedules are disabled")
      return
   end

   local scheduler = self
   local route = formation:GetRoute()
   local stamp = route:GetTimeStamp()
   local wps = route:GetWPs()
   
   for num, wp in ipairs(wps) do
      
      --[[  DEPRECATED
      local start = wp:GetOptions():GetStartTime()
      if start ~= nil then
         local elapsedSecs = GLSCO_SCHEDULER.getSecondsFromMissionStart()
         local startDelay = start*60 - elapsedSecs
         env.info("GLSCO_SCHEDULER: formation="..formation:GetName().."; wp="..num..";  t="..start.." will start in "..startDelay.." seconds")
         self.scheduler:Schedule(nil, GLSCO_SCHEDULER.doAction, {scheduler, formation, num, stamp}, math.max(startDelay, 0))
      end
      --]]
      
      local offset = wp:GetOptions():GetOffsetTime()
      if offset ~= nil then
         local offsetDelay = offset*60
         env.info("GLSCO_SCHEDULER: formation="..formation:GetName().."; wp="..num..";  t+"..offset.." will start in "..offsetDelay.." seconds")
         self.scheduler:Schedule(nil, GLSCO_SCHEDULER.doAction, {scheduler, formation, num, stamp}, offsetDelay)
      end
      
      local flag = wp:GetOptions():GetFlag()
      if flag ~= nil then
         env.info("GLSCO_SCHEDULER: formation="..formation:GetName().."; wp="..num..";  flag="..flag)
         local index = self:getScheduleIndex()
         --SCHEDULER:New():Schedule(MasterObject,SchedulerFunction,SchedulerArguments,Start,Repeat,RandomizeFactor,Stop,TraceLevel,Fsm)
         local schedId = self.scheduler:Schedule(nil, GLSCO_SCHEDULER.doActionIfFlagOn, {scheduler, formation, num, stamp, flag, index}, 5, 15)
         self:addSchedule(index, schedId)
      end
	  
      local strength = wp:GetOptions():GetStrength()
      if strength ~= nil then
         env.info("GLSCO_SCHEDULER: formation="..formation:GetName().."; wp="..num..";  strength="..strength)
         local index = self:getScheduleIndex()
         local schedId = self.scheduler:Schedule(nil, GLSCO_SCHEDULER.doActionIfLosses, {scheduler, formation, num, stamp, strength, index}, 5, 15)
         self:addSchedule(index, schedId)
      end
   end

end

function GLSCO_SCHEDULER:getScheduleIndex()

   self.schedules.index = self.schedules.index + 1
   return self.schedules.index

end

function GLSCO_SCHEDULER:addSchedule(index, schedId)

   self.schedules.list[index..""] = schedId

end

function GLSCO_SCHEDULER:getSchedule(index)

   return self.schedules.list[index..""]

end

function GLSCO_SCHEDULER.doAction(scheduler, formation, num, stamp)

   env.info(string.format("GLSCO_SCHEDULER: EVENT formation=%s; num=%d stamp=%d", formation:GetName(), num, stamp))
   
   if scheduler.disabled then
      env.warning("GLSCO_SCHEDULER: schedules are disabled")
      return
   end
   
   local currentStamp = formation:GetRoute():GetTimeStamp()
   
   if currentStamp ~= stamp then
      -- If time stamps don't match, then route was overriden which makes this schedule obsolete.
      env.warning("Route must have reset, time stamps don't match.  orig="..stamp.." current="..currentStamp)
      return
   end
   
   formation:MoveToWP(num)

end

function GLSCO_SCHEDULER.doActionIfFlagOn(scheduler, formation, num, stamp, flag, index)

   --env.warning("checking flag ["..(flag or "nil").."]")
   if USERFLAG:New(flag):Get() ~= 0 then
      local schedId = scheduler:getSchedule(index)
      scheduler:removeSchedule(schedId)
      GLSCO_SCHEDULER.doAction(scheduler, formation, num, stamp)
   end

end

function GLSCO_SCHEDULER.doActionIfLosses(scheduler, formation, num, stamp, strength, index)

   local percentAlive = formation:GetPercentAlive()
   --local schedId = scheduler:getSchedule(index)
   --env.warning("checking strength ["..(strength or "nil").."] percent="..(percentAlive or "nil").." schedId="..(schedId or "nil"))
   
   if percentAlive <= strength then
      local schedId = scheduler:getSchedule(index)
      scheduler:removeSchedule(schedId)
      GLSCO_SCHEDULER.doAction(scheduler, formation, num, stamp)
   end

end

function GLSCO_SCHEDULER.getSecondsFromMissionStart()

   return timer.getAbsTime() - timer.getTime0()

end

function GLSCO_SCHEDULER:removeSchedule(schedId)

   if schedId == nil then
      env.error("GLSCO_SCHEDULER: expected schedule to remove!")
      return
   end

   self.scheduler:Remove(schedId)

end

--[[
function GLSCO_SCHEDULER:disable(formation)

   formation:GetRoute():setTimeStamp()

end
--]]

-- ========================================================================================================================
-- GLSCO_BATTLEFIELD
-- ========================================================================================================================
-- The main object used to setup blue and red forces.  Contains formations, scheduler, and 
-- unit tracker for the entire battle.
-- 
GLSCO_BATTLEFIELD = {}

function GLSCO_BATTLEFIELD:GetFormations()
   
   return self.formations
   
end

function GLSCO_BATTLEFIELD:New()

   local inst = 
   {
      active = false,
      formations = {},
      scheduler = GLSCO_SCHEDULER:New(),
      tracker = GLSCO_TRACKER:New()
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

-- Uses group naming convention to register late-activated DCS Groups defined in the miz.
-- Keyword parameter is optional and can be used to define a different prefix (default is "LSCO")
-- You can technically instantiate multiple battlefields as long as they have different prefixes.
function GLSCO_BATTLEFIELD:ScanAndRegisterFormations(keyword)
 
   keyword = keyword or GLSCO.Keyword

   local groups = GROUP:FindAllByMatching("^"..keyword.."[:!].*")

   -- Loop thru all groups and sort by formation name.
   local groupDict = {}
   for _, group in ipairs(groups) do
   
      local groupName = group:GetName()..GLSCO.Bookend
      local formationName = groupName:sub(#keyword+2, groupName:find(GLSCO.Bookend)-1)

      if groupDict[formationName] == nil then
         groupDict[formationName] = {}
      end
   
      table.insert(groupDict[formationName], group)
   
   end
   
   -- Loop thru formations and register
   for name, list in pairs(groupDict) do
   
      -- We'll assume the group with the most waypoints is to be used
      -- to define the formation's route.
      local routeGroup = self:getGroupWithLongestRoute(list)
      local points = routeGroup:GetTaskRoute()
      local radianHdg = routeGroup:GetUnit(1):GetTemplate().heading or 0
      local hdg = UTILS.ToDegree(radianHdg)
      
      local formation = GLSCO_FORMATION:New(name, hdg)
      
      -- Loop thru all groups in this formation
      for _, group in ipairs(list) do

         local isLeader = false
         if self:isLeader(group:GetName()) then
            isLeader = true
         end

         if self:isMultiUnit(group:GetName()) then
            -- These groups remain whole and are not split into individual groups.  Useful
            -- if you want a group for Combined Arms human players to slot into that 
            -- automatically follow the formation assuming human has turned on "AutoPilot"
            -- NOTE: AutoPilot only works if you slot into a non-lead unit, hence why we need
            -- the ability to leave a group whole, otherwise all units would be lead units.
            -- It's still advised that these groups have as few units as possible since the likelihood
            -- of getting stuck on terrain increases as the number of units in a group increases.
            local template = GLSCO_SPAWN:CreateSpawnTemplate(group)
            local spawn = GLSCO_SPAWN:CreateSpawn(template, group:GetName())
            local newGroup = spawn:Spawn()
            --newGroup:Activate()
            
            local combatant = GLSCO_COMBATANT:New(newGroup)
            --combatant:SetMultiUnit()
            formation:AddCombatant(combatant)
            
            if isLeader then
               combatant:SetAsLeader()
            end
         else
            -- Combatants work best if each group only has a single unit.
            -- We are going to take each unit in a group and split into their own group.
            -- Additionally, all groups spawned this way have their routes deleted.
            local disjoinGroups = GLSCO_SPAWN.DisjoinGroupAndSpawn(group)
            for _, disjoinGroup in ipairs(disjoinGroups) do
               local combatant = GLSCO_COMBATANT:New(disjoinGroup)
               formation:AddCombatant(combatant)
               
               if isLeader then
                  combatant:SetAsLeader()
                  isLeader = false -- only support one leader, so remaining will not be leaders
               end
            end
         end
      end
      formation:InitRoute(points)
      self:RegisterFormation(formation)
   end

end

function GLSCO_BATTLEFIELD:RegisterFormation(formation)

   if not formation then
      return
   end

   table.insert(self.formations, #self.formations + 1, formation)
   self.scheduler:RegisterFormation(formation)
   self.tracker:RegisterFormation(formation)

end

function GLSCO_BATTLEFIELD:Activate()

   if self.active then
      return
   end

   for i = 1, #self.formations do
      self.formations[i]:Activate()
   end
   
   self.scheduler:Start()
   self.tracker:Start(60)
   
   self.active = true

end

function GLSCO_BATTLEFIELD:StartPhase(phaseName)

   self:Activate()

   for i = 1, #self.formations do
      self.formations[i]:MoveToPhase(phaseName)
   end

end

-- Pops smoke on all units on the map.  Not intended to be used during a real mission, but
-- is available so mission maker can visualize battlefield in 3D.
function GLSCO_BATTLEFIELD:SmokeFormations()

   for i = 1, #self.formations do
      self.formations[i]:Smoke()
   end

end

-- Draws lines on the map so mission maker or GM can visualize formations routes.
function GLSCO_BATTLEFIELD:DrawFormations()

   for i = 1, #self.formations do
      self.formations[i]:Draw()
   end

end

function GLSCO_BATTLEFIELD:EraseFormations()

   for i = 1, #self.formations do
      self.formations[i]:Erase()
   end

end

function GLSCO_BATTLEFIELD:HoldFire(coalition)

   for i = 1, #self.formations do
      local formation = self.formations[i]
      if coalition == nil or (formation:GetCoalition() == coalition) then
         formation:HoldFire()
      end
   end

end

function GLSCO_BATTLEFIELD:SimulateFire(coalition)

   for i = 1, #self.formations do
      local formation = self.formations[i]
      if coalition == nil or (formation:GetCoalition() == coalition) then
         formation:SimulateFire()
      end
   end

end

function GLSCO_BATTLEFIELD:ShootToKill(coalition)

   for i = 1, #self.formations do
      local formation = self.formations[i]
      if coalition == nil or (formation:GetCoalition() == coalition) then
         formation:ShootToKill()
      end
   end

end

function GLSCO_BATTLEFIELD:HaltFormation(name)

   if not self.active then
      return
   end

   for i = 1, #self.formations do
      local formation = self.formations[i]
      if formation:GetName() == name then
         formation:Halt()
         return
      end
   end

end

function GLSCO_BATTLEFIELD:HaltAll(coalition)

   if not self.active then
      return
   end

   for i = 1, #self.formations do
      local formation = self.formations[i]
      if coalition == nil or (formation:GetCoalition() == coalition) then
         formation:Halt()
      end
   end

end

function GLSCO_BATTLEFIELD:ResumeFormation(name)

   if not self.active then
      return
   end

   for i = 1, #self.formations do
      local formation = self.formations[i]
      if formation:GetName() == name then
         formation:Resume()
         return
      end
   end

end

function GLSCO_BATTLEFIELD:ResumeAll(coalition)

   if not self.active then
      return
   end

   for i = 1, #self.formations do
      local formation = self.formations[i]
      if coalition == nil or (formation:GetCoalition() == coalition) then
         formation:Resume()
      end
   end

end

function GLSCO_BATTLEFIELD:DisableSchedules(coalition)

   self.scheduler:DisableSchedules(coalition)

end

function GLSCO_BATTLEFIELD:DestroyAll()

   for i = 1, #self.formations do
      self.formations[i]:Destroy()
   end

end

function GLSCO_BATTLEFIELD:FindFormationFromGroup(group)

   local id = group:GetTemplate().groupId

   for i = 1, #self.formations do
      local combatants = self.formations[i]:GetCombatants()
      for _, combatant in ipairs(combatants) do
         if combatant:GetID() == id then
            return self.formations[i]
         end
      end
   end
   
   return nil

end

function GLSCO_BATTLEFIELD:isMultiUnit(name)

   if #name == 0 then return false end

   return name:sub(#name, #name) == "+"

end

function GLSCO_BATTLEFIELD:isLeader(name)

   local prefix = string.lower(GLSCO.Keyword.."!")
   return string.match(string.lower(name), "^"..prefix) == prefix

end

function GLSCO_BATTLEFIELD:getGroupWithLongestRoute(groups)

   if groups == nil or #groups == 0 then
      return nil
   end

   local longestRoute = {}
   local longestGroup = groups[1]

   for index, group in ipairs(groups) do
      
      local points = group:GetTaskRoute()
      if #points > #longestRoute then
         longestRoute = points
         longestGroup = group
      end
   
   end

   return longestGroup

end

-- ========================================================================================================================
-- GLSCO_MARK_LISTENER
-- ========================================================================================================================
-- Internally used to detect mark labels (orange circles) place by humans on the F10 map.
-- 
GLSCO_MARK_LISTENER = {}

-- The source mark label must be within this many meters from a unit in a formation
GLSCO_MARK_LISTENER.MaxProximityToMarkInMeters = UTILS.NMToMeters(2)

function GLSCO_MARK_LISTENER:New(battleField, sourcePrefix, destinationPrefix)

   if battleField == nil then
      env.error("GLSCO_MARK_LISTENER: battleField is nil")
      return nil
   end
  
   local inst = 
   {
      battle = battleField,
      srcPrefix = string.lower(sourcePrefix or GLSCO.MarkSourceLabel),
      destPrefix = string.lower(destinationPrefix or GLSCO.MarkDestinationLabel),
      srcCoord = nil,
      marks = {},
      listening = false,
      handler = EVENTHANDLER:New()
   }

   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)

   return inst

end

function GLSCO_MARK_LISTENER:ListenForCommands()

   local inst = self

   if inst.listening then
      return
   end

   inst:logInfo("Listening for commands.")
   inst.handler:HandleEvent(EVENTS.MarkChange)
   inst.handler:HandleEvent(EVENTS.MarkRemoved)

   function inst.handler:OnEventMarkChange(Event)
   
      inst:logInfo("OnEventMarkChange", Event)
      inst.marks[Event.MarkID .. ""] = 
      {
         text = string.lower(Event.MarkText or ""), 
         coord = Event.MarkCoordinate
      }
      
   end
   
   function inst.handler:OnEventMarkRemoved(Event)
   
      --inst:logInfo("OnEventMarkRemoved", Event)
      inst:processMark(inst.marks[Event.MarkID .. ""])
      inst.marks[Event.MarkID .. ""] = nil
   end
   
   inst.listening = true

end

function GLSCO_MARK_LISTENER:StopListening()

   if self.listening then
      self:logInfo("Stopped listening.")
      self.handler:UnHandleEvent(EVENTS.MarkChange)
      self.handler:UnHandleEvent(EVENTS.MarkRemoved)
      self.listening = false
   end

end

function GLSCO_MARK_LISTENER:processMark(mark)

   if mark == nil or mark.text == nil or #mark.text == 0 then
      return
   end
   
   self:logInfo("Processing mark. text=["..mark.text.."]")
   
   if not self:hasPrefix(mark.text, self.destPrefix) then
      -- Not a relevant mark
      self:logInfo("Doesn't match destination prefix. text=["..mark.text.."]")
      return
   end
   
   local sourceCoord = self:findSourceCoord()
   
   if sourceCoord == nil then
      -- Source mark not found
      self:logInfo("Source mark not found.")
      return
   end
   
   local formation = self:findNearestFormationToCoord(sourceCoord)
   
   if formation == nil then
      -- No formation near coord
      self:logInfo("No formation near source coord.")
      return
   end
   
   local hdg = GLSCO_ROUTE:extractHeading(mark.text)
   local scale = GLSCO_ROUTE:extractScale(mark.text)
   local useRoads = GLSCO_ROUTE:extractRoads(mark.text, false)
   local shift = GLSCO_ROUTE:extractShift(mark.text, true)
   local deploy = GLSCO_ROUTE:extractDeployment(mark.text)
   local speed = GLSCO_ROUTE:extractSpeed(mark.text)
   local roe = GLSCO_ROUTE:extractROE(mark.text)
   local flag = GLSCO_ROUTE:extractFlag(mark.text)
   local setflag = GLSCO_ROUTE:extractFlagToSet(mark.text)
   local direct = nil
   local strength = nil
   local options = GLSCO_WP_OPTIONS:New(nil, nil, nil, useRoads, shift, deploy, speed, roe, flag, setflag, direct, strength)
   
   self:logInfo("Moving formation to custom waypoont.")
   formation:MoveToCustomWP(mark.coord, hdg, scale, options)

end

function GLSCO_MARK_LISTENER:hasPrefix(str, prefix)

   return string.match(string.lower(str), "^"..prefix) == prefix

end

function GLSCO_MARK_LISTENER:findSourceCoord()

   for _, val in pairs(self.marks) do
      if val.text == self.srcPrefix then
         return val.coord
      end
   end
   
   return nil

end

function GLSCO_MARK_LISTENER:findNearestFormationToCoord(coord)

   local group = SET_GROUP:New()
      :FilterAlive()
      :FilterCategoryGround()
      :FilterOnce()
      :FindNearestGroupFromPointVec2(POINT_VEC2:NewFromVec2(coord:GetVec2(), 0))

    if group == nil then
       self:logInfo("Nearest group is nil.")
       return nil
    end
    
    if group:GetCoordinate():Get2DDistance(coord) > GLSCO_MARK_LISTENER.MaxProximityToMarkInMeters then
       self:logInfo("Nearest group not within max proximity range.")
       return nil
    end

    return self.battle:FindFormationFromGroup(group)

end

function GLSCO_MARK_LISTENER:logInfo(msg, event)

   if event then
      env.info("GLSCO_MARK_LISTENER: "..msg.." text=["..event.MarkText.."] markid: ["..event.MarkID.."]")
   else
      env.info("GLSCO_MARK_LISTENER: "..msg)
   end
   
end

-- ========================================================================================================================
-- GLSCO_MENU
-- ========================================================================================================================
-- Creates an F10 menu item with various sub-menus to control formations on the F10 map.
-- 
GLSCO_MENU = {}

function GLSCO_MENU:New(battleField)

   local inst = 
   {
      battle = battleField
   }
   
   local mt = {}
   mt.__index = self
   setmetatable(inst, mt)
   
   return inst

end

function GLSCO_MENU:CreateMissionMenu(rootMenu, text)

   local mnuLSCO = MENU_MISSION:New(text, rootMenu)
   self:createLSCOMenu(mnuLSCO)

end

function GLSCO_MENU:createLSCOMenu(parentMenu)

   local mnuBegin = MENU_MISSION_COMMAND:New("Activate", parentMenu, function(arg) arg.battle:Activate() end, {battle = self.battle})
   self:createCoalitionMenu(parentMenu, "BLUE Coalition", coalition.side.BLUE)
   self:createCoalitionMenu(parentMenu, "RED Coalition", coalition.side.RED)
   self:createUtilMenu(parentMenu)

end

function GLSCO_MENU:createCoalitionMenu(parentMenu, text, _coalition)

   local mnuTeam = MENU_MISSION:New(text, parentMenu)
   self:createPhaseMenu(mnuTeam, _coalition)
   self:createROEMenu(mnuTeam, _coalition)
   self:createDisableMenu(mnuTeam, _coalition)
   local mnuHalt = MENU_MISSION_COMMAND:New("Halt Movement", mnuTeam, function(arg) arg.battle:HaltAll(arg.coalition) end, {battle = self.battle, coalition = _coalition})
   local mnuResume = MENU_MISSION_COMMAND:New("Resume Movement", mnuTeam, function(arg) arg.battle:ResumeAll(arg.coalition) end, {battle = self.battle, coalition = _coalition})
   
end

function GLSCO_MENU:createPhaseMenu(parentMenu, _coalition)

   local mnuPhases = MENU_MISSION:New("Start Phase", parentMenu)
   local phaseNames = self:getPhaseNames(_coalition)
   table.sort(phaseNames)
   
   local cnt = 0
   for _, name in ipairs(phaseNames) do
      cnt = cnt + 1
      
      if cnt == 10 then
         mnuPhases = MENU_MISSION:New("<MORE>", mnuPhases)
         cnt = 1
      end
      
      MENU_MISSION_COMMAND:New("\""..string.upper(name).."\"", mnuPhases, function(arg) arg.battle:StartPhase(arg.phase) end, {battle = self.battle, phase = name})
   end
end

function GLSCO_MENU:createROEMenu(parentMenu, _coalition)

   local mnuROE = MENU_MISSION:New("ROE", parentMenu)
   local mnuHold = MENU_MISSION_COMMAND:New("Hold Fire", mnuROE, function(arg) arg.battle:HoldFire(arg.coalition) end, {battle = self.battle, coalition = _coalition})
   local mnuSimulate = MENU_MISSION_COMMAND:New("Simulate Fire", mnuROE, function(arg) arg.battle:SimulateFire(arg.coalition) end, {battle = self.battle, coalition = _coalition})
   local mnuKill = MENU_MISSION_COMMAND:New("Shoot-to-Kill", mnuROE, function(arg) arg.battle:ShootToKill(arg.coalition) end, {battle = self.battle, coalition = _coalition})

end

function GLSCO_MENU:createDisableMenu(parentMenu, _coalition)

   local mnuDisable = MENU_MISSION:New("Disable Schedules", parentMenu)
   local mnuConfirm = MENU_MISSION_COMMAND:New("Are you sure?", mnuDisable, function(arg) arg.battle:DisableSchedules(arg.coalition) end, {battle = self.battle, coalition = _coalition})

end

function GLSCO_MENU:createUtilMenu(parentMenu)

   local mnuUtil = MENU_MISSION:New("DEBUG", parentMenu)
   local mnuSmoke = MENU_MISSION_COMMAND:New("Smoke Positions", mnuUtil, function(arg) arg.battle:SmokeFormations() end, {battle = self.battle})
   local mnuDraw = MENU_MISSION_COMMAND:New("Show Routes", mnuUtil, function(arg) arg.battle:DrawFormations() end, {battle = self.battle})
   local mnuErase = MENU_MISSION_COMMAND:New("Hide Routes", mnuUtil, function(arg) arg.battle:EraseFormations() end, {battle = self.battle})

end

function GLSCO_MENU:getPhaseNames(_coalition)

   local dict = {}
   local formations = self.battle:GetFormations()
   
   for _, formation in ipairs(formations) do
    
      if formation:GetCoalition() == _coalition then
      
         local dictPhases = formation:GetRoute():GetPhaseNames()
         for name, value in pairs(dictPhases) do
            dict[name] = value 
         end
      end
   end
   
   local list = {}
   for name, _ in pairs(dict) do
      table.insert(list, name)
   end

   return list

end

-- ========================================================================================================================
-- Check for ME pre-defined flags 
-- ========================================================================================================================
if GLSCO.AutoInitialize == nil then
   GLSCO.AutoInitialize = true

   local flag = USERFLAG:New("tic_init"):Get()
   env.info("Reading [tic_init] flag "..(flag or "nil"))
   if flag == 2 then
      GLSCO.AutoInitialize = false
   end
end

if GLSCO.CreateMenus == nil then
   GLSCO.CreateMenus = true
   
   local flag = USERFLAG:New("tic_menu"):Get()
   env.info("Reading [tic_menu] flag "..(flag or "nil"))
   if flag == 2 then
      GLSCO.CreateMenus = false
   end
end

if GLSCO.AutoStart == nil then
   GLSCO.AutoStart = true
   
   local flag = USERFLAG:New("tic_activate"):Get()
   env.info("Reading [tic_activate] flag "..(flag or "nil"))
   if flag == 2 then
      GLSCO.AutoStart = false
   end
end

if GLSCO.StormTrooperAI == nil then
   GLSCO.StormTrooperAI = true
   
   local flag = USERFLAG:New("tic_stormtrooper"):Get()
   env.info("Reading [tic_stormtrooper] flag "..(flag or "nil"))
   if flag == 2 then
      GLSCO.StormTrooperAI = false
   end
end

if GLSCO.DisableSchedules == nil then
   GLSCO.DisableSchedules = false
   
   local flag = USERFLAG:New("tic_disableT"):Get()
   env.info("Reading [tic_disableT] flag "..(flag or "nil"))
   if flag == 1 then
      GLSCO.DisableSchedules = true
   end
end

-- ========================================================================================================================

-- Creates a standard battlefield.
function GLSCO:Initialize()

   -- Add units to battlefield
   local battle = GLSCO_BATTLEFIELD:New()
   battle:ScanAndRegisterFormations()
   GLSCO.battle = battle
   
   -- Create menus
   if GLSCO.CreateMenus then
      local rootMenu = nil
      local menu = GLSCO_MENU:New(battle)
      menu:CreateMissionMenu(rootMenu, "Troops in Contact")
      GLSCO.menu = menu
   end
   
   if GLSCO.DisableSchedules then
      env.warning("TIC schedules have been disabled!")
      battle:DisableSchedules(coalition.side.BLUE)
	  battle:DisableSchedules(coalition.side.RED)
   end
   
   --local listener = GLSCO_MARK_LISTENER:New(battle)
   --listener:ListenForCommands()
   --GLSCO.listener = listener
   
end

if GLSCO.StormTrooperAI then
   env.info("Storm Trooper AI is enabled.")
   GLSCO.DisableCloaking = false
   GLSCO.EnableWeaponFree = false
else
   env.info("Storm Trooper AI is disabled.")
   GLSCO.DisableCloaking = true
   GLSCO.EnableWeaponFree = true
end

if GLSCO.DisableCloaking then
   env.warning("Cloaking is disabled for all TIC units!")
end

if GLSCO.EnableWeaponFree then
   env.warning("All TIC units are weapon free!")
end

if GLSCO.AutoInitialize then
   env.info("Initializing TIC...")
   GLSCO:Initialize()
else
   env.warning("TIC not configured to auto initialize!")
end

if GLSCO.AutoStart and GLSCO.battle ~= nil then
   env.info("Starting TIC...")
   GLSCO.battle:Activate()
else
   env.warning("TIC not configured to auto start!")
end

env.info("TIC Script " .. version .. " END")
