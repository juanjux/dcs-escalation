-- Only native-probe-validated batteries are registered by the mission generator.
local config=ESCALATION_SAM_TRANSIT_CONFIG or {}
local api={active={},groups={}}
ESCALATION_SAM_TRANSIT=api
local byUnit={}
local function log(r,text)env.info('SAM_TRANSIT_DEFENSE|'..r.meta.name..'|'..text)end
local function copy(t)
  if type(t)~='table'then return t end
  local out={};for k,v in pairs(t)do out[k]=copy(v)end;return out
end
local function live(u)return u and u:isExist()and u:getLife()>0 end
local function group(r)return Group.getByName(r.meta.name)end
local function members(r)local g=group(r);return g and g:getUnits()or{}end
local function controller(r)local g=group(r);return g and g:getController()end
local function options(r,alarm,roe)
  local c=controller(r)
  if c then c:setOption(0,roe);c:setOption(9,alarm)end
end
local function halt(r,value)
  local c=controller(r)
  if c then c:setCommand({id='StopRoute',params={value=value}})end
end
local function phase(r,value,now)
  r.phase=value;r.phaseAt=now
  api.active[r.meta.name]=value=='DEFENDING'
  log(r,value)
end
function api.reached(name,index)
  local r=api.groups[name]
  if not r or r.disabled then return end
  if type(index)~='number'or index<1 or index>#r.meta.route then return end
  r.next=math.max(r.next,index+1)
end
local function resume(r,now)
  local g=group(r)
  local leader=g and g:getUnit(1)
  if not live(leader)then phase(r,'DESTROYED',now);r.disabled=true;return end
  local remaining={}
  for i=r.next,#r.meta.route do remaining[#remaining+1]=copy(r.meta.route[i])end
  if #remaining>0 then
    local p=leader:getPoint()
    local first=copy(remaining[1])
    first.x=p.x;first.y=p.z;first.alt=p.y
    first.ETA=0;first.ETA_locked=false
    first.task={id='ComboTask',params={tasks={}}}
    table.insert(remaining,1,first)
    controller(r):setTask({id='Mission',params={route={points=remaining}}})
  end
  -- GREEN suppresses native sensor contacts. AUTO keeps detection while HOLD
  -- prevents firing until this controller validates and deploys against a threat.
  options(r,0,4);halt(r,false)
  phase(r,r.next>#r.meta.route and 'ARRIVED'or 'MARCH',now)
  -- Native packing/reloading can take many minutes. Never reset tasks on a timer.
end
local function manual(r)
  for _,u in ipairs(members(r))do
    if live(u)then
      local ok,name=pcall(function()return u:getPlayerName()end)
      if ok and name and name~=''then return true end
    end
  end
  return false
end
local function defend(r,now)
  if r.disabled then return end
  if manual(r)then r.disabled=true;api.active[r.meta.name]=true;log(r,'MANUAL_CONTROL');return end
  r.lastActivity=now
  r.initialized=true
  if r.phase=='DEFENDING'then return end
  halt(r,true);options(r,2,0);phase(r,'DEFENDING',now)
end
local function detectedAirThreat(r)
  local c=controller(r)
  local g=group(r)
  local leader=g and g:getUnit(1)
  if not c or not live(leader)then return false end
  local p=leader:getPoint()
  local side=leader:getCoalition()
  local enemy=side==1 and 2 or(side==2 and 1 or nil)
  if not enemy then return false end
  -- Only this group's native sensor contacts, never coalition/world enumeration.
  for _,entry in ipairs(c:getDetectedTargets()or{})do
    local u=entry.object
    if u and u:isExist()and Object.getCategory(u)==Object.Category.UNIT and live(u)
      and u:getCoalition()==enemy and c:isTargetDetected(u)then
      local desc=u:getDesc()
      if desc.category==Unit.Category.AIRPLANE or desc.category==Unit.Category.HELICOPTER then
        local q=u:getPoint()
        -- Native positions are MSL: use relative height, including elevated sites.
        local height=math.abs(q.y-p.y)
        local distance2=(p.x-q.x)^2+(p.z-q.z)^2+height*height
        local minimum=r.meta.minRange or 0
        if distance2<=r.meta.range*r.meta.range and distance2>=minimum*minimum
          and(not r.meta.ceiling or height<=r.meta.ceiling)then return true end
      end
    end
  end
  return false
end
local function tickGroup(r,now)
  if r.disabled then return end
  local living=false
  for _,u in ipairs(members(r))do if live(u)then living=true;break end end
  if not living then phase(r,'DESTROYED',now);r.disabled=true;return end
  if manual(r)then r.disabled=true;api.active[r.meta.name]=true;log(r,'MANUAL_CONTROL');return end
  if not r.initialized and r.phase=='MARCH'then
    r.initialized=true;resume(r,now)
  end
  if (r.phase=='MARCH'or r.phase=='PACKING')and detectedAirThreat(r)then defend(r,now)end
  if r.phase=='DEFENDING'then
    if detectedAirThreat(r)then r.lastActivity=now end
    if now-r.lastActivity>=90 and now-r.phaseAt>=60 then
      options(r,1,4);phase(r,'PACKING',now)
    end
  elseif r.phase=='PACKING'and now-r.phaseAt>=120 then resume(r,now)end
end
for _,meta in ipairs(config)do
  local r={meta=meta,next=2,phase='MARCH',phaseAt=0,lastActivity=0}
  api.groups[meta.name]=r;api.active[meta.name]=false
  for _,name in ipairs(meta.units)do byUnit[name]=r end
end
world.addEventHandler({onEvent=function(self,e)
  local now=timer.getTime()
  if e.id==world.event.S_EVENT_HIT and e.target then
    local r=byUnit[e.target:getName()]
    if r then
      local ok,err=pcall(defend,r,now)
      if not ok then log(r,'ERROR|'..tostring(err));r.failed=true end
    end
  elseif (e.id==world.event.S_EVENT_SHOT or(world.event.S_EVENT_SHOOTING_START and e.id==world.event.S_EVENT_SHOOTING_START))and e.initiator then
    local r=byUnit[e.initiator:getName()]
    if r and not r.disabled then r.lastActivity=now end
  end
end})
local function tick(_,now)
  for _,r in pairs(api.groups)do
    local ok,err=pcall(function()
      if r.failed then error('Previous defense command failed')end
      tickGroup(r,now)
    end)
    if not ok then
      log(r,'ERROR|'..tostring(err));r.disabled=true;api.active[r.meta.name]=false
      pcall(function()options(r,1,4);halt(r,false)end)
    end
  end
  return now+5
end
timer.scheduleFunction(tick,nil,timer.getTime()+5)


