-- F10 reads the existing contact service; it never queries live unit positions.
assert(RealisticCAS, 'load Realistic CAS core first')

do
  local function finite(n) return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge end
  local function integer(n) return finite(n) and n>0 and n==math.floor(n) end
  local function point(p) return type(p)=='table' and finite(p.x) and finite(p.y) and finite(p.z) end
  local function copy(p) return {x=p.x,y=p.y,z=p.z} end

  function RealisticCAS.validateF10Contacts(groups,managed)
    assert(type(groups)=='table','explicit F10 frontline groups required')
    local ids,names={},{}
    for _,g in ipairs(groups)do
      assert(type(g)=='table' and integer(g.id) and not ids[g.id], 'invalid F10 group ID')
      assert(type(g.name)=='string' and g.name~='' and not names[g.name], 'invalid F10 group name')
      assert(g.coalition==1 and (not managed or managed[g.name]), 'F10 group must be a managed RED frontline group')
      ids[g.id]=true;names[g.name]=true
    end
  end

  function RealisticCAS.newF10Contacts(options)
    local o=options
    RealisticCAS.validateF10Contacts(o.groups)
    for _,name in ipairs({'readContact','allocateMarkId','setMark','removeMark'})do
      assert(type(o[name])=='function',name..' callback required')
    end
    local cursor,active,drawn,owned,pending=1,true,{},{},{}
    local stats={reads=0,created=0,removed=0,errors=0}
    local api={}
    local function call(name,...)
      local ok,result=pcall(o[name],...)
      if not ok or result==false then
        stats.errors=stats.errors+1
        if o.log then pcall(o.log,name..': '..tostring(result))end
        return false
      end
      return true,result
    end
    local function retire(id)
      if not owned[id] then return true end
      if not call('removeMark',id) then pending[id]=true;return false end
      owned[id]=nil;pending[id]=nil;stats.removed=stats.removed+1
      return true
    end
    function api:tick(budget)
      if not active then return 0 end
      budget=budget or 64
      assert(integer(budget) and budget<=4096, 'invalid F10 work budget')
      local retries=0
      for id in pairs(pending)do
        retire(id);retries=retries+1
        if retries>=budget then break end
      end
      local work=math.min(budget,#o.groups)
      for _=1,work do
        local g=o.groups[cursor];cursor=cursor%#o.groups+1
        stats.reads=stats.reads+1
        local ok,c=call('readContact',g.id,2)
        if ok then
          if type(c)=='table' and c.owner==g.coalition and c.revealed==true and point(c.lastPosition) then
            local p,old=c.lastPosition,drawn[g.id]
            local label='Frontline contact: '..RealisticCAS.contactDescription(c)
            -- Renewals at the same position need no native marker replacement.
            if not next(pending) and (not old or old.label~=label or old.point.x~=p.x or old.point.y~=p.y or old.point.z~=p.z) then
              local allocated,id=call('allocateMarkId')
              if allocated and integer(id) then
                local observed=copy(p)
                owned[id]=true
                if call('setMark',id,2,copy(observed),label) then
                  stats.created=stats.created+1
                  if old then retire(old.markId)end
                  drawn[g.id]={markId=id,point=observed,label=label}
                else retire(id)end
              end
            end
          elseif drawn[g.id]then
            retire(drawn[g.id].markId);drawn[g.id]=nil
          end
        end
      end
      return work
    end
    function api:stop()
      active=false
      for id in pairs(owned)do retire(id)end
      drawn={}
      return next(owned)==nil
    end
    function api:diagnostics()
      local result={}
      for k,v in pairs(stats)do result[k]=v end
      return result
    end
    return api
  end

  function RealisticCAS.startF10Contacts(fog,options)
    local o=options
    RealisticCAS.validateF10Contacts(o.groups)
    local api={active=true}
    local layer,handler
    function api:stop()
      self.active=false
      if handler then world.removeEventHandler(handler);handler=nil end
      return not layer or layer:stop()
    end
    if #o.groups==0 then return api end
    for _,name in ipairs({'markToCoalition','removeMark'})do
      assert(type(trigger.action[name])=='function','F10 API unavailable: '..name)
    end
    assert(type(world.getMarkPanels)=='function','F10 mark inventory unavailable')
    local limit=2147483646
    local function reserve(id)
      if integer(id) and id<=limit then
        RealisticCAS._f10MarkSerial=math.max(RealisticCAS._f10MarkSerial or 100000000,id)
      end
    end
    reserve(RealisticCAS._f10MarkSerial or 100000000)
    for _,m in pairs(world.getMarkPanels() or {})do reserve(m.idx)end
    handler={}
    function handler:onEvent(event)
      if event and world.event.S_EVENT_MARK_ADDED and event.id==world.event.S_EVENT_MARK_ADDED then reserve(event.idx)end
    end
    local nextLog=0
    layer=RealisticCAS.newF10Contacts({groups=o.groups,
      readContact=function(id,side)return fog.service:getContact(id,side)end,
      allocateMarkId=function()
        local id=RealisticCAS._f10MarkSerial+1
        assert(id<=limit,'F10 marker ID space exhausted')
        RealisticCAS._f10MarkSerial=id
        return id
      end,
      setMark=function(id,side,p,label)
        trigger.action.markToCoalition(id,label,p,side,true)
        return true
      end,
      removeMark=function(id)trigger.action.removeMark(id);return true end,
      log=function(detail)
        local now=timer.getTime()
        if o.log and now>=nextLog then nextLog=now+30;pcall(o.log,detail)end
      end})
    local ok,err=pcall(function()
      world.addEventHandler(handler)
      timer.scheduleFunction(function(_,now)
        if not api.active then return nil end
        local worked,why=pcall(function()layer:tick(64)end)
        if not worked and o.log then pcall(o.log,tostring(why))end
        return now+0.5
      end,nil,timer.getTime()+0.5)
    end)
    if not ok then api:stop();error(err)end
    return api
  end
end
