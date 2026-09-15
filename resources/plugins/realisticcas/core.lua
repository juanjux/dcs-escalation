-- Realistic CAS contact state. Pure Lua 5.1: no DCS/MIST/MOOSE dependencies.
-- Loading this file has no mission side effects. Visibility ownership is explicit.
RealisticCAS = RealisticCAS or {}
RealisticCAS.version = "0.1.0-prototype"

do
  local function finite(n)
    return type(n)=="number" and n==n and n~=math.huge and n~=-math.huge
  end
  local function position(p)
    if type(p)~="table" or not finite(p.x) or not finite(p.y) or not finite(p.z) then return nil end
    return {x=p.x,y=p.y,z=p.z}
  end
  local function enemy(side) return side==1 and 2 or 1 end

  function RealisticCAS.new(options)
    local o=options or {}
    local ttl=o.ttl or 600
    local retry=o.retryInterval or 5
    assert(finite(ttl) and ttl>0,"ttl must be positive seconds")
    assert(finite(retry) and retry>0,"retryInterval must be positive seconds")
    assert(type(o.clock)=="function","clock is required")
    assert(type(o.setVisible)=="function","setVisible callback is required")
    local enabled=o.enabled==true
    local records,heap,index={},{},{}
    local counters={registered=0,reveals=0,renewals=0,expirations=0,backendErrors=0}
    local api={}
    local function emit(kind,r,detail)
      if o.log then pcall(o.log,kind,r and r.id or nil,detail) end
    end
    local function swap(a,b)
      heap[a],heap[b]=heap[b],heap[a]
      index[heap[a].id],index[heap[b].id]=a,b
    end
    local function up(i)
      while i>1 do
        local p=math.floor(i/2)
        if heap[p].due<=heap[i].due then break end
        swap(i,p);i=p
      end
      return i
    end
    local function down(i)
      while 2*i<=#heap do
        local c=2*i
        if c<#heap and heap[c+1].due<heap[c].due then c=c+1 end
        if heap[i].due<=heap[c].due then break end
        swap(i,c);i=c
      end
    end
    local function remove(id)
      local i=index[id]
      if not i then return end
      index[id]=nil
      local last=table.remove(heap)
      if i<=#heap then
        heap[i]=last;index[last.id]=i
        down(up(i))
      end
    end
    local function schedule(id,due)
      local i=index[id]
      if i then heap[i].due=due;down(up(i))
      else heap[#heap+1]={id=id,due=due};index[id]=#heap;up(#heap) end
    end
    local function apply(r,visible)
      local ok,result=pcall(o.setVisible,r.id,visible)
      if not ok or result~=true then
        counters.backendErrors=counters.backendErrors+1
        emit("BACKEND_ERROR",r,tostring(result))
        return false
      end
      r.backendVisible=visible
      return true
    end
    local function currentTime()
      local t=o.clock()
      assert(finite(t),"clock must return finite seconds")
      return t
    end

    function api:register(id,owner)
      if not enabled then return false,"disabled" end
      if id=="" or (type(id)~="string" and type(id)~="number") or (type(id)=="number" and not finite(id)) then
        return false,"invalid id"
      end
      if owner~=1 and owner~=2 then return false,"unsupported coalition" end
      if records[id] then return false,"already registered" end
      local r={id=id,owner=owner,backendVisible=true}
      if not apply(r,false) then return false,"hide failed" end
      records[id]=r
      counters.registered=counters.registered+1
      emit("REGISTER",r,owner)
      return true
    end

    function api:observe(id,observingCoalition,point,reason)
      if not enabled then return false,"disabled" end
      local r=records[id]
      if not r then return false,"unknown group" end
      if observingCoalition~=enemy(r.owner) then return false,"not opposing coalition" end
      local p=position(point)
      if not p then return false,"invalid observed position" end
      if reason~=nil and (type(reason)~="string" or reason=="") then return false,"invalid reason" end
      local t=currentTime()
      local fresh=r.expiresAt and t<r.expiresAt
      if not r.backendVisible and not apply(r,true) then return false,"reveal failed" end
      r.lastPosition=p;r.observedAt=t;r.expiresAt=t+ttl;r.reason=reason or "observation"
      schedule(id,r.expiresAt)
      if fresh then counters.renewals=counters.renewals+1 else counters.reveals=counters.reveals+1 end
      emit(fresh and "RENEW" or "REVEAL",r,r.reason)
      return true
    end

    function api:fire(id,point)
      local r=records[id]
      if not r then return false,"unknown group" end
      return self:observe(id,enemy(r.owner),point,"fire")
    end

    function api:isRevealed(id,coalition)
      local r=records[id]
      return enabled and r~=nil and coalition==enemy(r.owner) and
        r.expiresAt~=nil and currentTime()<r.expiresAt and r.backendVisible==true
    end

    function api:getContact(id,coalition)
      local r=records[id]
      if not r or coalition~=enemy(r.owner) or not r.observedAt then return nil end
      -- Copies only: reading/sharing a contact never renews it or follows its object.
      return {id=r.id,owner=r.owner,observedAt=r.observedAt,expiresAt=r.expiresAt,
        lastPosition=position(r.lastPosition),reason=r.reason,
        revealed=self:isRevealed(id,coalition),backendVisible=r.backendVisible}
    end

    function api:tick(budget)
      budget=budget or 128
      assert(finite(budget) and budget>=1 and budget==math.floor(budget),"invalid budget")
      local now=currentTime()
      local processed=0
      while enabled and heap[1] and heap[1].due<=now and processed<budget do
        local id=heap[1].id
        remove(id);processed=processed+1
        local r=records[id]
        if r and r.backendVisible then
          if apply(r,false) then
            counters.expirations=counters.expirations+1
            emit("EXPIRE",r,now)
          else
            -- Logical contact remains expired. Do not claim physical concealment.
            schedule(id,now+retry)
          end
        end
      end
      return processed
    end

    function api:unregister(id,restore)
      local r=records[id]
      if not r then return false,"unknown group" end
      if restore and not r.backendVisible and not apply(r,true) then return false,"restore failed" end
      remove(id);records[id]=nil
      counters.registered=counters.registered-1
      emit("UNREGISTER",r,restore==true)
      return true
    end

    function api:stop()
      -- Caller retries if restoration failed; never silently abandon hidden groups.
      local ids={}
      for id in pairs(records) do ids[#ids+1]=id end
      local success=true
      for _,id in ipairs(ids) do if not self:unregister(id,true) then success=false end end
      if success then enabled=false end
      return success
    end

    function api:isRegistered(id) return records[id]~=nil end

    function api:getDiagnostics()
      local result={enabled=enabled,scheduled=#heap,ttl=ttl}
      for k,v in pairs(counters) do result[k]=v end
      return result
    end
    return api
  end
end
