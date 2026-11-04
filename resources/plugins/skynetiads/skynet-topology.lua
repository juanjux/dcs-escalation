-- Operational paths through the turn's generated topology. No proximity links
-- are invented in DCS; infrastructure losses only remove usable paths.
EscalationIadsTopology = {}
EscalationIadsTopology.__index = EscalationIadsTopology

function EscalationIadsTopology:create(iads, data, coalition)
    local topology = setmetatable({
        iads=iads, coalition=coalition, rows={}, ordered={}, roots={}, sources={},
    }, self)
    for _, role in ipairs({'Sam', 'SamAsEwr', 'Ewr', 'CommandCenter', 'ConnectionNode', 'PowerSource'}) do
        for _, row in ipairs(data[role] or {}) do
            topology.rows[row.dcsGroupName] = {role=role, data=row}
            table.insert(topology.ordered, row.dcsGroupName)
        end
    end
    -- Point defences use their site's radio links, not an airborne-radio fallback.
    -- They retain their native independent power supply.
    for _, name in ipairs(topology.ordered) do
        local owner = topology.rows[name].data
        for _, defence in ipairs(owner.PD or {}) do
            if not topology.rows[defence] then
                topology.rows[defence] = {role='PD', data={
                    dcsGroupName=defence, CommandCenter=owner.CommandCenter,
                    ConnectionNode=owner.ConnectionNode, independentComms=owner.independentComms,
                }}
                table.insert(topology.ordered, defence)
            end
        end
    end
    topology:refresh()
    return topology
end

function EscalationIadsTopology:alive(name)
    local row = self.rows[name]
    if not row then return false end
    local object
    if row.role == 'CommandCenter' or row.role == 'ConnectionNode' or row.role == 'PowerSource' then
        object = StaticObject.getByName(name .. ' object')
    elseif row.role == 'Ewr' then
        object = Unit.getByName(name)
    else
        object = Group.getByName(name)
    end
    if not object then return false end
    local ok, live = pcall(function()
        if not object:isExist() then return false end
        if object.getCoalition and object:getCoalition() ~= self.coalition then return false end
        if object.getUnits then
            for _, unit in ipairs(object:getUnits()) do
                if unit:isExist() and unit:getLife() > 0 then return true end
            end
            return false
        end
        return object:getLife() > 0
    end)
    return ok and live
end

function EscalationIadsTopology:refresh()
    local alive, powered, signature = {}, {}, {}
    for _, name in ipairs(self.ordered) do alive[name] = self:alive(name) end
    for _, name in ipairs(self.ordered) do
        local row = self.rows[name]
        local power = row.data.PowerSource or {}
        powered[name] = row.role == 'PowerSource' or #power == 0
        for _, source in ipairs(power) do
            if alive[source] then powered[name] = true; break end
        end
        signature[#signature+1] = (alive[name] and powered[name]) and '1' or '0'
    end
    signature = table.concat(signature)
    if signature == self.signature then return false end
    self.signature, self.aliveNodes, self.powered = signature, alive, powered
    self.roots = {}
    for _, name in ipairs(self.ordered) do
        local reached, visited, pending = {}, {}, {name}
        if self.rows[name].data.independentComms then
            pending = {}
            for _, candidate in ipairs(self.ordered) do
                if self.rows[candidate].role == 'CommandCenter' then
                    pending[#pending+1] = candidate
                end
            end
        end
        if alive[name] and powered[name] then
            while #pending > 0 do
                local current = table.remove(pending)
                if not visited[current] then
                    visited[current] = true
                    local row = self.rows[current]
                    if row and alive[current] and powered[current] then
                        if row.role == 'CommandCenter' then reached[current] = true end
                        for _, role in ipairs({'CommandCenter', 'ConnectionNode'}) do
                            for _, neighbor in ipairs(row.data[role] or {}) do
                                local target = self.rows[neighbor]
                                if target and (target.role == 'CommandCenter' or target.role == 'ConnectionNode') then
                                    pending[#pending+1] = neighbor
                                end
                            end
                        end
                    end
                end
            end
        end
        self.roots[name] = reached
    end
    return true
end

function EscalationIadsTopology:elementName(element)
    local name = element:getDCSName()
    if self.rows[name] then return name end
    -- pydcs appends this suffix to the static object's actual DCS name.
    local staticName = string.gsub(name, ' object$', '')
    if self.rows[staticName] and self.rows[staticName].role == 'CommandCenter' then
        return staticName
    end
    return name
end

function EscalationIadsTopology:connected(element)
    local name = self:elementName(element)
    local row = self.rows[name]
    -- AWACS retain their native independent radio connectivity.
    if not row then return element:genericCheckOneObjectIsAlive(element:getConnectionNodes()) end
    if next(self.roots[name] or {}) then return true end
    if row.data.independentComms and self.aliveNodes[name] and self.powered[name] then
        for _, candidate in ipairs(self.ordered) do
            if self.rows[candidate].role == 'CommandCenter' then return false end
        end
        return true
    end
    return false
end

function EscalationIadsTopology:hasPower(element)
    local name = self:elementName(element)
    if not self.rows[name] then return nil end
    return self.powered[name] == true
end

function EscalationIadsTopology:canExchange(left, right)
    if not self:connected(left) or not self:connected(right) then return false end
    local a, b = self:elementName(left), self:elementName(right)
    if not self.rows[a] or not self.rows[b] then return true end -- Airborne radio.
    if self.rows[a].data.independentComms or self.rows[b].data.independentComms then return true end
    for command in pairs(self.roots[a] or {}) do
        if (self.roots[b] or {})[command] then return true end
    end
    return false
end

function EscalationIadsTopology:beginCycle()
    self.sources = {}
    self:updateState()
end

function EscalationIadsTopology:updateState()
    if self:refresh() then
        -- Remote relay losses are not necessarily a direct Skynet dependency.
        -- Re-evaluate autonomy when the graph changes, not every contact pair.
        for _, element in ipairs(self.iads:getAbstracRadarElements()) do
            element:setToCorrectAutonomousState()
        end
    end
end

function EscalationIadsTopology:onEvent(event)
    local object = event.initiator
    if object then
        local ok, relevant = pcall(function()
            local name = object:getName()
            if self.rows[name] or self.rows[string.gsub(name, ' object$', '')] then return true end
            if object.getGroup then
                local group = object:getGroup()
                return group and self.rows[group:getName()] ~= nil
            end
            return false
        end)
        -- Unrelated ground losses must not rescan the entire IADS.
        if not ok or not relevant then return end
    end
    self:updateState()
end

function EscalationIadsTopology:noteContact(contact, source)
    local name = contact:getName()
    self.sources[name] = self.sources[name] or {}
    self.sources[name][source] = true
end

function EscalationIadsTopology:canReceive(receiver, contact)
    for source in pairs(self.sources[contact:getName()] or {}) do
        if source == receiver or self:canExchange(source, receiver) then return true end
    end
    return false
end
