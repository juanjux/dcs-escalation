-- Pure Lua 5.1 perception approximation. Metres, seconds, radians; no DCS calls.
-- Values below are gameplay starting points, NOT real-world sensor specifications.
assert(RealisticCAS, "load core.lua first")
do
  local M = {}
  RealisticCAS.Sensors = M
  local rad, sqrt, abs = math.rad, math.sqrt, math.abs
  local terrain = {desert=1, grassland=0.8, tundra=0.65, forest=0.35, city=0.25}
  local radarRoles = {CAS=true, BAI=true, ["Armed Recon"]=true}
  local integral = {
    ["MQ-9"]={ir=true, eo=true, rbm=true},
    ["OH58D"]={ir=true, eo=true},
    ["Su-25T"]={eo=true},
    ["Ka-50"]={eo=true}, ["Ka-50_3"]={eo=true},
    ["FA-18C_hornet"]={rbm=true, gmti=true},
    ["F-15ESE"]={rbm=true, gmti=true},
    ["M-1 Abrams"]={ir=true},
  }
  local function finite(n)
    return type(n)=="number" and n==n and n~=math.huge and n~=-math.huge
  end
  local function bounded(n,lo,hi) return finite(n) and n>=lo and n<=hi end
  local function vec(p) return type(p)=="table" and finite(p.x) and finite(p.y) and finite(p.z) end
  M.finite, M.vector = finite, vec

  function M.profile(typeName, category, equipment)
    assert(category=="air" or category=="ground", "unsupported observer category")
    local e = equipment or {}
    local c = integral[typeName] or {}
    local air = category=="air"
    local function capability(key)
      if e[key]~=nil then assert(type(e[key])=="boolean", "capability must be boolean");return e[key] end
      return c[key]==true
    end
    local p = {category=category, visualRange=air and 9260 or 3000,
      visualMaxAGL=air and 3500 or 100, opticalMaxAGL=air and 6500 or 100,
      irRange=capability("ir") and (air and 12000 or 4500) or 0,
      eoRange=capability("eo") and (air and 12000 or 4000) or 0,
      rbmRange=air and capability("rbm") and 12000 or 0,
      gmtiRange=air and capability("gmti") and 24000 or 0,
      visualHalfAngle=air and rad(120) or math.pi,
      radarHalfAngle=rad(60), radarMaxDepression=rad(80),
      minimumMovingSpeed=2, minimumRadialSpeed=1}
    -- A mounted targeting pod is explicit mission metadata. Native getSensors
    -- omitted it on tested Hornets/A-10s; IRST is not an air-to-ground pod.
    if e.targetingPod==true then p.irRange=air and 12000 or p.irRange;p.eoRange=air and 12000 or p.eoRange end
    return p
  end

  function M.maxRange(p)
    return math.max(p.visualRange, p.irRange, p.eoRange, p.rbmRange, p.gmtiRange)
  end

  -- Environment comes from the mission adapter/exporter. Unknown values never
  -- silently mean sunny desert; return an explicit failure for missing inputs.
  function M.assess(o, t, e, p)
    if not o or not t or o.side==t.side or (o.side~=1 and o.side~=2) or
      (t.side~=1 and t.side~=2) then return nil,"coalition" end
    if not vec(o.point) or not vec(t.point) or not bounded(o.agl,0,100000) then return nil,"geometry" end
    if not e or not terrain[e.cover] or not bounded(e.light,0,1) or
      not bounded(e.weather,0,1) or not bounded(e.visibility,0,1000000) or
      not bounded(e.visualTransmission,0,1) or not bounded(e.irTransmission,0,1) then
      return nil,"environment"
    end
    local dx,dy,dz=t.point.x-o.point.x,t.point.y-o.point.y,t.point.z-o.point.z
    local distance=sqrt(dx*dx+dy*dy+dz*dz)
    if distance>M.maxRange(p) then return nil,"range" end
    if not vec(o.forward) then return nil,"orientation" end
    local length=sqrt(o.forward.x^2+o.forward.z^2)
    if length<0.001 then return nil,"orientation" end
    local along=(dx*o.forward.x+dz*o.forward.z)/length
    local across=(-dx*o.forward.z+dz*o.forward.x)/length
    local azimuth=abs(math.atan2(across,along))
    local cover=terrain[e.cover]
    local weather=0.2+0.8*e.weather
    local light=0.04+0.96*e.light
    local mode,reach
    local function choose(name,r)
      if r>0 and distance<=r and (not reach or r>reach) then mode,reach=name,r end
    end
    if azimuth<=p.visualHalfAngle then
      if o.agl<=p.visualMaxAGL then
        choose("visual", math.min(p.visualRange*cover*weather*light,e.visibility)*e.visualTransmission)
      end
      if o.agl<=p.opticalMaxAGL then
        choose("eo", math.min(p.eoRange*cover*weather*light,e.visibility)*e.visualTransmission)
        -- No universal cloud veto for IR: an independent configurable attenuation.
        choose("ir", math.min(p.irRange*(0.35+0.65*cover)*sqrt(weather),
          e.visibility*1.5)*e.irTransmission)
      end
    end
    -- This is an approximate forward/downward search cone, not actual pod/radar
    -- pointing. GMTI requires target ground motion AND a radial component.
    local depression=math.atan2(-dy,sqrt(dx*dx+dz*dz))
    if p.category=="air" and radarRoles[o.role] and o.radarOn==true and
      azimuth<=p.radarHalfAngle and depression>=0 and depression<=p.radarMaxDepression then
      local attenuation=(0.4+0.6*cover)*(0.7+0.3*e.weather)
      choose("rbm",p.rbmRange*attenuation)
      if vec(t.velocity) then
        local speed=sqrt(t.velocity.x^2+t.velocity.z^2)
        local radial=distance>0 and abs((dx*t.velocity.x+dz*t.velocity.z)/distance) or 0
        if speed>=p.minimumMovingSpeed and radial>=p.minimumRadialSpeed then
          choose("gmti",p.gmtiRange*attenuation)
        end
      end
    end
    if not mode then return nil,"sensor envelope" end
    -- LOS deliberately lives outside this pure model and is checked only AFTER
    -- these cheap filters, once for the winning candidate channel.
    return {mode=mode,distance=distance,range=reach}
  end

  -- Cheap daily illumination from exported sunrise/sunset (seconds of local day).
  -- The exporter must supply correct theatre/date values; no invented timezone.
  function M.lightAt(seconds, sunrise, sunset, twilight)
    assert(finite(seconds) and bounded(sunrise,0,86400) and bounded(sunset,0,86400)
      and sunrise~=sunset, "invalid solar schedule")
    twilight=twilight or 1800
    assert(bounded(twilight,1,7200),"invalid twilight")
    local sinceRise=(seconds-sunrise)%86400
    local dayLength=(sunrise==0 and sunset==86400) and 86400 or (sunset-sunrise)%86400
    if sinceRise<=dayLength then return 1 end
    -- Circular distances also cover dawn before midnight and sunset after it.
    local beforeRise=(sunrise-seconds)%86400
    local afterSet=(seconds-sunset)%86400
    return math.max(0,1-math.min(beforeRise,afterSet)/twilight)
  end
end
