-- Ground-only diagnostic. Preserves original failing pairs, selects LOS-verified
-- controls from stationary candidate rings, never disables the actual LOS filter.
do
  local cfg=RCAS_GROUND_TEST
  local start=timer.getTime()
  local failures,inconclusive=0,0
  local checks,targets,groups,unique={},{},{},{}
  local cityGroup=nil
  local function log(kind,detail)
    env.info('RCAS_GROUND_TEST|'..kind..'|elapsed='..string.format('%.1f',timer.getTime()-start)..'|'..detail)
  end
  local function result(ok,message)
    if not ok then failures=failures+1 end
    log(ok and 'PASS' or 'FAIL',message)
  end
  local function invalid(message)
    inconclusive=inconclusive+1;log('INCONCLUSIVE',message)
  end
  local function geometry(observerName,targetName,verbose)
    local o,t=Unit.getByName(observerName),Unit.getByName(targetName)
    if not o or not t or not o:isExist() or not t:isExist() then return nil end
    local op,tp=o:getPoint(),t:getPoint()
    local a={x=op.x,y=op.y+2,z=op.z}
    local b={x=tp.x,y=tp.y+1,z=tp.z}
    local los=land.isVisible(a,b)
    local distance=math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2)
    if verbose then
      local minClearance=math.huge
      for i=1,39 do
        local f=i/40
        local h=land.getHeight({x=a.x+(b.x-a.x)*f,y=a.z+(b.z-a.z)*f})
        minClearance=math.min(minClearance,a.y+(b.y-a.y)*f-h)
      end
      local raisedA={x=a.x,y=a.y+10,z=a.z};local raisedB={x=b.x,y=b.y+10,z=b.z}
      log('GEOMETRY',string.format('%s -> %s|distance=%.2f|LOS=%s|a=%.2f,%.2f,%.2f|b=%.2f,%.2f,%.2f'..
        '|observerOriginAGL=%.2f|targetOriginAGL=%.2f|minSampledClearance=%.2f|LOS_plus10m=%s',
        observerName,targetName,distance,tostring(los),a.x,a.y,a.z,b.x,b.y,b.z,
        op.y-land.getHeight({x=op.x,y=op.z}),tp.y-land.getHeight({x=tp.x,y=tp.z}),
        minClearance,tostring(land.isVisible(raisedA,raisedB))))
    end
    return {los=los,distance=distance}
  end
  for _,set in ipairs(cfg.sets) do
    local chosen,initial
    for _,v in ipairs(set.candidates) do
      local g=geometry(set.observer,v.name,true)
      if g and (set.original or g.los==true) and not chosen then chosen=v;initial=g end
    end
    if not chosen then
      invalid(set.label..': no usable LOS pair; not a sensor failure')
    else
      log('SELECT',set.label..'|observer='..set.observer..'|target='..chosen.name..'|LOS='..tostring(initial.los))
      checks[#checks+1]={label=set.label,observer=set.observer,target=chosen,
        initialLOS=initial.los,expected=set.expected and initial.los==true,city=set.city==true}
      if set.city then cityGroup=chosen.groupName end
      if not unique[chosen.name] then
        unique[chosen.name]=true
        targets[#targets+1]={name=chosen.name,groupName=chosen.groupName}
        groups[#groups+1]={name=chosen.groupName,originalInvisible=false}
      end
    end
  end
  local fog=assert(RealisticCAS.start({enabled=true,ttl=30,debug=true,targets=groups}))
  local baseEnvironment=RealisticCAS.newEnvironment({defaultCover='desert',startTime=12*3600,
    sunrise=6*3600,sunset=18*3600,weather=1,visibility=30000})
  local engine=RealisticCAS.startDetection(fog,{observers=cfg.observers,targets=targets,
    debug=true,traceDecisions=true,environment=function(o,t,now)
      local e=baseEnvironment(o,t,now)
      if now-start>=60 and t.groupName==cityGroup then e.cover='city' end
      return e
    end})
  local function revealed(v)
    local g=Group.getByName(v.groupName)
    return fog.service:isRevealed(g:getID(),2)
  end
  local seen={}
  local done=false
  timer.scheduleFunction(function(_,now)
    if done then return nil end
    for _,v in ipairs(targets) do if revealed(v) then seen[v.name]=true end end
    trigger.action.outText('RCAS GROUND / '..math.floor(now-start)..'s / solo log. FIN a 180s.',5,true)
    return now+5
  end,nil,start+5)
  local function at(seconds,label,action)
    timer.scheduleFunction(function()
      log('PHASE',label)
      local ok,err=pcall(action)
      if not ok then failures=failures+1;log('ERROR',tostring(err)) end
    end,nil,start+seconds)
  end
  at(55,'BASELINE',function()
    for _,v in ipairs(checks) do
      local g=geometry(v.observer,v.target.name,true)
      if not g or g.los~=v.initialLOS then invalid(v.label..': LOS changed')
      else result((seen[v.target.name]==true)==v.expected,v.label..'|expected='..tostring(v.expected)) end
    end
  end)
  at(60,'CITY_COVER_ONLY',function()log('INFO','Only the selected city target cover changes; units do not move')end)
  at(110,'CITY_CHECK',function()
    for _,v in ipairs(checks) do
      if v.city then
        local g=geometry(v.observer,v.target.name,true)
        if not seen[v.target.name] or not g or not g.los then invalid('city lacked positive LOS/control')
        else result(not revealed(v.target),'city cover rejects previously observed identical geometry') end
      end
    end
    result(engine:getDiagnostics().errors==0,'no detector callback errors')
  end)
  at(120,'SENSORS_STOP',function()engine:stop()end)
  at(165,'EXPIRY',function()
    for _,v in ipairs(targets) do result(not revealed(v),'expired '..v.name) end
  end)
  at(180,'FIN',function()
    result(fog:stop(),'visibility restored')
    log('RESULT','failures='..failures..'|inconclusive='..inconclusive..'|checks='..#checks)
    trigger.action.outText('RCAS GROUND FIN: '..failures..' fallos, '..inconclusive..' inconclusos. Guarda dcs.log.',600)
    done=true
  end)
  log('START','real ground geometry and LOS; raised ray is diagnostic only, never used to reveal')
end
