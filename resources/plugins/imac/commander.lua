-- Decision engine: all observations and native orders pass through an adapter.
assert(EscalationIMAC and EscalationIMAC.geometry,'load IMAC geometry first')
do
  local API,G=EscalationIMAC,EscalationIMAC.geometry
  local NM,ORBIT_LEASE=1852,600
  local AIR_CLEARANCE_SECONDS=180
  local WINCHESTER='WINCHESTER during fighter evasion'
  function API.newCommander(config,io)
    local opt=config.options
    local api={states={},paused={},active=true,history={}}
    local now=0
    local tracks,threats,samples,authority={},{},{},{}
    local noThreats={}
    local function flightThreats(s)
      local sead=s.meta.seadMission or s.meta.deadSupport or s.meta.mode=='dead'
      if sead then
        if opt.avoidSamThreats==false or opt.neverDivertSead~=false then return noThreats end
      elseif opt.avoidSamThreats==false and
        (s.meta.mode=='strike' or s.meta.mode=='cap' or s.meta.returnInterceptor or
          s.meta.packageDefenseStart) then return noThreats end
      return threats[s.meta.side]
    end
    local function diagnose(s,topic,detail)
      if opt.debug and io.debug then io.debug(s.meta.side,s.meta.group,topic,detail) end
    end
    for _,meta in ipairs(config.flights) do
      assert(not api.states[meta.group],'duplicate IMAC group')
      api.states[meta.group]={meta=meta,index=1,revision=0,cooldown=0}
    end
    local function record(s,kind,reason)
      local entry={time=now,group=s.meta.group,side=s.meta.side,kind=kind,reason=reason}
      api.history[#api.history+1]=entry
      if #api.history>128 then table.remove(api.history,1) end
      io.report(entry)
    end
    local function release(s,reason,restoreAvoidance)
      if not s.order then return end
      local avoidance=s.order.data.avoidance
      -- An intercept pushed over SAM avoidance leaves the orbit as the native root.
      if s.order.kind=='samAvoid' or (avoidance and not restoreAvoidance) then
        local ok,why=io.resumeCap(s)
        if not ok then diagnose(s,'resume blocked',tostring(why));return end
      end
      s.revision=s.revision+1;s.order=restoreAvoidance and avoidance or nil;s.cooldown=now+30
      if s.order then
        s.order.clearSince=nil
        record(s,'samAvoid','intercept ended; return to SAM avoidance orbit')
        return
      end
      record(s,'resume',reason)
      -- No popTask: it could remove a tanker's or human commander's task.
    end
    local function resumeDelayedAttack(s,reason)
      local attack=s.meta.mode=='strike' or
        (s.meta.mode=='dead' and (s.meta.deadSupport or not s.meta.seadMission))
      if attack and s.index<s.meta.attackIndex and not s.pendingHold then
        local ok,detail=io.resumeAttack(s)
        if not ok then diagnose(s,'resume blocked',detail);return false end
        if detail then diagnose(s,'resume route',detail) end
      end
      release(s,reason)
      return true
    end
    local function nativeRefuel(s)
      local state=EscalationBARCAP and EscalationBARCAP.states[s.meta.group]
      return state and (state.refuelling or state.finished)
    end
    local function returningFighter(s)
      return s.meta.returnInterceptor==true and s.meta.returnStartIndex and
        s.index>=s.meta.returnStartIndex and s.index<(s.meta.approachIndex or #s.meta.route)
    end
    local function packageDefender(s)
      return s.meta.packageDefenseStart and s.index>=s.meta.packageDefenseStart and
        s.index<math.min(s.meta.recoveryIndex,s.meta.approachIndex or #s.meta.route)
    end
    local function home(s)
      local point=s.meta.route[#s.meta.route]
      return {x=point.x,z=point.y}
    end
    local function anchor(s,p)
      if s.order and s.order.data.anchor then return s.order.data.anchor end
      if returningFighter(s) or packageDefender(s) then return G.copy(p.point) end
      local point=s.meta.route[s.meta.stationStart]
      return {x=point.x,z=point.y}
    end
    local function reservation(track)
      if track.kind=='missile' then return 'missile:'..track.key end
      return 'group:'..tostring(track.groupId)
    end
    local function unavailable(s,p)
      if not p then return 'flight unavailable' end
      if p.player then return 'human-controlled flight' end
      if s.paused or api.paused[s.meta.side] then return 'manual control / commander paused' end
      if not authority[s.meta.side] then return 'no active command authority or side disabled' end
      if not p.airborne then return 'not airborne' end
      if not p.healthy then return 'aircraft damaged' end
      if p.refuelling or nativeRefuel(s) then return 'native refuelling or recovery owns the flight' end
      if not G.finite(p.fuel) or p.fuel<=s.meta.bingo+0.05 then return 'fuel at BINGO reserve or unavailable' end
      if s.finished or (s.index>=s.meta.recoveryIndex and not returningFighter(s)) then
        return 'recovering / mission complete'
      end
      if returningFighter(s) and G.distance(p.point,home(s))<15*NM and
        p.point.y-io.height(p.point)<1500 then return 'landing approach' end
      if s.meta.endTime and now>=s.meta.endTime and not returningFighter(s) then
        return 'original station time expired'
      end
    end
    local function available(s,p)
      return unavailable(s,p)==nil
    end
    local function bingoWhileWaiting(s,p,why)
      local attackEvasion=s.order and s.order.kind=='evade' and
        (s.meta.mode=='strike' or s.meta.mode=='dead')
      return why=='fuel at BINGO reserve or unavailable' and p and G.finite(p.fuel) and
        (s.pendingHold or attackEvasion or
          (s.order and (s.order.kind=='hold' or s.order.kind=='samAvoid' or s.order.data.avoidance)))
    end
    local function bingoReason(s)
      if s.order and (s.order.kind=='samAvoid' or s.order.data.avoidance) then
        return 'BINGO during SAM avoidance'
      end
      if s.pendingHold or (s.order and s.order.kind=='hold') then
        return 'BINGO while waiting for DEAD/SEAD'
      end
      return 'BINGO during fighter evasion'
    end
    local function push(s,kind,data,duration)
      local previous=s.order
      if now<s.cooldown or (previous and not (kind=='intercept' and previous.kind=='samAvoid')) then return false end
      data.avoidance=previous
      s.revision=s.revision+1
      s.order={kind=kind,data=data,issued=now,deadline=now+duration,revision=s.revision}
      local ok,why=io.order(s,s.order)
      if not ok then s.order=previous;s.cooldown=now+60;record(s,'error',tostring(why));return false end
      record(s,kind,data.reason or kind)
      local detail='target group='..tostring(data.groupId)
      if data.point then detail=string.format('%s x=%.0f z=%.0f',
        kind=='intercept' and 'missile intercept' or 'safe orbit',data.point.x,data.point.z) end
      diagnose(s,'order',kind..'; '..detail..'; lease='..duration..'s')
      return true
    end
    function api:reached(name,index)
      local s=self.states[name]
      if s and index>s.index then
        s.index=index
        if index>=s.meta.attackIndex then s.pendingHold=nil end
      end
    end
    function api:pause(side,value)
      self.paused[side]=value==true
      if value then for _,s in pairs(self.states) do if s.meta.side==side then release(s,'commander paused') end end end
    end
    function api:pauseFlight(name,value)
      local s=self.states[name]
      if s then s.paused=value==true;if value then release(s,'flight released for manual control') end end
    end
    function api:stop()
      self.active=false
      for _,s in pairs(self.states) do release(s,'commander stopped') end
    end
    function api:shouldStop(name,revision)
      local s=self.states[name]
      if not self.active or not s or not s.order or s.revision~=revision then return true end
      -- Native stop conditions also run between decision ticks. Player takeover,
      -- station expiry and loss of authority release tasks immediately. BINGO
      -- during a DEAD/SEAD hold first requests a safe recovery route.
      now=io.time()
      authority[s.meta.side]=io.authority(s.meta.side)
      local p=io.sample(s.meta)
      local why=unavailable(s,p)
      if bingoWhileWaiting(s,p,why) then
        -- Keep the attack suspended until the decision cycle installs recovery.
        s.abortReason=bingoReason(s);return false
      end
      if why then
        release(s,'temporary order ended');return true
      end
      if now>=s.order.deadline then
        if s.order.kind=='recoveryHold' then
          s.order.deadline=now+opt.interval*2
        elseif s.order.kind=='evade' or s.order.kind=='hold' or s.order.kind=='samAvoid' then
          -- Safety, not lease age, decides when to resume. The next tick still
          -- checks clearance; BINGO and command loss remain higher priority.
          s.order.deadline=now+ORBIT_LEASE
        else release(s,'temporary order expired',true);return true end
      end
      return false
    end
    local function dangers(s,p)
      local out={}
      if opt.evadeFighters==false or
        (s.meta.fighterMission and opt.neverEvadeFighterMissions~=false) then return out end
      for _,t in ipairs(tracks[s.meta.side]) do
        if t.kind=='fighter' or t.kind=='unknown' then
          local d=G.distance(p.point,t.point)
          if d<opt.defendRangeNm*NM and
            (d<15*NM or G.closing(p.point,p.velocity,t.point,t.velocity)>20) then out[#out+1]=t end
        end
      end
      return out
    end
    local function airLegClear(s,from,to,startTime,endTime)
      local margin=(opt.defendRangeNm+10)*NM
      for _,t in ipairs(tracks[s.meta.side]) do
        if t.kind=='fighter' or t.kind=='unknown' then
          local relativeFrom={x=from.x-t.point.x-t.velocity.x*startTime,
            z=from.z-t.point.z-t.velocity.z*startTime}
          local relativeTo={x=to.x-t.point.x-t.velocity.x*endTime,
            z=to.z-t.point.z-t.velocity.z*endTime}
          if G.segment(from,to,t.point)<margin or
            G.segment(relativeFrom,relativeTo,{x=0,z=0})<margin then return false end
        end
      end
      return true
    end
    local function evasionClear(s,p)
      local target=s.pendingHold and s.pendingHold.data.point
      if not target then
        local wp=s.meta.route[math.min(#s.meta.route,s.index+1)]
        target={x=wp.x,z=wp.y}
      end
      local seconds=AIR_CLEARANCE_SECONDS
      local length=G.distance(p.point,target)
      local f=length>0 and math.min(1,p.speed*seconds/length) or 0
      local finish={x=p.point.x+(target.x-p.point.x)*f,z=p.point.z+(target.z-p.point.z)*f}
      return airLegClear(s,p.point,finish,0,seconds)
    end
    local function recoveryClear(s,points)
      -- Use the actual recovery legs, including any detours inserted by DCS's adapter.
      local elapsed=0
      for i=2,#points do
        local start,finish=points[i-1],points[i]
        local from,to={x=start.x,z=start.y},{x=finish.x,z=finish.y}
        local duration=G.distance(from,to)/math.max(1,finish.speed)
        local seconds=math.min(duration,AIR_CLEARANCE_SECONDS-elapsed)
        if seconds<duration then
          local f=seconds/duration
          to={x=from.x+(to.x-from.x)*f,z=from.z+(to.z-from.z)*f}
        end
        if not airLegClear(s,from,to,elapsed,elapsed+seconds) then return false end
        elapsed=elapsed+seconds
        if elapsed>=AIR_CLEARANCE_SECONDS then break end
      end
      return true
    end
    local function destination(s)
      local route=s.meta.route
      local p=route[math.min(#route,s.meta.recoveryIndex+1)]
      return {x=p.x,y=p.alt,z=p.y}
    end
    local function retreat(s,p,reason)
      s.abortReason=reason
      local clear
      if reason==WINCHESTER then clear=function(points)return recoveryClear(s,points)end end
      local ok,why=io.recover(s,p,flightThreats(s),clear)
      if ok then
        s.revision=s.revision+1;s.order=nil;s.pendingHold=nil;s.finished=true;s.abortReason=nil;record(s,'rtb',reason)
      else
        -- Keep an existing safe hold suspended above the original attack route.
        -- A failed recovery search must not accidentally resume that attack.
        if s.order then s.order.deadline=now+60
        else
          local q=G.escape(p.point,{},flightThreats(s),io.height,p.speed,destination(s))
          if q then push(s,'recoveryHold',{point=q,reason='waiting for a safe recovery corridor'},60) end
        end
        if now>=(s.nextRecovery or 0) then
          s.nextRecovery=now+60;record(s,'blocked','no safe recovery corridor: '..tostring(why))
        end
      end
    end
    local function capPathSafe(s,p,q,escape)
      for _,member in ipairs(p.members or {p})do
        if not G.safe(member.point,q,math.min(member.point.y,q.y),flightThreats(s),io.height,12000,escape)then
          return false
        end
      end
      return true
    end
    local function capExposure(s,p)
      for _,member in ipairs(p.members or {p})do
        local a,v=member.point,member.velocity
        local q={x=a.x+v.x*60,y=a.y+(v.y or 0)*60,z=a.z+v.z*60}
        local clear,threat=G.leg(a,q,math.min(a.y,q.y),flightThreats(s),12000,true)
        if not clear then return threat end
      end
    end
    local function avoidCapSam(s,p,threat)
      if s.index>=s.meta.recoveryIndex then retreat(s,p,'SAM blocks returning patrol');return end
      local q=G.escape(p.point,{},flightThreats(s),io.height,p.speed,anchor(s,p),
        function(point)return capPathSafe(s,p,point,true)end)
      if not q then
        if now>=(s.nextCapWarning or 0)then
          s.nextCapWarning=now+60;record(s,'blocked','no safe SAM escape corridor for all patrol members')
        end
        return
      end
      local old,revision=s.order,s.revision
      s.order=nil;s.cooldown=0
      if not push(s,'samAvoid',{point=q,reason='known SAM threatens patrol ('..
        tostring(threat and threat.name or 'unknown')..'); suspend native pursuit'},ORBIT_LEASE)then
        s.order=old;s.revision=revision
      end
    end
    local function capResumeClear(s,p)
      local index=s.index<s.meta.recoveryIndex and s.meta.stationStart or math.min(#s.meta.route,s.index+1)
      local wp=s.meta.route[math.max(1,index)]
      local q={x=wp.x,y=io.altitude(wp),z=wp.y}
      if not capPathSafe(s,p,q,false)then return false end
      if s.index<s.meta.recoveryIndex then
        for i=s.meta.stationStart+1,s.meta.recoveryIndex do
          local nextPoint=s.meta.route[i]
          local to={x=nextPoint.x,y=io.altitude(nextPoint),z=nextPoint.y}
          if not G.safe(q,to,math.min(q.y,to.y),flightThreats(s),io.height,12000)then return false end
          q=to
        end
        q={x=wp.x,y=io.altitude(wp),z=wp.y}
        local reach=50*NM
        for _,point in ipairs(s.meta.route)do
          for _,task in ipairs(point.task and point.task.params and point.task.params.tasks or {})do
            if task.id=='EngageTargets' then
              reach=task.params.maxDistEnabled and task.params.maxDist or math.huge
            end
          end
        end
        -- Do not restore the native pursuit while an observed target within its
        -- engagement range would immediately draw it back through a SAM ring.
        for _,t in ipairs(tracks[s.meta.side])do
          if math.min(G.distance(p.point,t.point),G.distance(q,t.point))<reach and
            (not G.leg(p.point,t.point,math.min(p.point.y,t.point.y),flightThreats(s),12000)or
             not G.leg(q,t.point,math.min(q.y,t.point.y),flightThreats(s),12000))then return false end
        end
      end
      return true
    end
    local function blocker(s,p)
      if (s.meta.mode~='strike' and s.meta.mode~='dead') or s.index>=s.meta.attackIndex then return end
      local target=s.meta.route[s.index+1]
      if not target then return end
      local q={x=target.x,y=target.alt,z=target.y}
      local length=G.distance(p.point,q)
      local reach=p.speed*180+10000
      if length>reach then
        local f=reach/length;q.x=p.point.x+(q.x-p.point.x)*f;q.z=p.point.z+(q.z-p.point.z)*f
      end
      local altitude=math.min(p.point.y,io.altitude(target))
      local clear,t=G.leg(p.point,q,altitude,flightThreats(s),10000)
      if not clear then return t,p.point,q,altitude end
    end
    local function pendingDEAD(s,t,support)
      local pending={}
      for name,other in pairs(api.states) do
        local p=samples[name]
        if other~=s and other.meta.side==s.meta.side and (other.meta.deadSupport or other.meta.mode=='dead') and p and p.airborne and
          G.finite(p.fuel) and p.fuel>other.meta.bingo+0.05 and not other.finished and not other.abortReason and
          other.index<other.meta.recoveryIndex and
          ((support and support[name]) or (not support and
            (other.meta.package==s.meta.package or G.distance(p.point,t.point)<60*NM))) then pending[name]=true end
      end
      if next(pending) then return pending end
    end
    local function resumeHold(s,p)
      local hold=s.pendingHold
      if not hold then return end
      s.pendingHold=nil
      local clear,t=G.leg(hold.data.from,hold.data.to,hold.data.altitude,flightThreats(s),10000)
      if clear then return end
      if not pendingDEAD(s,t,hold.data.support) then retreat(s,p,'DEAD/SEAD ended; attack corridor still unsafe');return end
      local q=G.escape(p.point,{},flightThreats(s),io.height,p.speed,destination(s))
      if not q then retreat(s,p,'no safe holding area');return end
      hold.data.point=q;s.cooldown=0
      push(s,'hold',hold.data,ORBIT_LEASE)
    end
    local function service(s,p)
      local why=unavailable(s,p)
      if why then
        if s.meta.mode~='observe' or s.meta.returnInterceptor or s.meta.packageDefenseStart then
          local detail=why
          if why=='fuel at BINGO reserve or unavailable' and p and G.finite(p.fuel) then
            detail=string.format('fuel at BINGO reserve (%.0f%% fuel, %.0f%% reserve)',
              p.fuel*100,(s.meta.bingo+0.05)*100)
          end
          diagnose(s,'availability',detail)
        end
        if bingoWhileWaiting(s,p,why) then
          retreat(s,p,bingoReason(s));return
        end
        release(s,'unavailable, BINGO, recovery or command lost');return
      end
      if s.abortReason then
        if now>=(s.retryRecovery or 0) then
          s.retryRecovery=now+30;retreat(s,p,s.abortReason)
        end
        return
      end
      if s.pendingHold then
        local hold=s.pendingHold
        local clear,t=G.leg(hold.data.from,hold.data.to,hold.data.altitude,flightThreats(s),10000)
        if clear then s.pendingHold=nil
        elseif not pendingDEAD(s,t,hold.data.support) then
          retreat(s,p,'DEAD/SEAD ended; attack corridor still unsafe');return
        end
      end
      -- Native EngageTargets can pursue independently of IMAC orders. Guard
      -- every patrol member's actual heading, including during a cooldown.
      if s.meta.mode=='cap' and s.index>=s.meta.stationStart and
        (not s.order or s.order.kind=='intercept')then
        local threat=capExposure(s,p)
        if threat then avoidCapSam(s,p,threat);return end
      end
      local order=s.order
      if order then
        diagnose(s,'active',string.format('%s; waypoint=%d; fuel=%.0f%%; remaining=%.0fs',
          order.kind,s.index,p.fuel*100,math.max(0,order.deadline-now)))
        if now>=order.deadline then
          if order.kind=='hold' or order.kind=='evade' or order.kind=='samAvoid' then order.deadline=now+ORBIT_LEASE
          else release(s,'temporary order expired',true);resumeHold(s,p) end
          if order.kind~='evade' and order.kind~='hold' and order.kind~='samAvoid' then return end
        end
        if order.kind=='intercept' then
          local target
          for _,t in ipairs(tracks[s.meta.side]) do if t.key==order.data.key then target=t;break end end
          local centre=anchor(s,p)
          local aim=target and G.copy(target.point)
          if aim then
            local seconds=math.min(60,G.distance(p.point,aim)/math.max(100,p.speed))
            aim.x=aim.x+target.velocity.x*seconds;aim.z=aim.z+target.velocity.z*seconds
          end
          local reason
          if not target then reason='contact expired; resume original route'
          elseif order.data.packageDefense and not packageDefender(s) then
            reason='package defense leg ended; resume original route'
          elseif not p.ammo then reason='air-to-air ammunition exhausted; resume original route'
          elseif nativeRefuel(s) then reason='native refuelling owns the flight'
          elseif p.fuel<=s.meta.bingo+0.08+(s.meta.burnPerMeter or 0)*
            G.distance(p.point,returningFighter(s) and home(s) or centre) then
            reason='fuel reserve reached; resume original route'
          elseif G.distance(p.point,centre)>opt.patrolLeashNm*NM or
            G.distance(aim,centre)>opt.patrolLeashNm*NM then reason='intercept leash exceeded; resume original route'
          elseif not G.safe(p.point,aim,target.kind=='missile' and p.point.y or math.min(p.point.y,aim.y),
            flightThreats(s),io.height,12000) or
            not G.safe(p.point,target.point,target.kind=='missile' and p.point.y or math.min(p.point.y,target.point.y),
              flightThreats(s),io.height,12000) then
            reason='known SAM or terrain blocks pursuit; resume original route'
          end
          if reason then
            if s.meta.mode=='cap' and reason=='known SAM or terrain blocks pursuit; resume original route' then
              local _,threat=G.leg(p.point,aim,math.min(p.point.y,aim.y),flightThreats(s),12000)
              if not threat then _,threat=G.leg(p.point,target.point,math.min(p.point.y,target.point.y),flightThreats(s),12000)end
              if threat then avoidCapSam(s,p,threat);return end
            end
            release(s,reason,true);return
          end
          local d=G.distance(target.point,order.data.asset)
          if d>order.data.nearest+5000 then order.retreatSince=order.retreatSince or now
          else order.retreatSince=nil;order.data.nearest=math.min(order.data.nearest,d) end
          if order.retreatSince and now-order.retreatSince>=opt.pursuitSeconds then
            release(s,'enemy withdrawing; resume original route',true)
          end
        elseif order.kind=='samAvoid' then
          if not capPathSafe(s,p,order.data.point,true) or
            not G.leg(order.data.point,order.data.point,order.data.point.y,flightThreats(s),17000)then
            avoidCapSam(s,p);return
          end
          if capResumeClear(s,p) then
            order.clearSince=order.clearSince or now
            if now-order.clearSince>=60 then release(s,'SAM-safe patrol and pursuit corridors restored')end
          else order.clearSince=nil end
        elseif order.kind=='evade' then
          if s.meta.deadSupport and s.index>=s.meta.attackIndex and p.groundAmmo==false then
            s.retryRecovery=now+30
            retreat(s,p,WINCHESTER);return
          end
          if evasionClear(s,p) then
            order.clearSince=order.clearSince or now
            if now-order.clearSince>=30 then
              if resumeDelayedAttack(s,'air threat cleared') then resumeHold(s,p) end
              return
            end
          else order.clearSince=nil end
          if not G.safe(p.point,order.data.point,p.point.y,flightThreats(s),io.height,15000,true) then
            resumeDelayedAttack(s,'evasion corridor changed')
          end
        elseif order.kind=='hold' then
          local danger=dangers(s,p)
          if #danger>0 then
            local q=G.escape(p.point,danger,flightThreats(s),io.height,p.speed,destination(s))
            if q then
              s.order=nil
              if push(s,'evade',{point=q,reason='enemy fighters approaching; leave holding area'},600) then
                s.pendingHold=order
              else s.order=order;s.revision=order.revision end
              return
            end
          end
          local clear,threat=G.leg(order.data.from,order.data.to,order.data.altitude,flightThreats(s),10000)
          if clear then resumeDelayedAttack(s,'attack corridor clear')
          elseif not pendingDEAD(s,threat,order.data.support) then retreat(s,p,'DEAD/SEAD ended; attack corridor still unsafe') end
        end
        return
      end
      if now<s.cooldown or s.meta.mode=='observe' or s.meta.mode=='cap' or
        (returningFighter(s) and p.ammo) then return end
      local danger=dangers(s,p)
      if #danger>0 then
        local q=G.escape(p.point,danger,flightThreats(s),io.height,p.speed,destination(s))
        if q then push(s,'evade',{point=q,reason='enemy fighters approaching; reposition safely'},600) end
        return
      end
      if s.pendingHold then resumeHold(s,p);return end
      local threat,from,to,altitude=blocker(s,p)
      if threat then
        local support=pendingDEAD(s,threat)
        if support then
          local q=G.escape(p.point,{},flightThreats(s),io.height,p.speed,destination(s))
          if q then push(s,'hold',{point=q,from=G.copy(from),to=G.copy(to),altitude=altitude,
            support=support,reason='known SAM blocks ingress ('..tostring(threat.name or 'unknown')..'); waiting for DEAD/SEAD'},ORBIT_LEASE)
          else retreat(s,p,'no safe holding area') end
        else retreat(s,p,'known SAM blocks ingress; no active DEAD/SEAD') end
      end
    end
    local function targetPriority(t,side)
      local best,asset
      local packages={}
      for name,s in pairs(api.states) do
        local p=samples[name]
        if s.meta.side==side and p and p.airborne and not s.finished then
          local vulnerable=s.meta.mode~='cap'
          local avoidingSAM=s.order and s.order.kind=='samAvoid'
          local distance=G.distance(p.point,t.point)
          local closing=distance<15*NM or G.closing(p.point,p.velocity,t.point,t.velocity)>20
          local attacker=t.kind=='bomber' or t.kind=='attack' or t.kind=='transport' or t.kind=='missile'
          local defend=(vulnerable and closing) or (avoidingSAM and t.kind=='fighter')
          if (defend and distance<opt.defendRangeNm*NM) or
            (attacker and closing and distance<opt.interceptRangeNm*NM) then
            local score=(vulnerable and 1000000 or 0)+(attacker and 200000 or 0)-distance
            if not best or score>best then best,asset=score,G.copy(p.point) end
          end
          if closing and s.meta.package and s.order and s.order.kind=='evade' and
            (t.kind=='fighter' or t.kind=='unknown') and distance<opt.defendRangeNm*NM then
            local defended=packages[s.meta.package]
            if not defended or distance<defended.distance then
              packages[s.meta.package]={distance=distance,asset=G.copy(p.point)}
            end
          end
        end
      end
      return best,asset,packages
    end
    local function assign(side)
      local reserved,targets={},{}
      for _,s in pairs(api.states) do
        if s.order and s.order.kind=='intercept' then
          reserved[s.order.data.reservation or ('group:'..tostring(s.order.data.groupId))]=true
        end
      end
      for _,t in ipairs(tracks[side]) do
        local priority,asset,packages=targetPriority(t,side)
        if priority and not reserved[reservation(t)] then
          targets[#targets+1]={track=t,priority=priority,asset=asset,packages=packages}
        end
      end
      table.sort(targets,function(a,b)
        if a.priority==b.priority then return a.track.key<b.track.key end
        return a.priority>b.priority
      end)
      for _,candidate in ipairs(targets) do
        local t=candidate.track
        if not reserved[reservation(t)] then
          local best,bestDistance,bestAim,bestDefense
          for name,s in pairs(api.states) do
            local p=samples[name]
            local patrol=s.meta.mode=='cap' and s.index>=s.meta.stationStart and s.index<s.meta.recoveryIndex
            local returning=returningFighter(s)
            local defense=packageDefender(s) and candidate.packages[s.meta.package] or nil
            local onAvoidance=patrol and s.order and s.order.kind=='samAvoid'
            if s.meta.side==side and (patrol or returning or defense) and (not s.order or onAvoidance) and now>=s.cooldown and
              available(s,p) and p.ammo then
              local centre=anchor(s,p)
              local d=G.distance(p.point,t.point)
              local seconds=math.min(60,d/math.max(100,p.speed))
              local aim={x=t.point.x+t.velocity.x*seconds,y=t.point.y,z=t.point.z+t.velocity.z*seconds}
              local maxRange=s.meta.burnPerMeter and opt.interceptRangeNm*NM or 30*NM
              local reserve=s.meta.bingo+0.08+(s.meta.burnPerMeter or 0)*
                (d+(returning and G.distance(aim,home(s)) or d))
              local reason
              if d>=maxRange then reason='contact outside intercept range'
              elseif p.fuel<=reserve then reason='insufficient fuel for intercept and return'
              elseif G.distance(t.point,centre)>=opt.patrolLeashNm*NM or
                G.distance(aim,centre)>=opt.patrolLeashNm*NM then reason='contact beyond patrol leash'
              elseif patrol and now+d/math.max(100,p.speed)+120>=s.meta.endTime then reason='insufficient station time'
              elseif not G.safe(p.point,t.point,t.kind=='missile' and p.point.y or math.min(p.point.y,t.point.y),
                flightThreats(s),io.height,12000) or
                not G.safe(p.point,aim,t.kind=='missile' and p.point.y or math.min(p.point.y,aim.y),
                  flightThreats(s),io.height,12000) then
                reason='known SAM or terrain blocks intercept corridor'
              end
              if reason then diagnose(s,'intercept rejected',reason)
              elseif not best or (defense and not bestDefense) or
                ((defense~=nil)==(bestDefense~=nil) and
                  (d<bestDistance or (d==bestDistance and name<best.meta.group))) then
                best,bestDistance,bestAim,bestDefense=s,d,aim,defense
              end
            end
          end
          if best then
            local asset=bestDefense and bestDefense.asset or candidate.asset
            if push(best,'intercept',{key=t.key,groupId=t.groupId,reservation=reservation(t),
              missile=t.kind=='missile',point=t.kind=='missile' and bestAim or nil,
              packageDefense=bestDefense~=nil,
              anchor=anchor(best,samples[best.meta.group]),asset=asset,
              nearest=G.distance(t.point,asset),reason='intercept detected '..t.kind..' threat'},900) then
              reserved[reservation(t)]=true
            end
          end
        end
      end
    end
    function api:tick()
      if not self.active then return end
      now=io.time()
      for side=1,2 do
        authority[side]=not self.paused[side] and io.authority(side)
        tracks[side]=authority[side] and io.contacts(side) or {}
        threats[side]=io.threats(side)
      end
      for name,s in pairs(self.states) do samples[name]=io.sample(s.meta) end
      for name,s in pairs(self.states) do service(s,samples[name]) end
      for side=1,2 do if authority[side] then assign(side) end end
    end
    return api
  end
end
