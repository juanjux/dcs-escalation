-- Test setup only: find ground rays before spawning three stationary units.
-- Production sensor heights/ranges/LOS are unchanged.
do
  local cfg=RCAS_GROUND_TEST
  local search=cfg.search
  local cursor=1
  local function log(kind,message)
    env.info('RCAS_SITE_TEST|'..kind..'|t='..timer.getTime()..'|'..message)
  end
  local function surfacePoint(p,height)
    local surface=land.getSurfaceType({x=p.x,y=p.z})
    if surface==2 or surface==3 then return nil end -- shallow/deep water
    return {x=p.x,y=land.getHeight({x=p.x,y=p.z})+height,z=p.z}
  end
  local function spawn(template,p,country)
    template.x,template.y=p.x,p.z
    template.lateActivation=false
    local u=template.units[1]
    u.x,u.y=p.x,p.z
    local wp=template.route.points[1]
    wp.x,wp.y=p.x,p.z
    assert(coalition.addGroup(country,Group.Category.GROUND,template),'group spawn failed: '..template.name)
  end
  local function attempt()
    for _=1,8 do
      local c=search.candidates[cursor]
      if not c then
        log('INCONCLUSIVE','search exhausted; no engine-valid placement, no sensor verdict')
        trigger.action.outText('RCAS GROUND FIN: busqueda sin emplazamiento. Guarda dcs.log.',600)
        return false
      end
      cursor=cursor+1
      -- Half a metre below production rays for a conservative placement margin.
      local a=surfacePoint(c.observer,1.5)
      local b=surfacePoint(c.near,0.5)
      local d=surfacePoint(c.city,0.5)
      local nearLOS=a and b and land.isVisible(a,b)==true
      local cityLOS=a and d and land.isVisible(a,d)==true
      log('CANDIDATE',tostring(cursor-1)..'|nearLOS='..tostring(nearLOS)..'|cityLOS='..tostring(cityLOS))
      if nearLOS and cityLOS then
        log('SELECT',string.format('candidate=%d|observer=%.2f,%.2f|near=%.2f,%.2f|city=%.2f,%.2f',
          cursor-1,a.x,a.z,b.x,b.z,d.x,d.z))
        spawn(search.templates.observer,c.observer,80)
        spawn(search.templates.near,c.near,81)
        spawn(search.templates.city,c.city,81)
        -- Allow initial waypoint options to run before visibility ownership.
        timer.scheduleFunction(function()
          local ok,err=pcall(RCAS_RUN_GROUND_TEST)
          if not ok then
            log('ERROR',tostring(err))
            trigger.action.outText('RCAS GROUND FIN: error de arranque. Guarda dcs.log.',600)
          end
        end,nil,timer.getTime()+3)
        return false
      end
    end
    trigger.action.outText('RCAS: buscando emplazamiento despejado ('..(cursor-1)..' candidatos). Solo log.',2,true)
    return true
  end
  timer.scheduleFunction(function(_,now)
    local ok,more=pcall(attempt)
    if not ok then
      log('ERROR',tostring(more))
      trigger.action.outText('RCAS GROUND FIN: error de seleccion. Guarda dcs.log.',600)
      return nil
    end
    if more then return now+1 end
  end,nil,timer.getTime()+1)
end
