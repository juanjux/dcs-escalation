-- In-engine smoke test of the actual contact core, not a sensor model.
-- Immortal tanks keep the two test lanes available; no player aircraft.
do
  local started=timer.getTime()
  local finished=false
  local phase="INITIAL_HIDDEN"
  local failures=0
  local fired={RED_ARMOUR=0,BLUE_ARMOUR=0}
  local red=assert(Group.getByName("RED_ARMOUR"))
  local blue=assert(Group.getByName("BLUE_ARMOUR"))
  local names={"RED_ARMOUR","BLUE_ARMOUR"}
  local groups={RED_ARMOUR=red,BLUE_ARMOUR=blue}
  local function log(kind,message)
    env.info("RCAS_CORE_TEST|"..kind.."|elapsed="..string.format("%.1f",timer.getTime()-started)..
      "|phase="..phase.."|"..tostring(message))
  end
  local function check(condition,message)
    if not condition then failures=failures+1 end
    log(condition and "PASS" or "FAIL",message)
  end
  local function roe(g,value)
    g:getController():setOption(AI.Option.Ground.id.ROE,AI.Option.Ground.val.ROE[value])
    log("ROE",g:getName().."="..value)
  end
  local function point(g) return g:getUnit(1):getPoint() end
  local fog=assert(RealisticCAS.start({enabled=true,ttl=60,debug=true,targets={
    {name="RED_ARMOUR",originalInvisible=false},{name="BLUE_ARMOUR",originalInvisible=false}}}))
  local function hidden(name)
    local g=groups[name]
    local side=g:getCoalition()==1 and 2 or 1
    local c=fog.service:getContact(g:getID(),side)
    return not fog.service:isRevealed(g:getID(),side) and (not c or not c.backendVisible)
  end
  local events={}
  function events:onEvent(e)
    if finished or not e or not e.initiator then return end
    if e.id~=world.event.S_EVENT_SHOT and e.id~=world.event.S_EVENT_SHOOTING_START then return end
    local ok,err=pcall(function()
      local g=e.initiator:getGroup()
      if not g or fired[g:getName()]==nil then return end
      fired[g:getName()]=fired[g:getName()]+1
      log("FIRE",g:getName().."|event="..e.id.."|weapon="..
        tostring(e.weapon and e.weapon:getTypeName()))
    end)
    if not ok then failures=failures+1;log("ERROR",err) end
  end
  world.addEventHandler(events)
  local function at(seconds,label,action)
    timer.scheduleFunction(function()
      phase=label;log("PHASE",label)
      local ok,err=pcall(action)
      if not ok then failures=failures+1;log("ERROR",err) end
    end,nil,started+seconds)
  end
  at(20,"CHECK_INITIAL",function()
    check(fog.service:getDiagnostics().registered==2,"both groups registered")
    check(hidden("RED_ARMOUR") and hidden("BLUE_ARMOUR"),"both initially hidden in core")
  end)
  at(30,"REVEAL_BLUE",function()
    check(fog:observe("BLUE_ARMOUR",1,point(blue),"scripted observation"),"observe BLUE")
  end)
  at(40,"RED_FIRE",function() roe(red,"OPEN_FIRE") end)
  at(65,"RENEW_BLUE",function()
    check(fog:observe("BLUE_ARMOUR",1,point(blue),"scripted renewal"),"renew BLUE")
  end)
  at(75,"BLUE_FIRE",function() roe(blue,"OPEN_FIRE") end)
  at(210,"CEASE_FIRE",function()
    roe(red,"WEAPON_HOLD");roe(blue,"WEAPON_HOLD")
    check(fired.RED_ARMOUR>0,"RED produced real firing events (otherwise invalid fire coverage)")
    check(fired.BLUE_ARMOUR>0,"BLUE produced real firing events (otherwise invalid fire coverage)")
    for _,name in ipairs(names) do
      local g=groups[name];local enemy=g:getCoalition()==1 and 2 or 1
      local c=fog.service:getContact(g:getID(),enemy)
      check(c and c.reason=="fire",name.." fire reached actual core")
    end
  end)
  at(295,"CHECK_EXPIRED",function()
    check(hidden("RED_ARMOUR") and hidden("BLUE_ARMOUR"),"exposure expired after cease fire")
  end)
  at(300,"OBSERVE_RED",function()
    check(fog:observe("RED_ARMOUR",2,point(red),"scripted observation"),"observe RED")
  end)
  at(330,"RENEW_RED",function()
    check(fog:observe("RED_ARMOUR",2,point(red),"scripted renewal"),"renew RED")
  end)
  at(370,"CHECK_RENEWAL",function()
    check(fog.service:isRevealed(red:getID(),2),"renewal extended past original expiry")
  end)
  at(400,"CHECK_SECOND_EXPIRY",function()
    check(hidden("RED_ARMOUR"),"renewed RED expired")
  end)
  at(430,"STOP_RESTORE",function()
    check(fog:stop(),"stop restored ownership and removed runtime")
    check(fog.service:getDiagnostics().registered==0,"no registrations left")
  end)
  at(480,"FIN",function()
    log("RESULT", "failures="..failures.."|redFire="..fired.RED_ARMOUR.."|blueFire="..fired.BLUE_ARMOUR)
    trigger.action.outText("RCAS CORE FIN: "..failures.." fallos. Guarda dcs.log. No hace falta observar nada.",600)
    finished=true;world.removeEventHandler(events)
  end)
  timer.scheduleFunction(function(_,now)
    if finished then return nil end
    local ok,err=pcall(function()
      for _,name in ipairs(names) do
        local g=groups[name];local enemy=g:getCoalition()==1 and 2 or 1
        local target=name=="RED_ARMOUR" and blue or red
        local detected,visible,knowType,knowDistance,lastTime,lastPos=
          g:getController():isTargetDetected(target:getUnit(1))
        local c=fog.service:getContact(g:getID(),enemy)
        log("SAMPLE",name.."|ownExposed="..tostring(fog.service:isRevealed(g:getID(),enemy))..
          "|backendVisible="..tostring(c and c.backendVisible)..
          "|observedAt="..tostring(c and c.observedAt).."|expiresAt="..tostring(c and c.expiresAt)..
          "|enemyDetected="..tostring(detected).."|enemyVisible="..tostring(visible)..
          "|knowType="..tostring(knowType).."|knowDistance="..tostring(knowDistance)..
          "|lastTime="..tostring(lastTime).."|lastPos="..tostring(lastPos))
      end
      local d=fog.service:getDiagnostics()
      log("STATS","scheduled="..d.scheduled.."|reveals="..d.reveals.."|renewals="..d.renewals..
        "|expirations="..d.expirations.."|backendErrors="..d.backendErrors)
      trigger.action.outText("RCAS CORE / "..math.floor(now-started).."s / "..phase..
        "\nFallos="..failures..". Solo necesito el log. FIN a 480s.",5,true)
    end)
    if not ok then failures=failures+1;log("ERROR",err) end
    return now+5
  end,nil,started+5)
  log("START","actual prototype loaded; TTL=60; manual observations are test injections, not sensors")
end
