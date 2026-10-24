-- AFAC search bounds and skill tuning. Pure Lua 5.1; no DCS scans or timers.
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
  -- Approximate gameplay skill scale, not a claim about real sensor performance.
  function A.skillFactor(m) return 0.6+0.1*m.skill end
end
