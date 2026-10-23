-- Coalition-known threat sampling and temporary native AFAC navigation tasks.
assert(RealisticCAS and RealisticCAS.AFACSafety, 'load afac-safety.lua first')

do
  local A,S=RealisticCAS.AFACSafety,RealisticCAS.Sensors
  function RealisticCAS.newAFACNavigation(fog,c)
    local threats,groups,order,byUnit={},{},{},{}
    local definitions=c.airDefenseThreats or {}
    assert(#definitions<=10000, 'too many AFAC threat definitions')
    for _,t in ipairs(definitions) do
      assert(type(t.name)=='string' and type(t.groupName)=='string' and
        (t.coalition==1 or t.coalition==2) and S.finite(t.radius) and t.radius>0,
        'invalid AFAC threat metadata')
      assert(t.ceiling==nil or (S.finite(t.ceiling) and t.ceiling>0), 'invalid threat ceiling')
      local r={meta=t}
      if t.known and t.initialPoint then
        assert(S.finite(t.initialPoint.x) and S.finite(t.initialPoint.z), 'invalid known threat point')
        -- Static sites are already coalition knowledge. Until sampled, deny
        -- overflight at every altitude rather than inventing their terrain height.
        r.sample={name=t.name,typeName=t.typeName,point={x=t.initialPoint.x,y=0,z=t.initialPoint.z},
          radius=t.radius,side=t.coalition}
      end
      threats[#threats+1]=r
      byUnit[t.name]=r
    end
    for _,o in ipairs(c.observers) do
      if o.afac then
        local m=o.afac
        assert(type(m.navigation)=='table', 'AFAC native navigation metadata required')
        local n=m.navigation
        assert(S.finite(n.speed) and n.speed>0 and S.finite(n.altitude) and
          (n.altType=='BARO' or n.altType=='RADIO') and #n.points==2 and
          S.finite(n.exitWaypoint) and n.exitWaypoint>=3 and n.exitWaypoint==math.floor(n.exitWaypoint), 'invalid AFAC native route')
        for _,p in ipairs(n.points)do assert(S.finite(p.x) and S.finite(p.z), 'invalid AFAC patrol point')end
        local r=groups[m.groupName]
        if not r then
          r={meta=m,side=o.coalition,names={},revision=0}
          groups[m.groupName]=r;order[#order+1]=m.groupName
        end
        r.names[#r.names+1]=o.name
      end
    end
    RealisticCAS.afacNavigation=RealisticCAS.afacNavigation or {}
    RealisticCAS.afacAbort=RealisticCAS.afacAbort or {}
    RealisticCAS.afacReturn=RealisticCAS.afacReturn or {}
    local api={active=true}
    local nextTick,cursor,groupCursor=0,1,1
    local function live(name)
      local u=Unit.getByName(name)
      if u and u:isExist() and u:getLife()>0 then return u end
    end
    local function known(r)
      if r.meta.known then return true end
      local g=Group.getByName(r.meta.groupName)
      return g and fog.service:isRevealed(g:getID(),3-r.meta.coalition)==true
    end
    local function sample()
      local used,visited=0,{}
      local function read(r)
        visited[r]=true;used=used+1
        r.sample=nil
        -- This gate precedes every native enemy position/life getter.
        local shared=known(r)==true
        r.seenKnowledge=shared
        if shared then
          local u=live(r.meta.name)
          local g=u and u:getGroup()
          if g and g:getName()==r.meta.groupName and u:getTypeName()==r.meta.typeName and u:getCoalition()==r.meta.coalition then
            local p=u:getPoint()
            if S.vector(p) then
              r.sample={name=r.meta.name,typeName=r.meta.typeName,point={x=p.x,y=p.y,z=p.z},
                radius=r.meta.radius,ceiling=r.meta.ceiling,side=r.meta.coalition}
            end
          end
        end
      end
      -- Newly shared contacts take priority over periodic static-site refreshes.
      for _,r in ipairs(threats)do
        if used>=64 then break end
        if not r.sample and not r.seenKnowledge and known(r) then read(r) end
      end
      for _=1,#threats do
        if used>=64 then break end
        local r=threats[cursor];cursor=cursor%#threats+1
        if not visited[r] then read(r) end
      end
    end
    local function relevant(side,source,m)
      local out={}
      local a=m.zone.points[1]
      local reach=m.zone.radius+A.distance(source,a)
      if m.zone.points[2] then reach=reach+A.distance(a,m.zone.points[2]) end
      for _,r in ipairs(threats) do
        local t=r.sample
        if t and t.side~=side and known(r) and A.distance(t.point,a)<=reach+t.radius+10000 then
          out[#out+1]=t
          if #out>64 then return nil end -- Never silently drop a threatening ring.
        end
      end
      table.sort(out,function(a,b)return A.distance(a.point,source)-a.radius<A.distance(b.point,source)-b.radius end)
      return out
    end
    local function notice(name,r,text)
      if r.lastNotice==text then return end
      r.lastNotice=text
      trigger.action.outTextForCoalition(r.side,'JTAC '..name..' '..text,c.afacMarking.messageSeconds)
      env.info('REALISTIC_CAS_AFAC_NAV|'..name..'|'..text)
    end
    local function release(name,r,controller)
      local state=RealisticCAS.afacNavigation[name]
      if state then state.active=false end
      if r.applied and state and not state.finished and controller then
        local ok=pcall(function()controller:popTask()end)
        if not ok then return false end
      end
      r.applied=false;return true
    end
    local function depart(name,r,controller,reason,aborted)
      if aborted then RealisticCAS.afacAbort[name]=true end
      RealisticCAS.afacReturn[name]=reason
      if not release(name,r,controller) then return false end
      if not r.returning then
        -- The exit skips racetrack-end tasks, including this campaign option.
        if r.meta.navigation.restoreUnlimitedFuel then
          controller:setCommand({id='SetUnlimitedFuel',params={value=true}})
        end
        controller:setCommand({id='SwitchWaypoint',params={fromWaypointIndex=1,
          goToWaypointIndex=r.meta.navigation.exitWaypoint}})
        local state=RealisticCAS.afacNavigation[name] or {active=false,revision=r.revision}
        state.exitWaypoint=r.meta.navigation.exitWaypoint
        RealisticCAS.afacNavigation[name]=state
        r.returning=true
        notice(name,r,'returning to base: '..reason..'.')
      end
      return true
    end
    local function abort(name,r,controller,reason)
      return depart(name,r,controller,reason,true)
    end
    local function condition(name,revision,seconds)
      return string.format([[(function()
local R=RealisticCAS;local s=(R.afacNavigation or {})[%q]
if not s or s.revision~=%d then return true end
local start=(R.afacStations or {})[%q]
local g=Group.getByName(%q)
local done=not s.active or (R.afacAbort or {})[%q] or not g or not g:isExist() or
  (start and timer.getTime()>=start+%d)
if not done then for _,u in ipairs(g:getUnits())do
  if u:isExist() and u:getFuel()<=0.2 then done=true;break end
end end
if done then s.finished=true end
return done==true
end)()]],name,revision,name,name,name,seconds)
    end
    local function push(name,r,controller,source,plan)
      if not release(name,r,controller) then return false end
      r.revision=r.revision+1
      RealisticCAS.afacNavigation[name]={active=true,revision=r.revision,nextPoint=1,
        altitude=plan.altitude}
      local points={}
      local function waypoint(p,altitude)
        return {x=p.x,y=p.z,alt=altitude,alt_type='BARO',speed=r.meta.navigation.speed,
          speed_locked=true,type='Turning Point',action='Turning Point',
          task={id='ComboTask',params={tasks={}}}}
      end
      points[1]=waypoint(source,source.y)
      for index,p in ipairs(plan.path)do
        -- Climb during the validated safe transit, not only after reaching its end.
        local point=waypoint(p,plan.altitude)
        point.task.params.tasks[1]={number=1,auto=false,enabled=true,id='WrappedAction',
          params={action={id='Script',params={command=string.format(
            'local s=(RealisticCAS.afacNavigation or {})[%q]; if s and s.revision==%d then s.nextPoint=%d end',
            name,r.revision,index+1)}}}}
        points[#points+1]=point
      end
      local last=points[#points]
      last.task.params.tasks[2]={number=2,auto=false,enabled=true,id='Orbit',params={
        pattern='Circle',point={x=plan.point.x,y=plan.point.z},
        altitude=plan.altitude,speed=r.meta.navigation.speed}}
      controller:pushTask({id='ControlledTask',params={task={id='Mission',params={route={points=points}}},
        stopCondition={condition=condition(name,r.revision,r.meta.stationSeconds)}}})
      r.applied=true;r.plan=plan
      env.info(string.format('REALISTIC_CAS_AFAC_NAV|PLAN|%s|revision=%d|altitude=%.0f|points=%d',
        name,r.revision,plan.altitude,#plan.path))
      notice(name,r,string.format('avoiding known air defence; orbit %.0f m MSL.',plan.altitude))
      return true
    end
    local function update(name,r)
      local nativeGroup=Group.getByName(name)
      if not nativeGroup or not nativeGroup:isExist() then return end
      local controller=nativeGroup:getController()
      local source,ceiling,manual,bingo
      for _,id in ipairs(r.names) do
        local u=live(id)
        if u then
          if u:getPlayerName() then manual=true end
          if u:getFuel()<=0.2 then bingo=true end
          if u:inAir() then source=source or u end
          local ok,desc=pcall(function()return u:getDesc()end)
          local h=ok and type(desc)=='table' and desc.Hmax
          if S.finite(h) and h>0 then ceiling=math.min(ceiling or h,h) else ceiling=0 end
        end
      end
      if not source or manual then release(name,r,controller);return end
      local m=r.meta
      local start=(RealisticCAS.afacStations or {})[name]
      if start and not r.stationLogged then
        r.stationLogged=true
        env.info(string.format('REALISTIC_CAS_AFAC_NAV|STATION|%s|start=%.2f|end=%.2f',
          name,start,start+m.stationSeconds))
      end
      if RealisticCAS.afacReturn[name] then
        depart(name,r,controller,RealisticCAS.afacReturn[name],RealisticCAS.afacAbort[name]);return
      end
      if RealisticCAS.afacAbort[name] then abort(name,r,controller,'unsafe assigned zone');return end
      if bingo or (start and timer.getTime()>=start+m.stationSeconds) then
        depart(name,r,controller,bingo and 'BINGO fuel' or 'station complete',false);return
      end
      local p=source:getPoint()
      local knownThreats=relevant(r.side,p,m)
      if not knownThreats then abort(name,r,controller,'too many known threats for bounded planning');return end
      if r.nextPlan and timer.getTime()<r.nextPlan and r.threatCount==#knownThreats and
        math.abs(p.y-r.lastAltitude)<100 then return end
      r.nextPlan=timer.getTime()+5;r.threatCount=#knownThreats;r.lastAltitude=p.y
      local n=m.navigation
      local center={x=(n.points[1].x+n.points[2].x)/2,z=(n.points[1].z+n.points[2].z)/2}
      local ground=land.getHeight({x=center.x,y=center.z})
      local altitude=n.altitude+(n.altType=='RADIO' and ground or 0)
      local maxAltitude=ceiling and ceiling>300 and ceiling-300 or altitude
      maxAltitude=math.min(maxAltitude,ground+(c.probability and c.probability.opticalMaxAGL or 7010.4))
      local clouds=c.afacAvoidance.clouds
      if clouds then maxAltitude=math.min(maxAltitude,clouds.base-300) end
      local footprint=math.max(500,n.speed*n.speed/3.5)*1.5+250
      local input={source=p,zone=m.zone,points=n.points,altitude=altitude,
        maxAltitude=maxAltitude,footprint=footprint,threats=knownThreats,clearance=150,
        holdPoint=r.plan and r.plan.point,
        approach=not start,height=function(q)return land.getHeight({x=q.x,y=q.z})end}
      local state=RealisticCAS.afacNavigation[name]
      if r.applied and state and state.active and not state.finished and
        p.y<r.plan.altitude-100 and A.requirement(input) and A.safePlan(input,r.plan,state.nextPoint) then
        if not start and not r.plan.approach and RealisticCAS.AFACSearch.inside(p,m.zone) then
          RealisticCAS.afacStations=RealisticCAS.afacStations or {};RealisticCAS.afacStations[name]=timer.getTime()
        end
        return
      end
      local plan=A.plan(input)
      if plan.mode=='abort' then
        local why=knownThreats[1] and knownThreats[1].typeName or 'air defence'
        abort(name,r,controller,plan.reason..' ('..why..')')
      elseif plan.mode=='original' then
        if r.applied then
          if release(name,r,controller) then notice(name,r,'resuming assigned search route.') end
        end
      else
        if not start and not plan.approach and RealisticCAS.AFACSearch.inside(p,m.zone) then
          RealisticCAS.afacStations=RealisticCAS.afacStations or {};RealisticCAS.afacStations[name]=timer.getTime()
        end
        local changed=not r.applied or A.distance(r.plan.point,plan.point)>250 or
          math.abs(r.plan.altitude-plan.altitude)>100
        if not changed then
          local remaining=state and state.nextPoint or 1
          if not A.safePlan(input,r.plan,remaining) then changed=true end
        end
        if changed then
          push(name,r,controller,p,plan)
        end
      end
    end
    function api:clear(name,p)
      local r=groups[name]
      if not r or RealisticCAS.afacAbort[name] or RealisticCAS.afacReturn[name] then
        return false,'mission complete'
      end
      local list=relevant(r.side,p,r.meta)
      if not list then return false,'too many known threats' end
      local safe,t=A.clear(p,list,1000)
      return safe,t and t.typeName or nil
    end
    function api:observe(target)
      local r=byUnit[target.name]
      if r and target.groupName==r.meta.groupName and target.side==r.meta.coalition and
        target.typeName==r.meta.typeName and S.vector(target.point) then
        r.sample={name=target.name,typeName=target.typeName,side=target.side,
          point={x=target.point.x,y=target.point.y-1,z=target.point.z},
          radius=r.meta.radius,ceiling=r.meta.ceiling}
        r.seenKnowledge=true
      end
    end
    function api:tick()
      local now=timer.getTime()
      if not self.active or now<nextTick then return end
      nextTick=now+1;sample()
      for _=1,math.min(4,#order) do
        local name=order[groupCursor];groupCursor=groupCursor%#order+1
        local r=groups[name]
        local ok,err=pcall(update,name,r)
        if not ok then
          RealisticCAS.afacAbort[name]=true
          env.info('REALISTIC_CAS_AFAC_NAV|ERROR|'..name..'|'..tostring(err))
        end
      end
    end
    function api:stop()
      self.active=false
      local success=true
      for name,r in pairs(groups) do
        local g=Group.getByName(name)
        local controller=g and g:isExist() and g:getController() or nil
        if not release(name,r,controller) then success=false end
      end
      return success
    end
    return api
  end
end
