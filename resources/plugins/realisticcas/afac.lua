-- AFAC coordinator, Lua 5.1. Native effects are supplied by the DCS adapter.
-- The caller supplies fresh, validated observations, never hidden live positions.
assert(RealisticCAS, "load core.lua first")

do
  local function finite(v)
    return type(v)=="number" and v==v and v~=math.huge and v~=-math.huge
  end
  local function integer(v,low,high)
    return finite(v) and v==math.floor(v) and v>=low and v<=high
  end
  local function name(v) return type(v)=="string" and #v>0 end
  local function point(p)
    if type(p)~="table" or not finite(p.x) or not finite(p.y) or not finite(p.z) then return nil end
    return {x=p.x,y=p.y,z=p.z}
  end
  local function target(t)
    return {id=t.id,group=t.group,side=t.side,point=point(t.point),typeName=t.typeName}
  end

  function RealisticCAS.newAFAC(options)
    local o=options or {}
    assert(type(o)=="table","AFAC options must be a table")
    assert(o.enabled==nil or type(o.enabled)=="boolean","invalid AFAC enable flag")
    local enabled=o.enabled==true
    local function setting(key,default)
      if o[key]==nil then return default end
      return o[key]
    end
    local markSeconds=setting("markSeconds",300)
    local stationSeconds=setting("stationSeconds",3600)
    local messageSeconds=setting("messageSeconds",15)
    local laserCode=setting("laserCode",1688)
    local contactBudget=setting("contactBudget",32)
    local bingo=setting("bingo",0.2)
    assert(integer(markSeconds,1,3600),"invalid AFAC mark duration")
    assert(integer(stationSeconds,1,14400),"invalid AFAC station duration")
    assert(integer(messageSeconds,1,300),"invalid AFAC message duration")
    assert(integer(contactBudget,1,256),"invalid AFAC contact budget")
    assert(finite(bingo) and bingo>=0 and bingo<=1,"invalid AFAC bingo")
    assert(integer(laserCode,1511,1788) and laserCode%10>=1 and laserCode%10<=8
      and math.floor(laserCode/10)%10>=1 and math.floor(laserCode/10)%10<=8
      and math.floor(laserCode/100)%10>=5 and math.floor(laserCode/100)%10<=7,
      "invalid AFAC laser code")
    if enabled then
      for _,key in ipairs({"clock","startMark","updateMark","stopMark","smoke"}) do
        assert(type(o[key])=="function",key.." callback required")
      end
    end
    local records,owners={},{}
    local lastTime=-math.huge
    local api={}
    local function now()
      local v=o.clock()
      assert(finite(v) and v>=lastTime,"AFAC clock must be finite and monotonic")
      lastTime=v;return v
    end
    local function event(r,kind,detail)
      -- The adapter must address r.side, never broadcast enemy reports globally.
      if o.emit then pcall(o.emit,r.side,r.id,kind,detail,messageSeconds) end
    end
    local function call(key,...)
      local ok,result=pcall(o[key],...)
      if not ok and o.log then pcall(o.log,key..': '..tostring(result)) end
      return ok and result==true
    end
    local function snapshot(r)
      return {id=r.id,side=r.side,state=r.state,reason=r.reason,
        group=r.mark and r.mark.group or nil,unit=r.mark and r.mark.id or nil,
        smokeRounds=r.smokeRounds,stationEnds=r.stationEnds,markEnds=r.markEnds,
        pendingState=r.pending and r.pending.state or nil}
    end
    local function cleanup(r)
      local p=r.pending
      if not p then return true end
      if not call("stopMark",r.id,target(r.mark)) then
        r.state="stopping";return false
      end
      -- Failed cleanup keeps the group reserved until the adapter confirms it.
      if owners[r.mark.group]==r.id then owners[r.mark.group]=nil end
      local old=r.mark
      r.mark,r.markEnds,r.pending=nil,nil,nil
      r.state,r.reason=p.state,p.reason
      event(r,"unmark",{group=old.group,unit=old.id,reason=p.reason})
      return true
    end
    local function leave(r,state,reason)
      if r.mark then
        r.pending={state=state,reason=reason};return cleanup(r)
      end
      r.state,r.reason=state,reason;return true
    end
    local function eligible(r,t)
      return type(t)=="table" and name(t.id) and name(t.group) and
        (t.typeName==nil or type(t.typeName)=="string") and
        (t.side==1 or t.side==2) and t.side~=r.side and t.alive==true and
        t.revealed==true and t.observed==true and t.safe==true and t.inZone==true and point(t.point)~=nil
    end

    function api:register(input)
      if not enabled then return false,"disabled" end
      assert(type(input)=="table" and name(input.id),"invalid AFAC observer")
      assert(input.side==1 or input.side==2,"invalid AFAC coalition")
      assert(not records[input.id],"duplicate AFAC observer")
      local c=input.capabilities or {}
      assert(type(c)=="table","AFAC capabilities must be a table")
      for _,key in ipairs({"laser","irPointer"}) do
        assert(c[key]==nil or type(c[key])=="boolean","invalid AFAC capability")
      end
      local rounds=input.smokeRounds or 0
      assert(integer(rounds,0,10000),"invalid AFAC smoke inventory")
      records[input.id]={id=input.id,side=input.side,state="transit",smokeRounds=rounds,
        laser=c.laser==true,irPointer=c.irPointer==true}
      return true
    end

    function api:step(id,report)
      if not enabled then return nil,"disabled" end
      local r=records[id]
      if not r then return nil,"unknown observer" end
      local time=now()
      if r.pending then
        -- A cleanup failure must not hide a subsequent loss/RTB request from
        -- the route adapter. Keep retrying cleanup, but export the exit intent.
        if type(report)=="table" and report.alive==false then
          r.pending={state="lost",reason="observer lost"}
        elseif r.pending.state~="lost" and ((r.stationEnds and time>=r.stationEnds) or
          (type(report)=="table" and report.stationComplete==true) or
          (type(report)=="table" and finite(report.fuel) and report.fuel>=0 and report.fuel<=bingo)) then
          r.pending={state="rtb",reason="station complete or bingo"}
        end
      end
      if not cleanup(r) then return snapshot(r) end
      if r.state=="rtb" or r.state=="lost" or r.state=="stopped" then return snapshot(r) end
      if type(report)~="table" or type(report.alive)~="boolean" then
        leave(r,r.stationEnds and "search" or "transit","invalid observer report")
        return snapshot(r)
      end
      -- A destroyed source need not expose fuel or any other native getters.
      if not report.alive then
        leave(r,"lost","observer lost");return snapshot(r)
      end
      if not finite(report.fuel) or report.fuel<0 or report.fuel>1 then
        leave(r,r.stationEnds and "search" or "transit","invalid observer report")
        return snapshot(r)
      end
      if report.fuel<=bingo or report.stationComplete==true or (r.stationEnds and time>=r.stationEnds) then
        local reason=report.fuel<=bingo and "bingo" or "station complete"
        leave(r,"rtb",reason);return snapshot(r)
      end
      if report.onStation~=true then
        leave(r,r.stationEnds and "search" or "transit","outside assigned zone")
        return snapshot(r)
      end
      -- The station clock starts on arrival and is never reset by re-entry.
      if not r.stationEnds then r.stationEnds=time+stationSeconds end
      r.state=r.mark and "mark" or "search"
      local contacts=type(report.contacts)=="table" and report.contacts or {}
      if r.mark then
        if report.targetDestroyed==true then
          leave(r,"search","target destroyed");return snapshot(r)
        end
        if time>=r.markEnds then
          r.blockedGroup=r.mark.group
          leave(r,"search","mark complete");return snapshot(r)
        end
        for i=1,math.min(#contacts,contactBudget) do
          local t=contacts[i]
          if eligible(r,t) and t.id==r.mark.id and t.group==r.mark.group then
            -- Updating a moving spot is an adapter responsibility; hand it only
            -- this newly observed sample, never an expired contact's live unit.
            if not call("updateMark",r.id,target(t)) then
              leave(r,"search","mark update failed")
            else r.mark=target(t) end
            return snapshot(r)
          end
        end
        leave(r,"search","observation or safety lost");return snapshot(r)
      end
      local infrared=report.night==true and r.irPointer
      if not r.laser and not infrared and r.smokeRounds==0 then return snapshot(r) end
      for i=1,math.min(#contacts,contactBudget) do
        local t=contacts[i]
        if eligible(r,t) and t.group~=r.blockedGroup and not owners[t.group] then
          -- Reserve the entire group, even when designating only one member.
          owners[t.group]=r.id;r.mark=target(t);r.markEnds=time+markSeconds
          local request={laser=r.laser,infrared=infrared,laserCode=laserCode,
            duration=markSeconds,coalition=r.side}
          if not call("startMark",r.id,target(t),request) then
            leave(r,"search","mark start failed");return snapshot(r)
          end
          r.state,r.reason,r.blockedGroup="mark",nil,nil
          local smoked=false
          if r.smokeRounds>0 then
            -- A failed/uncertain engine call cannot create free retry ammunition.
            r.smokeRounds=r.smokeRounds-1
            smoked=call("smoke",r.id,target(t))
          end
          if not r.laser and not infrared and not smoked then
            leave(r,"search","no effective marker");return snapshot(r)
          end
          event(r,"mark",{group=t.group,unit=t.id,laserCode=laserCode,
            laser=r.laser,infrared=infrared,smoke=smoked})
          return snapshot(r)
        end
      end
      return snapshot(r)
    end

    function api:get(id) return records[id] and snapshot(records[id]) or nil end

    function api:spendSmoke(id)
      -- Conservatively debit native weapon shots as well as scripted smoke.
      local r=records[id]
      if r then r.smokeRounds=math.max(0,r.smokeRounds-1) end
    end

    function api:disableSmoke(id)
      local r=records[id]
      if r then r.smokeRounds=0 end
    end

    function api:stop()
      if not enabled then return true end
      local success=true
      for _,r in pairs(records) do
        if not leave(r,"stopped","coordinator stopped") then success=false end
      end
      if success then enabled=false end
      return success
    end
    return api
  end
end
