-- Compare real native pursuit with patrol safety; no hostile tracks are injected.
do
  local c=__CONFIG__
  local api=assert(EscalationIMAC.start(c.config))
  local index,active=0,nil
  local handler={}
  local beginCase
  local function log(kind,text)
    env.info('IMAC_CAP_SAM|'..kind..'|case='..(active and active.row.group or 'none')..
      '|t='..string.format('%.1f',active and timer.getTime()-active.started or 0)..'|'..text)
  end
  local function destroy(name)
    local group=Group.getByName(name)
    if group and group:isExist()then group:destroy()end
  end
  local function step(state,seconds,fn)
    timer.scheduleFunction(function()
      if active~=state then return end
      local ok,why=pcall(fn)
      if not ok then state.errors=state.errors+1;log('ERROR',tostring(why))end
    end,nil,state.started+seconds)
  end
  beginCase=function()
    index=index+1
    if index>#c.cases then
      api:stop();world.removeEventHandler(handler)
      log('COMPLETE','cases='..#c.cases..'|Review actual control/guard paths, not order acceptance alone.')
      trigger.action.outText('IMAC CAP SAM COMPLETE. All four cases ended; review dcs.log. The mission can be ended.',90)
      return
    end
    local row=c.cases[index]
    local state={row=row,started=timer.getTime(),minimum=math.huge,entered=false,avoided=false,
      resumed=false,nativeDetected=false,intercepts=0,shots=0,samShots=0,errors=0}
    active=state
    c.config.options.avoidSamThreats=row.guarded
    for _,name in ipairs({row.group,row.bait,row.sam})do
      trigger.action.activateGroup(assert(Group.getByName(name)))
    end
    log('START','guarded='..tostring(row.guarded)..'|real native EngageTargets at 50NM; immortal aircraft')
    trigger.action.outText('IMAC CAP SAM '..index..'/'..#c.cases..': '..row.group,20)
    timer.scheduleFunction(function(_,now)
      if active~=state then return end
      local ok,why=pcall(function()
        local flight=assert(Group.getByName(row.group))
        local order=api.states[row.group].order
        local kind=order and order.kind or 'native'
        if kind=='samAvoid'then state.avoided=true end
        if state.avoided and kind=='native'then state.resumed=true end
        local distances={}
        for _,unit in ipairs(flight:getUnits())do
          if unit:isExist()and unit:getLife()>0 then
            local point=unit:getPoint()
            local range=EscalationIMAC.geometry.distance(point,row.center)
            if now-state.started<210 then
              state.minimum=math.min(state.minimum,range)
              if range<row.radius then state.entered=true end
            end
            distances[#distances+1]=string.format('%.0f',range)
            local bait=Group.getByName(row.bait):getUnits()[1]
            local detected=unit:getController():isTargetDetected(bait,1,2,4,8)
            state.nativeDetected=state.nativeDetected or detected==true
          end
        end
        log('STATE','order='..kind..'|ranges='..table.concat(distances,',')..
          '|nativeDetected='..tostring(state.nativeDetected))
      end)
      if not ok then state.errors=state.errors+1;log('ERROR',tostring(why))end
      return now+5
    end,nil,state.started+5)
    step(state,210,function()destroy(row.sam);log('SAM_REMOVED','test-owned removal; no combat kill assumed')end)
    step(state,c.duration,function()
      for _,entry in ipairs(api.history)do
        if entry.group==row.group and entry.kind=='intercept'then state.intercepts=state.intercepts+1 end
      end
      log('RESULT','guarded='..tostring(row.guarded)..'|minimumWhileSamAlive='..state.minimum..
        '|enteredActualRing='..tostring(state.entered)..'|avoidanceObserved='..tostring(state.avoided)..
        '|resumptionObserved='..tostring(state.resumed)..'|nativeDetected='..tostring(state.nativeDetected)..
        '|imacIntercepts='..state.intercepts..'|fighterShots='..state.shots..'|samShots='..state.samShots..
        '|errors='..state.errors)
      for _,name in ipairs({row.group,row.bait,row.sam})do destroy(name)end
      active=nil
      timer.scheduleFunction(function()beginCase()end,nil,timer.getTime()+5)
    end)
  end
  function handler:onEvent(event)
    if not active or not event or event.id~=world.event.S_EVENT_SHOT then return end
    local ok,group=pcall(function()return event.initiator:getGroup():getName()end)
    if not ok then return end
    if group==active.row.group then active.shots=active.shots+1
    elseif group==active.row.sam then active.samShots=active.samShots+1 end
  end
  world.addEventHandler(handler)
  beginCase()
end
