-- Bounded AFAC threat geometry. Inputs contain coalition-known positions only.
assert(RealisticCAS and RealisticCAS.AFACSearch, 'load afac-search.lua first')

do
  local A={};RealisticCAS.AFACSafety=A
  local function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.z-b.z)^2) end
  A.distance=distance
  local function segmentDistance(a,b,p)
    local dx,dz=b.x-a.x,b.z-a.z
    local length=dx*dx+dz*dz
    local t=length>0 and math.max(0,math.min(1,((p.x-a.x)*dx+(p.z-a.z)*dz)/length)) or 0
    return distance({x=a.x+t*dx,z=a.z+t*dz},p)
  end
  local function below(alt,t) return not t.ceiling or alt<=t.point.y+t.ceiling+300 end
  function A.clear(p,threats,padding)
    for _,t in ipairs(threats) do
      if below(p.y,t) and distance(p,t.point)<=t.radius+(padding or 1000) then return false,t end
    end
    return true
  end
  function A.leg(a,b,alt,threats,escape)
    for _,t in ipairs(threats) do
      if below(alt,t) then
        local radius=t.radius+1000
        local closest=segmentDistance(a,b,t.point)
        if closest<=radius then
          local start=distance(a,t.point)
          -- Discovery inside a ring permits an outward escape, never a closer pass.
          if not (escape and start<=radius and distance(b,t.point)>radius and closest>=start-1) then
            return false
          end
        end
      end
    end
    return true
  end
  function A.orbit(p,alt,zone,threats,radius)
    local inner={radius=zone.radius-radius,points=zone.points}
    return inner.radius>0 and RealisticCAS.AFACSearch.inside(p,inner) and
      A.clear({x=p.x,y=alt,z=p.z},threats,1000+radius)
  end
  function A.plan(input)
    local source,zone,threats=input.source,input.zone,input.threats
    local nominal=input.altitude
    local center={x=(input.points[1].x+input.points[2].x)/2,
      z=(input.points[1].z+input.points[2].z)/2}
    local footprint=input.footprint
    local needed,unknown=nominal,false
    local hazardous=false
    for _,t in ipairs(threats) do
      local closest=math.min(segmentDistance(input.points[1],input.points[2],t.point),
        segmentDistance(source,input.points[1],t.point))
      if below(nominal,t) and closest<=t.radius+1000+footprint then
        hazardous=true
        if t.ceiling then needed=math.max(needed,t.point.y+t.ceiling+500) else unknown=true end
      end
    end
    if not hazardous then return {mode='original'} end
    local altitude=math.min(nominal,input.maxAltitude)
    if not unknown and needed<=input.maxAltitude then altitude=needed end
    if altitude>input.maxAltitude then return {mode='abort',reason='cloud or aircraft altitude limit'} end
    local hold=input.holdPoint or {x=source.x,z=source.z}
    local candidates={center,input.points[1],input.points[2],hold}
    -- A fixed grid is predictable and bounded, including elongated frontline zones.
    for _,anchor in ipairs({input.points[1],center,input.points[2]}) do
      for i=0,7 do
        local angle=i*math.pi/4
        local radius=math.max(0,zone.radius-footprint-100)
        candidates[#candidates+1]={x=anchor.x+math.cos(angle)*radius,z=anchor.z+math.sin(angle)*radius}
      end
    end
    -- Sample standoff positions around the nearest few rings, not just the zone edge.
    for index=1,math.min(4,#threats) do
      local t=threats[index]
      for i=0,7 do
        local angle=i*math.pi/4
        local radius=t.radius+1000+footprint+150
        candidates[#candidates+1]={x=t.point.x+math.cos(angle)*radius,
          z=t.point.z+math.sin(angle)*radius}
      end
    end
    local best,cost
    local function terrainSafe(a,b)
      local minimum=math.min(source.y,altitude)
      for i=0,4 do
        local t=i/4
        local p={x=a.x+(b.x-a.x)*t,z=a.z+(b.z-a.z)*t}
        if input.height(p)+input.clearance>minimum then return false end
      end
      return true
    end
    local function orbitTerrainSafe(p)
      local minimum=math.min(source.y,altitude)
      for i=0,7 do
        local angle=i*math.pi/4
        local q={x=p.x+math.cos(angle)*footprint,z=p.z+math.sin(angle)*footprint}
        if input.height(q)+input.clearance>minimum then return false end
      end
      return true
    end
    for _,p in ipairs(candidates) do
      if A.orbit(p,math.min(source.y,altitude),zone,threats,footprint) and
        input.height(p)+input.clearance<=altitude and orbitTerrainSafe(p) then
        local path
        local flightAlt=math.min(source.y,altitude)
        if A.leg(source,p,flightAlt,threats,true) then path={p}
        else
          -- One intermediate corner can route around a circle; complex blocked
          -- corridors fail closed rather than claiming a globally optimal path.
          for _,corner in ipairs(candidates) do
            if RealisticCAS.AFACSearch.inside(corner,zone) and
              A.leg(source,corner,flightAlt,threats,true) and A.leg(corner,p,flightAlt,threats,false) then
              if not path or distance(source,corner)+distance(corner,p)<distance(source,path[1])+distance(path[1],p) then
                path={corner,p}
              end
            end
          end
        end
        if path then
          local valid,last,total=true,source,0
          for _,waypoint in ipairs(path) do
            if not terrainSafe(last,waypoint) then valid=false;break end
            total=total+distance(last,waypoint);last=waypoint
          end
          local score=distance(p,center)*2+total
          if valid and (not cost or score<cost) then
            best,cost={mode='avoid',point=p,altitude=altitude,path=path},score
          end
        end
      end
    end
    if best then return best end
    if input.approach and altitude>source.y+100 and
      A.clear({x=hold.x,y=source.y,z=hold.z},threats,1000+footprint) and
      A.leg(source,hold,source.y,threats,true) and terrainSafe(source,hold) and orbitTerrainSafe(hold) then
      return {mode='avoid',point=hold,altitude=altitude,path={hold},approach=true}
    end
    return {mode='abort',reason='no safe orbit and approach inside assigned zone'}
  end
end
