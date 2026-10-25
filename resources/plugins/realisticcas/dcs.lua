-- Explicit opt-in adapter. No automatic map-wide scan or task changes.
-- Load core.lua first, then call RealisticCAS.start with an OWNERSHIP allowlist.
assert(RealisticCAS and RealisticCAS.new,"Realistic CAS core must load first")

do
  function RealisticCAS.validateContactReports(c)
    assert(c.contactReports==nil or type(c.contactReports)=='boolean','invalid contact reports option')
    local seconds=c.contactReportSeconds
    if seconds==nil then seconds=15 end
    assert(type(seconds)=='number' and seconds==math.floor(seconds) and seconds>=1 and seconds<=300,
      'invalid contact report duration')
  end
  function RealisticCAS.contactCoordinates(p,format)
    local lat,lon=coord.LOtoLL(p)
    if format==2 then
      local m=coord.LLtoMGRS(lat,lon)
      return string.format('%s %s %05d %05d',m.UTMZone,m.MGRSDigraph,math.floor(m.Easting),math.floor(m.Northing))
    end
    local function angle(value,positive,negative)
      local scale=format==1 and 3600 or 60000
      local total=math.floor(math.abs(value)*scale+0.5)
      local degrees=math.floor(total/scale)
      local remainder=total-degrees*scale
      local hemisphere=value>=0 and positive or negative
      if format==1 then return string.format('%s %02d %02d %02d',hemisphere,degrees,math.floor(remainder/60),remainder%60)end
      return string.format('%s %02d %06.3f',hemisphere,degrees,remainder/1000)
    end
    return angle(lat,'N','S')..' '..angle(lon,'E','W')
  end
  function RealisticCAS.start(options)
    local o=options or {}
    if o.enabled~=true then return nil,"disabled" end
    if RealisticCAS._running then return nil,"already running" end
    assert(type(o.targets)=="table","explicit targets allowlist required")
    RealisticCAS.validateContactReports(o)
    assert(o.onFire==nil or type(o.onFire)=='function','onFire callback must be a function')
    local interval=o.interval or 1
    local budget=o.expiryBudget or 128
    assert(type(interval)=="number" and interval>=0.1 and interval<=60,"invalid interval")
    assert(type(budget)=="number" and budget>=1 and budget<=4096 and budget==math.floor(budget),"invalid budget")
    local allowed,managed={},{}
    -- Validate the whole allowlist before changing mission state.
    for _,entry in ipairs(o.targets) do
      assert(type(entry)=="table","target entry must be a table")
      assert(type(entry.name)=="string" and entry.name~="","target name required")
      assert(entry.originalInvisible==false,"visibility ownership must be explicitly confirmed")
      assert(not allowed[entry.name],"duplicate target name")
      allowed[entry.name]=true
    end
    local function log(kind,id,detail)
      if o.debug or kind=="BACKEND_ERROR" or kind=="ADAPTER_ERROR" or kind=="CONTACT_REPORT_ERROR" or kind=="WARNING" then
        env.info("REALISTIC_CAS|"..kind.."|t="..tostring(timer.getTime())..
          "|group="..tostring(id).."|"..tostring(detail))
      end
    end
    local function report(kind,contact)
      local side=contact.owner==1 and 2 or 1
      local action=kind=='EXPIRE' and 'Enemy contact forgotten: ' or
        (contact.reason=='fire' and 'Enemy contact revealed by firing: ' or 'Enemy contact discovered: ')
      local observer=contact.reason and contact.reason:match('^[^:]+:(.+)$')
      if kind=='REVEAL' and observer and (o.afacObservers or {})[observer]then
        local ok,label=pcall(function()return Unit.getByName(observer):getCallsign()end)
        action='JTAC '..(ok and type(label)=='string' and label~='' and label or observer)..' found '
      end
      local text=action..RealisticCAS.contactDescription(contact)..' at '..
        RealisticCAS.contactCoordinates(contact.lastPosition,o.contactCoordinateFormat)..'.'
      trigger.action.outTextForCoalition(side,text,o.contactReportSeconds or 15)
      env.info('REALISTIC_CAS_CONTACT|side='..side..'|'..text)
    end
    local service=RealisticCAS.new({enabled=true,ttl=o.ttl,clock=timer.getTime,
      retryInterval=o.retryInterval,log=log,onContact=o.contactReports==true and report or nil,
      setVisible=function(id,visible)
        local item=managed[id]
        if not item then return false end
        local g=Group.getByName(item.name)
        if not g or not g:isExist() then return true end -- No surviving group to conceal/restore.
        if g:getID()~=id then return false end -- Never mutate a replacement with a reused name.
        if g:getCoalition()~=item.owner then return false end
        g:getController():setCommand({id="SetInvisible",params={value=not visible}})
        return true -- Acceptance by DCS API, not independently observable engine visibility.
      end})
    local adapter={service=service,active=true}
    local function register(g)
      if not g or not g:isExist() or not allowed[g:getName()] then return false end
      if g:getCategory()~=Group.Category.GROUND then return false end
      local id,name,side=g:getID(),g:getName(),g:getCoalition()
      if side~=1 and side~=2 then return false end
      if managed[id] then
        return managed[id].name==name and managed[id].owner==side and service:isRegistered(id)
      end
      -- Replace a stale incarnation without restoring or modifying the new object.
      for old,item in pairs(managed) do
        if item.name==name then service:unregister(old,false);managed[old]=nil end
      end
      managed[id]={name=name,owner=side}
      local ok,why=service:register(id,side)
      if not ok then managed[id]=nil;log("ADAPTER_ERROR",id,why) end
      return ok
    end
    function adapter:observe(groupName,coalition,point,reason,typeName)
      if not self.active or self.stopping then return false,"stopped" end
      local g=Group.getByName(groupName)
      if not g or not g:isExist() then return false,"unmanaged group" end
      local item=managed[g:getID()]
      if not item or item.name~=groupName or item.owner~=g:getCoalition() then return false,"unmanaged group" end
      return service:observe(g:getID(),coalition,point,reason,typeName)
    end
    local handler={}
    function handler:onEvent(event)
      if not adapter.active or adapter.stopping or not event or not event.initiator then return end
      local relevant=event.id==world.event.S_EVENT_SHOT or
        (world.event.S_EVENT_SHOOTING_START and event.id==world.event.S_EVENT_SHOOTING_START) or
        event.id==world.event.S_EVENT_BIRTH
      if not relevant then return end
      local ok,err=pcall(function()
        local u=event.initiator
        if not u:isExist() or u:getCoalition()==0 then return end
        local g=u:getGroup()
        if not g or not allowed[g:getName()] then return end
        if not register(g) then return end
        if event.id~=world.event.S_EVENT_BIRTH then
          local p=u:getPoint()
          local typed,typeName=pcall(function()return u:getTypeName()end)
          local revealed=service:fire(g:getID(),p,typed and typeName or nil)
          if revealed and o.onFire then o.onFire(g:getName(),u:getName(),p)end
        end
      end)
      if not ok then log("ADAPTER_ERROR",nil,err) end
    end
    function adapter:stop()
      if not self.active then return true end
      self.stopping=true
      local restored=service:stop()
      for id in pairs(managed) do
        if not service:isRegistered(id) then managed[id]=nil end
      end
      if not restored then
        log("WARNING",nil,"stop incomplete: retry stop to restore remaining groups")
        return false
      end
      self.active=false
      world.removeEventHandler(handler)
      RealisticCAS._running=nil
      return true
    end
    local function update(_,now)
      if not adapter.active then return nil end
      if adapter.stopping then return now+interval end
      local ok,err=pcall(function() service:tick(budget) end)
      if not ok then log("ADAPTER_ERROR",nil,err) end
      return now+interval
    end
    -- Install infrastructure before hiding anything. Failed startup must not leave
    -- invisible groups without a running timer/handler or a handle to restore them.
    local installed,installError=pcall(function()
      world.addEventHandler(handler)
      timer.scheduleFunction(update,nil,timer.getTime()+interval)
    end)
    if not installed then
      adapter.active=false
      pcall(world.removeEventHandler,handler)
      error(installError)
    end
    RealisticCAS._running=adapter
    for name in pairs(allowed) do
      local ok,result=pcall(function() return register(Group.getByName(name)) end)
      if not ok then log("ADAPTER_ERROR",name,result) end
    end
    log("START",nil,"prototype; explicit targets only; TTL="..service:getDiagnostics().ttl)
    if not world.event.S_EVENT_SHOOTING_START then log("WARNING",nil,"gunfire start event unavailable") end
    return adapter
  end
end
