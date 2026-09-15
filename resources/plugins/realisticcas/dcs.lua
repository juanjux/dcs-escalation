-- Explicit opt-in adapter. No automatic map-wide scan or task changes.
-- Load core.lua first, then call RealisticCAS.start with an OWNERSHIP allowlist.
assert(RealisticCAS and RealisticCAS.new,"Realistic CAS core must load first")

do
  function RealisticCAS.start(options)
    local o=options or {}
    if o.enabled~=true then return nil,"disabled" end
    if RealisticCAS._running then return nil,"already running" end
    assert(type(o.targets)=="table","explicit targets allowlist required")
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
      if o.debug or kind=="BACKEND_ERROR" or kind=="ADAPTER_ERROR" or kind=="WARNING" then
        env.info("REALISTIC_CAS|"..kind.."|t="..tostring(timer.getTime())..
          "|group="..tostring(id).."|"..tostring(detail))
      end
    end
    local service=RealisticCAS.new({enabled=true,ttl=o.ttl,clock=timer.getTime,
      retryInterval=o.retryInterval,log=log,setVisible=function(id,visible)
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
    function adapter:observe(groupName,coalition,point,reason)
      if not self.active or self.stopping then return false,"stopped" end
      local g=Group.getByName(groupName)
      if not g or not g:isExist() then return false,"unmanaged group" end
      local item=managed[g:getID()]
      if not item or item.name~=groupName or item.owner~=g:getCoalition() then return false,"unmanaged group" end
      return service:observe(g:getID(),coalition,point,reason)
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
        if event.id~=world.event.S_EVENT_BIRTH then service:fire(g:getID(),u:getPoint()) end
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
