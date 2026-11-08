-- Native IMAC adapter. Only friendly sensors supply enemy air-track positions.
assert(EscalationIMAC and EscalationIMAC.newCommander,'load IMAC commander first')
do
  local API,G=EscalationIMAC,EscalationIMAC.geometry
  local TTL=30
  local function alive(object)
    return object and object:isExist() and object:getLife()>0
  end
  local function activeUnit(unit)
    -- Late-activated DCS units can exist, have life and report inAir() while
    -- still inactive. They cannot supply authority, observations or orders.
    return alive(unit) and unit:isActive()==true
  end
  local function copy(value)
    if type(value)~='table' then return value end
    local out={};for key,item in pairs(value) do out[key]=copy(item) end;return out
  end
  function API.start(config)
    if API.instance then return nil,'already started' end
    assert(type(config)=='table' and type(config.options)=='table','IMAC configuration required')
    local opt=config.options
    local cache,cursor={[1]={},[2]={}},{[1]=1,[2]=1}
    local sensors={[1]={},[2]={}}
    local priorities={[1]={},[2]={}}
    local warnings={}
    local lastThreats={}
    local commandSource={}
    local debugLast,debugBudget={},{}
    local instance
    local io={time=timer.getTime}
    function io.debug(side,group,topic,detail,screen)
      if not opt.debug or not ((side==1 and opt.red) or (side==2 and opt.blue)) then return end
      local now=timer.getTime()
      local key=side..'|'..group..'|'..topic
      local previous=debugLast[key]
      -- Periodic numeric snapshots stay in the log. Visible changes are bounded
      -- separately, so large campaigns do not flood the coalition's message area.
      if previous and now-previous.time<60 and (previous.detail==detail or topic=='active') then return end
      debugLast[key]={time=now,detail=detail}
      env.info(string.format('IMAC|DEBUG|t=%.1f|side=%d|group=%s|%s|%s',now,side,group,topic,detail))
      local budget=debugBudget[side]
      if not budget or now-budget.time>=60 then budget={time=now,count=0};debugBudget[side]=budget end
      if topic~='active' and budget.count<4 and screen~=false then
        budget.count=budget.count+1
        trigger.action.outTextForCoalition(side,
          'IMAC DEBUG ['..(side==2 and 'BLUE' or 'RED')..'] '..group..': '..topic..' - '..detail,15)
      end
    end
    local function warning(key,detail)
      if warnings[key] and timer.getTime()-warnings[key]<60 then return end
      warnings[key]=timer.getTime();env.warning('IMAC|ERROR|'..key..'|'..tostring(detail))
    end
    local function protected(key,fn,...)
      local ok,result=pcall(fn,...)
      if not ok then warning(key,result);return nil end
      return result
    end
    local awacsGroups={}
    for _,meta in ipairs(config.flights) do if meta.awacs then awacsGroups[meta.group]=true end end
    for _,sensor in ipairs(config.sensors) do
      sensors[sensor.side][#sensors[sensor.side]+1]=sensor
      if sensor.priority or awacsGroups[sensor.group] then
        priorities[sensor.side][#priorities[sensor.side]+1]=sensor
      end
    end
    function io.height(point) return land.getHeight({x=point.x,y=point.z}) end
    function io.altitude(point)
      return point.alt+(point.alt_type=='RADIO' and io.height({x=point.x,z=point.y}) or 0)
    end
    function io.sample(meta)
      return protected('sample '..meta.group,function()
        local g=Group.getByName(meta.group)
        if not g or not g:isExist() or g:getCoalition()~=meta.side then return end
        local result={fuel=1,healthy=true,ammo=false,airborne=true,player=false}
        local count=0
        for _,u in ipairs(g:getUnits()) do
          if activeUnit(u) then
            count=count+1
            result.player=result.player or (u:getPlayerName()~=nil)
            result.airborne=result.airborne and u:inAir()
            result.healthy=result.healthy and u:getLife()/math.max(1,u:getLife0())>=0.95
            result.fuel=math.min(result.fuel,u:getFuel())
            local hasAmmo=false
            for _,ammo in ipairs(u:getAmmo() or {}) do
              local desc=ammo.desc or {}
              if ammo.count>0 and (desc.missileCategory==1 or (meta.gunfighter and desc.category==0)) then hasAmmo=true end
            end
            -- The entire patrol must be combat-ready, not only the leader.
            if count==1 then result.ammo=hasAmmo else result.ammo=result.ammo and hasAmmo end
            if not result.point then
              local p,v=u:getPoint(),u:getVelocity()
              if not G.vector(p) or not G.vector(v) then return end
              result.point=G.copy(p);result.velocity=G.copy(v)
              result.speed=math.sqrt(v.x*v.x+v.z*v.z)
            end
          end
        end
        if count==0 then return end
        local state=instance and instance.states[meta.group]
        local point=state and meta.route[state.index]
        result.refuelling=point and point.name=='REFUEL'
        return result
      end)
    end
    function io.authority(side)
      commandSource[side]='none: no operating AWACS or powered command centre'
      if not ((side==1 and opt.red) or (side==2 and opt.blue)) then
        commandSource[side]='disabled in settings';return false
      end
      local granted=protected('authority '..side,function()
        for _,meta in ipairs(config.flights) do
          if meta.side==side and meta.awacs then
            local g=Group.getByName(meta.group)
            if g and g:isExist() and g:getCoalition()==side then
              for _,u in ipairs(g:getUnits()) do
                if activeUnit(u) and u:inAir() and u:getFuel()>0.05 and u:getRadar()==true then
                  commandSource[side]='AWACS '..meta.group;return true
                end
              end
            end
          end
        end
        for _,meta in ipairs(config.commandCenters) do
          if meta.side==side then
            local cc=StaticObject.getByName(meta.name)
            if alive(cc) and cc:getCoalition()==side then
              local powered=#meta.power==0
              for _,name in ipairs(meta.power) do
                local source=StaticObject.getByName(name)
                if alive(source) and source:getCoalition()==side then powered=true;break end
              end
              local query=dcsRetribution and dcsRetribution.iadsHasWorkingPower
              if query and query(meta.key)==false then powered=false end
              if powered then
                commandSource[side]='command centre '..meta.key..(#meta.power==0 and ' (standalone)' or ' (powered)')
                return true
              end
            end
          end
        end
        return false
      end)==true
      io.debug(side,'commander','authority',commandSource[side])
      return granted
    end
    local detection={Controller.Detection.VISUAL,Controller.Detection.OPTIC,
      Controller.Detection.RADAR,Controller.Detection.IRST}
    local function readSensor(sensor,side,now)
      local unit=Unit.getByName(sensor.name)
      if not activeUnit(unit) or unit:getCoalition()~=side or (sensor.air and not unit:inAir()) then return end
      local group=unit:getGroup()
      local state=group and instance.states[group:getName()]
      -- AttackGroup itself grants detection. Do not use an assigned interceptor's
      -- reports to renew the contact that its temporary attack order created.
      if state and state.order and state.order.kind=='intercept' then return end
      local controller=unit:getController() -- Air group controllers cannot report detections.
      if not controller then return end
      local entries=controller:getDetectedTargets(unpack(detection)) or {}
      local count=0
      for _,entry in pairs(entries) do
        count=count+1;if count>512 then break end
        local target=type(entry)=='table' and entry.object
        local weapon=target and target.getLauncher~=nil
        if target and target:isExist() and target:getCoalition()==3-side and
          (weapon or (target:getCategory()==Object.Category.UNIT and target:isActive()==true)) then
          local detected,visible,knownType,knownDistance,lastSeen,point,velocity=
            controller:isTargetDetected(target,unpack(detection))
          if detected==true and knownDistance==true then
            local desc=target:getDesc()
            local attributes=desc.attributes or {}
            local missile=weapon and knownType==true and desc.category==1 and
              (attributes['Cruise missiles'] or attributes['Anti-Ship missiles'] or attributes['Antiship Missiles'])
            if missile or (not weapon and
              (desc.category==Unit.Category.AIRPLANE or desc.category==Unit.Category.HELICOPTER)) then
              -- Native DCS returns four flags for a current detection. Memory
              -- time/position/velocity follow only when the contact is not visible.
              -- Read live coordinates only after positional detection and range
              -- are confirmed; a remembered or bearing-only contact cannot do this.
              if visible==true then
                point,velocity=target:getPoint(),target:getVelocity();lastSeen=now
              end
              if G.finite(lastSeen) and now-lastSeen<=TTL and lastSeen<=now+1 and
                G.vector(point) and G.vector(velocity) then
                local kind=missile and 'missile' or 'unknown'
                if not missile and knownType==true then
                  local a=attributes
                  if a.Fighters or a.Interceptors or a['Multirole fighters'] then kind='fighter'
                  elseif a.Bombers or a['Strategic bombers'] then kind='bomber'
                  elseif a.Battleplanes or a['Attack helicopters'] then kind='attack'
                  elseif a.Transports or a['Transport helicopters'] then kind='transport' end
                end
                local g=not weapon and target:getGroup()
                -- Native Weapon objects expose id_, not Unit.getID(). Use the
                -- shared native handle so separate sensors reserve one track.
                local id
                if weapon then id=target.id_ else id=target:getID() end
                if id~=nil then
                  local key=(weapon and 'weapon:' or '')..tostring(id)
                  local old=cache[side][key]
                  if (weapon or g) and (not old or lastSeen>=old.seen) then
                    cache[side][key]={key=key,groupId=g and g:getID(),point=G.copy(point),velocity=G.copy(velocity),
                      kind=kind,seen=lastSeen,visible=visible==true,weapon=weapon and target or nil}
                  end
                end
              end
            end
          end
        end
      end
    end
    function io.contacts(side)
      local now=timer.getTime()
      -- AWACS/long-range radars are sampled every cycle; local sensors rotate.
      for _,sensor in ipairs(priorities[side]) do
        protected('sensor '..sensor.name,readSensor,sensor,side,now)
      end
      local list=sensors[side]
      for _=1,math.min(64,#list) do
        local sensor=list[cursor[side]];cursor[side]=cursor[side]%#list+1
        protected('sensor '..sensor.name,readSensor,sensor,side,now)
      end
      local out={}
      for key,t in pairs(cache[side]) do
        local exists=true
        if t.weapon then
          local ok,live=pcall(function()return t.weapon:isExist()end)
          exists=ok and live
        end
        if now-t.seen>TTL or not exists then cache[side][key]=nil else out[#out+1]=t end
      end
      table.sort(out,function(a,b)return a.key<b.key end)
      return out
    end
    function io.threats(side)
      local out={}
      for _,meta in ipairs(config.threats) do
        if meta.side~=side then
          local ok,why=pcall(function()
            local known=meta.known
            if not known then
              local fog=RealisticCAS and RealisticCAS.mission and RealisticCAS.mission.fog
              local group=Group.getByName(meta.group)
              known=fog and fog.active and group and fog.service:isRevealed(group:getID(),side)==true
            end
            if not known then return end -- Gate all enemy ground life/position queries.
            if meta.transitDefense then
              local transit=ESCALATION_SAM_TRANSIT
              if not transit or transit.active[meta.group]~=true then lastThreats[meta.name]=nil;return end
            end
            local u=Unit.getByName(meta.name)
            if not activeUnit(u) or u:getCoalition()~=meta.side then lastThreats[meta.name]=nil;return end
            local query=dcsRetribution and dcsRetribution.iadsHasWorkingPower
            if query and query(meta.group)==false then lastThreats[meta.name]=nil;return end
            if meta.needsRadar then
              local radar=false
              for _,name in ipairs(meta.radars) do if activeUnit(Unit.getByName(name)) then radar=true;break end end
              if not radar then lastThreats[meta.name]=nil;return end
            end
            local p=u:getPoint()
            assert(G.vector(p),'invalid known SAM position')
            local t={name=meta.name,point=G.copy(p),radius=meta.radius,ceiling=meta.ceiling}
            lastThreats[meta.name]=t;out[#out+1]=t
          end)
          if not ok then
            warning('known SAM '..meta.name,why)
            local fallback=lastThreats[meta.name]
            if not fallback and meta.known and meta.initialPoint then
              local p=meta.initialPoint
              fallback={name=meta.name,point={x=p.x,y=0,z=p.z},radius=meta.radius}
            end
            if fallback then out[#out+1]=fallback end
          end
        end
      end
      return out
    end
    local function controllerFor(s)
      local g=Group.getByName(s.meta.group)
      local p=io.sample(s.meta)
      if not g or not p or p.player or not p.airborne then return end
      return g:getController(),p
    end
    function io.order(s,order)
      local controller,p=controllerFor(s)
      if not controller then return false,'not an airborne AI group' end
      local task
      if order.kind=='intercept' then
        if order.data.missile then
          -- Weapons have no Group or Unit target for AttackGroup/AttackUnit.
          -- Use DCS's native missile engagement filter on a temporary route.
          local function waypoint(point)
            return {x=point.x,y=point.z,alt=p.point.y,alt_type='BARO',
              type='Turning Point',action='Turning Point',speed=math.max(200,p.speed),
              ETA_locked=false,speed_locked=true,task={id='ComboTask',params={tasks={
                {id='EngageTargets',enabled=true,auto=false,number=1,params={
                  targetTypes={'Cruise missiles','Antiship Missiles'},priority=1,
                  maxDistEnabled=true,maxDist=opt.patrolLeashNm*1852}},
              }}}}
          end
          local aim=G.copy(order.data.point)
          local finish=waypoint(aim)
          finish.task.params.tasks[2]={id='Orbit',enabled=true,auto=false,number=2,params={
            pattern='Circle',point={x=aim.x,y=aim.z},altitude=p.point.y,speed=math.max(200,p.speed)}}
          task={id='Mission',params={route={points={waypoint(p.point),finish}}}}
        else task={id='AttackGroup',params={groupId=order.data.groupId,groupAttack=true}} end
      else
        local point=order.data.point
        local routePoint=s.meta.route[math.min(#s.meta.route,s.index+1)]
        task={id='Orbit',params={pattern='Circle',point={x=point.x,y=point.z},
          altitude=p.point.y,speed=math.max(p.speed,routePoint.speed)}}
      end
      controller:pushTask({id='ControlledTask',params={task=task,stopCondition={
        condition=string.format('return EscalationIMAC.shouldStop(%q,%d)',s.meta.group,order.revision)}}})
      return true
    end
    function io.recover(s,p,threats)
      local controller=controllerFor(s)
      if not controller then return false,'no AI controller' end
      local route=s.meta.route
      local home={}
      for i=math.min(#route,s.meta.recoveryIndex+1),#route do
        if route[i].name~='REFUEL' then home[#home+1]=copy(route[i]) end
      end
      if #home==0 then return false,'missing recovery waypoints' end
      local points={{x=p.point.x,y=p.point.z,alt=p.point.y,alt_type='BARO',type='Turning Point',
        action='Turning Point',speed=math.max(p.speed,home[1].speed),ETA_locked=false,speed_locked=true}}
      local previous=G.copy(p.point)
      for _,q in ipairs(home) do
        local target={x=q.x,y=io.altitude(q),z=q.y}
        if q.type=='Land' and not G.leg(target,target,io.height(target)+150,threats,2500) then
          return false,'known air defence covers the landing area'
        end
        -- Landing descent remains DCS's job. Check the approach corridor at
        -- cruise height, not at the runway's zero-MSL placeholder altitude.
        local altitude=q.type=='Land' and previous.y or math.min(previous.y,target.y)
        local path=G.detour(previous,target,altitude,threats,io.height)
        if not path then return false,'known SAM or terrain barrier' end
        for _,bend in ipairs(path) do
          points[#points+1]={x=bend.x,y=bend.z,alt=altitude,alt_type='BARO',type='Turning Point',
            action='Turning Point',speed=math.max(p.speed,q.speed),ETA_locked=false,speed_locked=true}
        end
        q.ETA_locked=false;q.speed_locked=true;points[#points+1]=q
        previous={x=target.x,y=q.type=='Land' and altitude or target.y,z=target.z}
      end
      controller:setTask({id='Mission',params={route={points=points}}})
      return true
    end
    function io.report(entry)
      env.info(string.format('IMAC|%s|t=%.1f|side=%d|group=%s|%s',
        entry.kind,entry.time,entry.side,entry.group,entry.reason))
      if opt.reports and entry.kind~='error' and entry.kind~='blocked' then
        trigger.action.outTextForCoalition(entry.side,'IMAC: '..entry.group..' — '..entry.reason,10)
      end
    end
    instance=API.newCommander(config,io)
    API.instance=instance
    function API.reached(name,index) instance:reached(name,index) end
    function API.shouldStop(name,revision) return instance:shouldStop(name,revision) end
    function API.pause(side,value) instance:pause(side,value) end
    function API.pauseFlight(name,value) instance:pauseFlight(name,value) end
    local menus={}
    local status={}
    function API.status(side) return status[side] or 'IMAC: waiting for first cycle' end
    if missionCommands then
      for number=1,2 do
        local side=number -- Lua 5.1 callbacks must retain each iteration's side.
        if (side==1 and opt.red) or (side==2 and opt.blue) then
          local root=missionCommands.addSubMenuForCoalition(side,'IMAC')
          menus[#menus+1]={side=side,path=root}
          missionCommands.addCommandForCoalition(side,'Pause / release flights for manual control',root,
            function()instance:pause(side,true)end)
          missionCommands.addCommandForCoalition(side,'Resume automatic command',root,
            function()instance:pause(side,false)end)
          missionCommands.addCommandForCoalition(side,'Commander status',root,function()
            trigger.action.outTextForCoalition(side,status[side] or 'IMAC: waiting for first cycle',15)
          end)
          local names={}
          for name,s in pairs(instance.states) do
            if s.meta.side==side and (s.meta.mode~='observe' or s.meta.returnInterceptor) then
              names[#names+1]=name
            end
          end
          table.sort(names)
          local page=missionCommands.addSubMenuForCoalition(side,'Flight control',root)
          for index,key in ipairs(names) do
            local name=key
            if index>1 and (index-1)%8==0 then
              page=missionCommands.addSubMenuForCoalition(side,'More flights',page)
            end
            local flightMenu=missionCommands.addSubMenuForCoalition(side,name,page)
            missionCommands.addCommandForCoalition(side,'Pause IMAC for this flight',flightMenu,
              function()instance:pauseFlight(name,true)end)
            missionCommands.addCommandForCoalition(side,'Resume IMAC for this flight',flightMenu,
              function()instance:pauseFlight(name,false)end)
          end
        end
      end
    end
    local function tick(_,time)
      if not instance.active then return end
      local ok,why=pcall(function()
        instance:tick()
        for side=1,2 do
          local orders,contactCount=0,0
          for _,s in pairs(instance.states) do if s.meta.side==side and s.order then orders=orders+1 end end
          for _,t in pairs(cache[side]) do if time-t.seen<=TTL then contactCount=contactCount+1 end end
          local enabled=(side==1 and opt.red) or (side==2 and opt.blue)
          local hasAuthority=io.authority(side)
          status[side]=string.format('IMAC: %s | command authority: %s | tracks: %d | temporary orders: %d | source: %s',
            not enabled and 'disabled' or instance.paused[side] and 'paused' or 'running',
            hasAuthority and 'available' or 'unavailable',contactCount,orders,commandSource[side])
          io.debug(side,'commander','authority',commandSource[side])
          io.debug(side,'commander','status',status[side],false)
        end
      end)
      if not ok then
        warning('decision cycle',why)
        instance:stop() -- Release our leases; never reset other owners' tasks.
        trigger.action.outText('IMAC stopped after an error. See dcs.log.',20)
        return
      end
      return time+opt.interval
    end
    local handler={}
    function handler:onEvent(event)
      if event and event.id==world.event.S_EVENT_MISSION_END then
        instance:stop()
        world.removeEventHandler(self)
        if missionCommands then
          for _,m in ipairs(menus) do missionCommands.removeItemForCoalition(m.side,m.path) end
        end
      end
    end
    world.addEventHandler(handler)
    timer.scheduleFunction(tick,nil,timer.getTime()+5)
    env.info('IMAC|START|flights='..#config.flights..'|sensors='..#config.sensors)
    return instance
  end
end
