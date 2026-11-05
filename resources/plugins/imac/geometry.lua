-- Horizontal geometry uses DCS Vec3 (x/z); all altitudes are MSL metres.
EscalationIMAC = EscalationIMAC or {}
do
  local G = {}
  EscalationIMAC.geometry = G
  function G.finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
  function G.vector(p) return type(p)=='table' and G.finite(p.x) and G.finite(p.y) and G.finite(p.z) end
  function G.distance(a,b) return math.sqrt((a.x-b.x)^2+(a.z-b.z)^2) end
  function G.copy(p) return {x=p.x,y=p.y,z=p.z} end
  function G.segment(a,b,p)
    local dx,dz=b.x-a.x,b.z-a.z
    local d=dx*dx+dz*dz
    local t=d>0 and math.max(0,math.min(1,((p.x-a.x)*dx+(p.z-a.z)*dz)/d)) or 0
    return G.distance(p,{x=a.x+dx*t,z=a.z+dz*t}),t
  end
  function G.closing(a,av,b,bv)
    local d=G.distance(a,b)
    if d<1 then return 0 end
    return ((b.x-a.x)*((av.x or 0)-(bv.x or 0))+
      (b.z-a.z)*((av.z or 0)-(bv.z or 0)))/d
  end
  local function low(alt,t)
    return not t.ceiling or alt<=t.point.y+t.ceiling+600
  end
  function G.leg(a,b,alt,threats,padding,escape)
    for _,t in ipairs(threats) do
      if low(alt,t) then
        local radius=t.radius+(padding or 10000)
        local d=G.segment(a,b,t.point)
        if d<radius then
          local from,to=G.distance(a,t.point),G.distance(b,t.point)
          -- Already exposed aircraft may leave a ring, but never cut across it.
          if not (escape and from<radius and to>radius and d>=from-1) then return false,t end
        end
      end
    end
    return true
  end
  function G.terrainClear(a,b,alt,height)
    for i=0,8 do
      local t=i/8
      local h=height({x=a.x+(b.x-a.x)*t,z=a.z+(b.z-a.z)*t})
      if not G.finite(h) or h+600>=alt then return false end
    end
    return true
  end
  function G.safe(a,b,alt,threats,height,padding,escape)
    return G.leg(a,b,alt,threats,padding,escape) and G.terrainClear(a,b,alt,height)
  end
  function G.escape(source,dangers,threats,height,speed,home)
    local best,bestScore
    local radius=math.max(20000,math.min(70000,speed*180))
    for i=0,23 do
      local angle=i*math.pi/12
      local p={x=source.x+math.cos(angle)*radius,y=source.y,z=source.z+math.sin(angle)*radius}
      -- Include room for a turn, rather than checking only the orbit centre.
      local padding=math.max(10000,speed*35)
      if G.safe(source,p,p.y,threats,height,padding,true) and G.leg(p,p,p.y,threats,padding+5000) then
        local score=math.huge
        for _,t in ipairs(dangers) do
          local d=G.segment(source,p,t.point)
          local from,to=G.distance(source,t.point),G.distance(p,t.point)
          if to<from+5000 or d<from-1000 then score=-math.huge;break end
          score=math.min(score,to)
        end
        if #dangers==0 then score=0 end
        if home then score=score-G.distance(p,home)*0.05 end
        if not bestScore or score>bestScore then best,bestScore=p,score end
      end
    end
    if bestScore and bestScore>-math.huge then return best end
  end
  function G.detour(a,b,alt,threats,height)
    if G.safe(a,b,alt,threats,height,10000,true) then return {} end
    local best,bestDistance
    -- Bounded single-bend recovery search. No unsafe direct-route fallback.
    for _,t in ipairs(threats) do
      if low(alt,t) and G.segment(a,b,t.point)<t.radius+15000 then
        local radius=(t.radius+17000)/math.cos(math.pi/12)
        for i=0,11 do
          local angle=i*math.pi/6
          local p={x=t.point.x+math.cos(angle)*radius,y=alt,z=t.point.z+math.sin(angle)*radius}
          local d=G.distance(a,p)+G.distance(p,b)
          if (not bestDistance or d<bestDistance) and
            G.safe(a,p,alt,threats,height,10000,true) and G.safe(p,b,alt,threats,height,10000) then
            best,bestDistance=p,d
          end
        end
      end
    end
    if best then return {best} end
  end
end
