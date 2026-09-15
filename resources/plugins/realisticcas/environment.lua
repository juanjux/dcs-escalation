-- Explicit, cheap environment supplied by the mission exporter/test harness.
-- DCS land.getSurfaceType is NOT a forest/city/desert classifier.
assert(RealisticCAS and RealisticCAS.Sensors,"load sensors.lua first")
do
  local S=RealisticCAS.Sensors
  local covers={desert=true,grassland=true,tundra=true,forest=true,city=true}
  function RealisticCAS.newEnvironment(config)
    local c=config or {}
    assert(covers[c.defaultCover],"default terrain cover required")
    assert(S.finite(c.startTime),"local mission start time required")
    local solarDays={}
    local function copyDay(v)
      if v.constantLight~=nil then
        assert(S.finite(v.constantLight) and v.constantLight>=0 and v.constantLight<=1,'invalid polar light')
        return {constantLight=v.constantLight}
      end
      S.lightAt(0,v.sunrise,v.sunset,c.twilight)
      return {sunrise=v.sunrise,sunset=v.sunset}
    end
    if c.solarDays then
      assert(type(c.solarDays)=='table' and #c.solarDays>0 and #c.solarDays<=4,'invalid solar calendar')
      for _,v in ipairs(c.solarDays)do solarDays[#solarDays+1]=copyDay(v)end
    else solarDays[1]=copyDay(c) end
    assert(S.finite(c.weather) and c.weather>=0 and c.weather<=1,"weather factor required")
    assert(S.finite(c.visibility) and c.visibility>=0 and c.visibility<=1000000,"visibility in metres required")
    local zones={}
    for _,z in ipairs(c.zones or {}) do
      assert(#zones<128 and S.finite(z.x) and S.finite(z.z) and S.finite(z.radius)
        and z.radius>0 and covers[z.cover],"invalid coverage zone")
      zones[#zones+1]={x=z.x,z=z.z,radius=z.radius,cover=z.cover}
    end
    local clouds
    if c.clouds then
      local v=c.clouds
      assert(S.finite(v.base) and S.finite(v.top) and v.top>v.base,"invalid cloud slab (MSL metres)")
      for _,n in ipairs({"visualTransmission","irTransmission"}) do
        assert(S.finite(v[n]) and v[n]>=0 and v[n]<=1,"cloud transmission required")
      end
      clouds={base=v.base,top=v.top,visualTransmission=v.visualTransmission,irTransmission=v.irTransmission}
    end
    local startTime,twilight=c.startTime,c.twilight
    local weather,visibility,defaultCover=c.weather,c.visibility,c.defaultCover
    local cache,queue={},{}
    local nextEviction=1
    local light,lightTime
    return function(observer,target,now)
      assert(S.vector(observer.point) and S.vector(target.point) and S.finite(now),"invalid environment query")
      local p=target.point
      -- 250m cover cells, bounded cache. First matching coverage zone wins.
      local cx,cz=math.floor(p.x/250),math.floor(p.z/250)
      local key=cx..":"..cz
      local cover=cache[key]
      if not cover then
        cover=defaultCover
        for _,z in ipairs(zones) do
          if ((cx+0.5)*250-z.x)^2+((cz+0.5)*250-z.z)^2<=z.radius^2 then cover=z.cover;break end
        end
        if #queue<4096 then queue[#queue+1]=key
        else cache[queue[nextEviction]]=nil;queue[nextEviction]=key;nextEviction=nextEviction%4096+1 end
        cache[key]=cover
      end
      local bucket=math.floor(now/30)
      if bucket~=lightTime then
        local absolute=startTime+now
        local day=solarDays[math.min(#solarDays,math.max(1,math.floor(absolute/86400)+1))]
        light=day.constantLight
        if light==nil then light=S.lightAt(absolute,day.sunrise,day.sunset,twilight)end
        lightTime=bucket
      end
      local vt,it=1,1
      if clouds and math.min(observer.point.y,p.y)<=clouds.top and
        math.max(observer.point.y,p.y)>=clouds.base then
        vt,it=clouds.visualTransmission,clouds.irTransmission
      end
      return {cover=cover,light=light,weather=weather,visibility=visibility,
        visualTransmission=vt,irTransmission=it}
    end
  end
end
