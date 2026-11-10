-- Share genuine observations with generated ground AI without replacing tasks.
-- Loading is inert; the mission bootstrap owns the lifetime and timer.
assert(RealisticCAS and RealisticCAS.new, 'load Realistic CAS core first')
do
  function RealisticCAS.newGroundIntel(fog, observers, targets, options)
    local o=options or {}
    local budget=o.budget or 128
    local refresh=o.refreshSeconds or 15
    assert(type(budget)=='number' and budget>=1 and budget<=4096 and budget==math.floor(budget), 'invalid intel budget')
    assert(type(refresh)=='number' and refresh>=1, 'invalid intel refresh interval')
    local receivers={[1]={},[2]={}}
    local receiverNames,allowed,records={},{},{}
    for _,meta in ipairs(observers)do
      if meta.category=='ground' and receivers[meta.coalition] and not receiverNames[meta.name]then
        receivers[meta.coalition][#receivers[meta.coalition]+1]=meta.name
        receiverNames[meta.name]=true
      end
    end
    for _,meta in ipairs(targets)do allowed[meta.name]=meta end
    local head,tail
    local stats={queued=0,delivered=0,errors=0}
    local api={active=true}
    local function log(kind,detail)
      if o.log then o.log(kind,detail)end
    end
    local function append(job)
      job.next=nil
      if tail then tail.next=job else head=job end
      tail=job
    end
    local function target(job)
      if records[job.name]~=job then return nil end
      if not fog.active or fog.stopping or not fog.service:isRevealed(job.groupId,job.side)then return nil end
      local u=Unit.getByName(job.name)
      if not u or not u:isExist() or u:getLife()<=0 or u:getID()~=job.unitId then return nil end
      local g=u:getGroup()
      if not g or not g:isExist() or g:getID()~=job.groupId or g:getName()~=job.groupName
        or g:getCoalition()~=job.owner or g:getCategory()~=Group.Category.GROUND then return nil end
      return u
    end
    function api:observe(name,side,contact)
      if not self.active or not name or not contact or not contact.revealed then return false end
      local meta=allowed[name]
      if not meta or meta.coalition==side or contact.owner~=meta.coalition
        or not receivers[side] or #receivers[side]==0 then return false end
      local u=Unit.getByName(name)
      if not u or not u:isExist() or u:getLife()<=0 then return false end
      local g=u:getGroup()
      if not g or not g:isExist() or g:getName()~=meta.groupName or g:getID()~=contact.id
        or g:getCoalition()~=meta.coalition then return false end
      local previous=records[name]
      local now=timer.getTime()
      if previous and previous.unitId==u:getID() and previous.groupId==contact.id
        and previous.discoveredAt==contact.discoveredAt then
        -- Renewals do not restart a wave: the last receiver must not starve.
        previous.observedAt=contact.observedAt
        if previous.pending or now-(previous.completedAt or -math.huge)<refresh then return true end
      end
      local job={name=name,unitId=u:getID(),groupName=meta.groupName,groupId=contact.id,
        side=side,owner=meta.coalition,cursor=1,pending=true,
        observedAt=contact.observedAt,discoveredAt=contact.discoveredAt}
      records[name]=job;append(job);stats.queued=stats.queued+1
      log('QUEUE',name..'|side='..side)
      return true
    end
    function api:tick()
      if not self.active or not fog.active or fog.stopping then return 0 end
      local processed=0
      while head and processed<budget do
        local job=head;head=job.next
        if not head then tail=nil end
        job.next=nil;processed=processed+1
        local keep=false
        local ok,err=pcall(function()
          local enemy=target(job)
          if not enemy then return end
          local names=receivers[job.side]
          local name=names[job.cursor];job.cursor=job.cursor+1
          keep=job.cursor<=#names
          local u=Unit.getByName(name)
          if not u or not u:isExist() or u:getLife()<=0 or u:getCoalition()~=job.side then return end
          local g=u:getGroup()
          if not g or not g:isExist() or g:getCategory()~=Group.Category.GROUND then return end
          local controller=u:getController()
          if not controller then return end
          controller:knowTarget(enemy,true,true)
          stats.delivered=stats.delivered+1
          log('SHARE',job.name..'|receiver='..name..'|observedAt='..tostring(job.observedAt))
        end)
        if not ok then
          stats.errors=stats.errors+1
          -- Report the first error, without flooding a mission on repeated failures.
          if stats.errors==1 then log('ERROR',tostring(err))end
        end
        if keep then append(job)
        else job.pending=false;job.completedAt=timer.getTime();stats.queued=stats.queued-1 end
      end
      return processed
    end
    function api:getDiagnostics()
      return {queued=stats.queued,delivered=stats.delivered,errors=stats.errors,budget=budget}
    end
    function api:stop()
      self.active=false;head=nil;tail=nil;records={};stats.queued=0
    end
    return api
  end
end
