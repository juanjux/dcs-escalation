-- AFAC search bounds, skill tuning and first-lap progress. Pure Lua 5.1.
assert(RealisticCAS, 'load core.lua first')
do
  local A={}
  RealisticCAS.AFACSearch=A
  local function finite(n)
    return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge
  end
  function A.validate(m)
    assert(type(m)=='table' and type(m.groupName)=='string' and m.groupName~='', 'AFAC group required')
    assert(finite(m.skill) and m.skill>=0 and m.skill<=4 and m.skill==math.floor(m.skill), 'invalid AFAC skill')
    assert(finite(m.stationSeconds) and m.stationSeconds>=60 and m.stationSeconds<=14400, 'invalid AFAC station time')
    local z=m.zone
    assert(type(z)=='table' and finite(z.radius) and z.radius>0 and z.radius<=100000, 'invalid AFAC zone')
    assert(type(z.points)=='table' and (#z.points==1 or #z.points==2), 'AFAC zone requires one or two points')
    for _,p in ipairs(z.points) do assert(type(p)=='table' and finite(p.x) and finite(p.z), 'invalid AFAC zone point') end
  end
  function A.inside(p,z)
    if type(p)~='table' or not finite(p.x) or not finite(p.z) then return false end
    local a,b=z.points[1],z.points[2] or z.points[1]
    local dx,dz=b.x-a.x,b.z-a.z
    local length=dx*dx+dz*dz
    local t=length>0 and math.max(0,math.min(1,((p.x-a.x)*dx+(p.z-a.z)*dz)/length)) or 0
    return (p.x-a.x-t*dx)^2+(p.z-a.z-t*dz)^2<=z.radius*z.radius
  end
  function A.active(m,p,now,start,fuel)
    return finite(start) and now>=start and now-start<m.stationSeconds
      and finite(fuel) and fuel>=0.2 and A.inside(p,m.zone)
  end
  local laps={}
  local function lap(group)
    if not laps[group] then laps[group]={} end
    return laps[group]
  end
  function A.lapComplete(group)
    return laps[group] and laps[group].complete==true
  end
  function A.resetLap(group)
    if not A.lapComplete(group) then laps[group]=nil end
  end
  function A.patrolWaypoint(group,index,count)
    local r=lap(group)
    if r.complete then return end
    if index==1 and r.nextWaypoint==count+1 then
      r.complete=true
    elseif index==1 or index==r.nextWaypoint then
      r.nextWaypoint=index+1
    end
  end
  function A.racetrackProgress(group,p,points)
    local a,b=points[1],points[2]
    local dx,dz=b.x-a.x,b.z-a.z
    local length=dx*dx+dz*dz
    if length<1 then return end
    local along=((p.x-a.x)*dx+(p.z-a.z)*dz)/length
    -- DCS turns before the end of a leg. Use gates across the track so the
    -- aircraft need not pass directly through its navigation waypoints.
    local endpoint=along<=0.2 and 1 or along>=0.8 and 2
    if not endpoint then return end
    local r=lap(group)
    if not r.firstEndpoint then r.firstEndpoint=endpoint
    elseif endpoint~=r.firstEndpoint then r.oppositeEndpoint=true
    elseif r.oppositeEndpoint then r.complete=true end
  end
  function A.circleProgress(group,p,center)
    local dx,dz=p.x-center.x,p.z-center.z
    if dx*dx+dz*dz<1 then return end
    local r=lap(group)
    local angle=math.atan2(dz,dx)
    local turn=2*math.pi
    if r.angle then
      local delta=(angle-r.angle+math.pi)%turn-math.pi
      r.sweep=(r.sweep or 0)+delta
      if math.abs(r.sweep)>=turn then r.complete=true end
    end
    r.angle=angle
  end
  -- Approximate gameplay skill scale, not a claim about real sensor performance.
  function A.skillFactor(m) return 0.6+0.1*m.skill end
end
