-- Native AFAC effects. Candidate names come only from successful perception samples.
-- Each second visits at most 32 AFACs and rechecks one target per aircraft.
assert(RealisticCAS and RealisticCAS.newAFAC, 'load afac.lua first')

do
  local S=RealisticCAS.Sensors
  function RealisticCAS.validateAFACMarking(c)
    assert(type(c)=='table', 'AFAC marking configuration required')
    for _,key in ipairs({'markSeconds','messageSeconds','laserCode'}) do
      assert(S.finite(c[key]), 'missing AFAC setting '..key)
    end
    assert(type(c.coordinateFormat)=='number' and c.coordinateFormat==math.floor(c.coordinateFormat)
      and c.coordinateFormat>=0 and c.coordinateFormat<=2, 'invalid AFAC coordinate format')
    -- The pure coordinator validates code and time bounds without native effects.
    RealisticCAS.newAFAC({markSeconds=c.markSeconds,messageSeconds=c.messageSeconds,laserCode=c.laserCode})
  end

  function RealisticCAS.newAFACMarking(fog,c,callbacks,navigation)
    RealisticCAS.validateAFACMarking(c.afacMarking)
    local settings=c.afacMarking
    local records,order,spots,announced={},{},{},{}
    for _,meta in ipairs(c.observers) do
      if meta.afac then
        assert(#order<32, 'at most 32 simultaneous AFAC aircraft supported')
        assert(meta.coalition==1 or meta.coalition==2, 'AFAC coalition required')
        local rounds=meta.afac.smokeRounds or 0
        assert(S.finite(rounds) and rounds==math.floor(rounds) and rounds>=0 and rounds<=10000,
          'invalid AFAC smoke rounds')
        records[meta.name]={meta=meta,contacts={},cursor=1,groups={}}
        order[#order+1]=meta.name
      end
    end
    -- Keep a stable colour per smoke-capable aircraft. Observers without smoke
    -- do not consume a colour; each coalition cycles through the four colours.
    local smokers,used={},{[1]=0,[2]=0}
    local colours={'Green','Red','Orange','Blue'}
    for _,id in ipairs(order)do
      if (records[id].meta.afac.smokeRounds or 0)>0 then smokers[#smokers+1]=id end
    end
    table.sort(smokers)
    for _,id in ipairs(smokers)do
      local r=records[id]
      local side=r.meta.coalition
      r.smokeColour=colours[used[side]%#colours+1]
      used[side]=used[side]+1
    end
    local api={active=true}
    local nextTick=0
    local nextError=0
    local function errorLog(detail)
      local now=timer.getTime()
      if now>=nextError then
        env.info('REALISTIC_CAS_AFAC|ERROR|'..tostring(detail));nextError=now+60
      end
    end
    local function live(name)
      local u=Unit.getByName(name)
      if u and u:isExist() and u:getLife()>0 then return u end
    end
    local function label(id)
      local u=live(id)
      local ok,value=pcall(function() return u:getCallsign() end)
      return ok and type(value)=='string' and value~='' and value or id
    end
    local function coordinates(p)
      return RealisticCAS.contactCoordinates(p,settings.coordinateFormat)
    end
    local function message(id,text)
      local side=records[id].meta.coalition
      local full='JTAC '..label(id)..' '..text
      trigger.action.outTextForCoalition(side,full,settings.messageSeconds)
      env.info('REALISTIC_CAS_AFAC|side='..side..'|'..full)
    end
    local function stopMark(id)
      local handles=spots[id]
      if not handles then return true end
      local success=true
      for _,key in ipairs({'laser','infrared'}) do
        if handles[key] then
          local ok=pcall(function() handles[key]:destroy() end)
          if ok then handles[key]=nil else success=false;errorLog('spot destruction failed: '..id) end
        end
      end
      if success then spots[id]=nil end
      return success
    end
    local function startMark(id,t,request)
      assert(not spots[id], 'previous AFAC spots still active')
      local source=live(id)
      if not source then return false end
      local h={};spots[id]=h
      records[id].smoked=false
      if request.laser then
        h.laser=Spot.createLaser(source,{x=0,y=2,z=0},t.point,request.laserCode)
        if not h.laser then errorLog('native laser returned no spot: '..id);return false end
      end
      if request.infrared then
        h.infrared=Spot.createInfraRed(source,{x=0,y=2,z=0},t.point)
        if not h.infrared then return false end
      end
      records[id].marked=t
      return true
    end
    local function updateMark(id,t)
      local h=spots[id]
      if not h then return false end
      local r=records[id]
      if r.meta.equipment.irPointer==true and r.night and not h.infrared then
        h.infrared=Spot.createInfraRed(assert(live(id)),{x=0,y=2,z=0},t.point)
        if not h.infrared then return false end
      elseif not r.night and h.infrared then
        h.infrared:destroy();h.infrared=nil
      end
      for _,key in ipairs({'laser','infrared'}) do
        if h[key] then h[key]:setPoint(t.point) end
      end
      records[id].marked=t
      return h.laser~=nil or h.infrared~=nil or r.smoked==true
    end
    local function credit(id,detail)
      if not detail.laser and not detail.infrared and not detail.smoke then return end
      RealisticCAS.afacMarkCredits=RealisticCAS.afacMarkCredits or {}
      local side=records[id].meta.coalition
      local key=side..':'..detail.group
      if RealisticCAS.afacMarkCredits[key] then return end
      afac_marks=afac_marks or {}
      if #afac_marks>=10000 then return end
      RealisticCAS.afacMarkCredits[key]=true
      afac_marks[#afac_marks+1]={observer=id,target=detail.unit,group=detail.group,
        coalition=side,laser=detail.laser,infrared=detail.infrared,smoke=detail.smoke}
      dirty_state=true
    end
    local coordinator=RealisticCAS.newAFAC({enabled=true,clock=timer.getTime,
      log=errorLog,
      markSeconds=settings.markSeconds,stationSeconds=14400,
      messageSeconds=settings.messageSeconds,laserCode=settings.laserCode,contactBudget=1,
      startMark=startMark,updateMark=updateMark,stopMark=stopMark,
      smoke=function(id,t)
        local p=t.point
        trigger.action.smoke({x=p.x,y=land.getHeight({x=p.x,y=p.z}),z=p.z},
          trigger.smokeColor[records[id].smokeColour])
        records[id].smoked=true
        return true
      end,
      emit=function(side,id,kind,detail)
        local t=records[id].marked
        if kind=='mark' then
          credit(id,detail)
          local effects={}
          if detail.laser then effects[#effects+1]='lasing' end
          if detail.infrared then effects[#effects+1]='IR pointing' end
          if detail.smoke then effects[#effects+1]='smoking' end
          message(id,table.concat(effects,' and ')..' '..(t.typeName or t.id)..' at '..
            coordinates(t.point)..(detail.laser and (' with code '..detail.laserCode) or '')..
            (detail.smoke and (' ('..records[id].smokeColour:lower()..' smoke)') or '')..'.')
        else
          message(id,'unmarking '..(t and (t.typeName or t.id) or detail.unit)..
            ' ('..detail.reason..').')
          records[id].marked=nil
        end
      end})
    api.coordinator=coordinator
    for _,id in ipairs(order) do
      local meta=records[id].meta
      coordinator:register({id=id,side=meta.coalition,capabilities=meta.equipment,
        smokeRounds=meta.afac.smokeRounds or 0})
    end
    function api:observe(target,observer,newContact)
      local r=records[observer.name]
      if not self.active or not r then return end
      -- One queue entry per group; new observations can replace a dead member.
      local entry=r.groups[target.groupName]
      if not entry then
        if #r.contacts==32 then
          entry=table.remove(r.contacts,1);r.groups[entry.group]=nil
        end
        entry={group=target.groupName};r.contacts[#r.contacts+1]=entry
        r.groups[target.groupName]=entry
      end
      entry.name=target.name
      -- Campaign contact reports own discovery announcements, including the off
      -- switch. Keep legacy standalone diagnostics when that option is absent.
      if newContact and c.contactReports==nil then
        local key=observer.side..':'..target.groupName
        if not announced[key] then
          announced[key]=true
          message(observer.name,'found '..(target.typeName or target.name)..' at '..coordinates(target.point)..'.')
        end
      end
    end
    local function refresh(id,r,state)
      local source=live(id)
      if not source then
        -- Late-activated flights are not losses before their first native appearance.
        return r.seen and {alive=false} or {alive=true,fuel=1,onStation=false}
      end
      r.seen=true
      -- Human AFACs fire their own smoke stores; do not duplicate those rounds
      -- with scripted puffs while leaving their native payload untouched.
      if source:getPlayerName() then coordinator:disableSmoke(id) end
      local report={alive=true,fuel=source:getFuel(),onStation=false,contacts={}}
      local meta=r.meta.afac
      local start=(RealisticCAS.afacStations or {})[meta.groupName]
      report.stationComplete=(RealisticCAS.afacAbort or {})[meta.groupName] or
        (RealisticCAS.afacReturn or {})[meta.groupName]~=nil or
        (S.finite(start) and timer.getTime()>=start+meta.stationSeconds)
      local observer=callbacks.readObserver(id)
      if not observer then return report end
      report.onStation=true
      if navigation then
        local safe,reason=navigation:clear(meta.groupName,observer.point)
        if not safe then
          if r.safetyNotice~=reason then
            r.safetyNotice=reason
            message(id,'not marking: known '..tostring(reason)..' threat within range.')
          end
          return report
        end
        r.safetyNotice=nil
      end
      local entry
      if state.unit then entry={name=state.unit,group=state.group}
      elseif #r.contacts>0 then
        r.cursor=(r.cursor-1)%#r.contacts+1
        entry=r.contacts[r.cursor];r.cursor=r.cursor+1
      end
      if not entry then return report end
      local t=callbacks.readTarget(entry.name)
      if not t then
        report.targetDestroyed=state.unit~=nil and not live(entry.name)
        return report
      end
      if t.groupName~=entry.group or callbacks.isRevealed(t,observer)~=true then return report end
      local weather=c.environment(observer,t,timer.getTime())
      report.night=weather.light<0.5
      r.night=report.night
      if not S.assess(observer,t,weather,r.profile) then return report end
      local clouds=c.afacAvoidance and c.afacAvoidance.clouds
      if clouds and math.min(observer.point.y,t.point.y)<=clouds.top and
        math.max(observer.point.y,t.point.y)>=clouds.base then return report end
      -- A radar-only contact must not produce a laser through opaque cloud.
      if weather.visualTransmission<=0 or not land.isVisible(observer.point,t.point) then return report end
      report.contacts={{id=t.name,group=t.groupName,side=t.side,point=t.point,typeName=t.typeName,
        alive=true,revealed=true,observed=true,safe=true,inZone=true}}
      return report
    end
    for _,id in ipairs(order) do
      local meta=records[id].meta
      records[id].profile=S.profile(meta.typeName,meta.category,meta.equipment,c.probability)
      records[id].profile.rbmRange=0;records[id].profile.gmtiRange=0
    end
    function api:tick()
      local now=timer.getTime()
      if not self.active or now<nextTick then return end
      nextTick=now+1
      for _,id in ipairs(order) do
        local r=records[id]
        local ok,report=pcall(refresh,id,r,coordinator:get(id))
        if not ok then
          errorLog(report);report={alive=true,fuel=1,onStation=false}
        end
        coordinator:step(id,report)
      end
    end
    function api:stop()
      self.active=false
      return coordinator:stop()
    end
    function api:shot(id)
      if self.active and records[id] then coordinator:spendSmoke(id) end
    end
    function api:busy(id)
      local state=coordinator:get(id)
      return state and (state.state=='mark' or state.state=='stopping') or false
    end
    return api
  end
end
