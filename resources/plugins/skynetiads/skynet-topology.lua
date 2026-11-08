-- Fixed power feeds and one effective radio uplink per site. Radio standby
-- candidates are range-checked by the generator, not invented during combat.
EscalationIadsTopology = {}
EscalationIadsTopology.__index = EscalationIadsTopology

function EscalationIadsTopology:create(iads, data, coalition)
    local topology = setmetatable({
        iads=iads, coalition=coalition, rows={}, ordered={}, roots={}, sources={}, localPower={}, staticMembers={},
    }, self)
    for _, role in ipairs({'Sam', 'SamAsEwr', 'Ewr', 'CommandCenter', 'ConnectionNode', 'PowerSource'}) do
        for _, row in ipairs(data[role] or {}) do
            topology.rows[row.dcsGroupName] = {role=role, data=row}
            table.insert(topology.ordered, row.dcsGroupName)
            for _, generator in ipairs(row.localPowerSources or {}) do
                topology.localPower[generator] = true
            end
            for _, member in ipairs(row.staticMembers or {}) do
                topology.staticMembers[member] = true
            end
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
                    radioCandidates=owner.radioCandidates, topologyKey=owner.topologyKey,
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
    if row.data.staticMembers then
        for _, member in ipairs(row.data.staticMembers) do
            local object = StaticObject.getByName(member .. ' object')
            if object then
                local ok, live = pcall(function()
                    return object:isExist() and object:getLife() > 0
                        and object:getCoalition() == self.coalition
                end)
                if ok and live then return true end
            end
        end
        return false
    end
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

function EscalationIadsTopology:generatorAlive(name)
    local object = Unit.getByName(name)
    if not object then return false end
    local ok, live = pcall(function()
        return object:isExist() and object:getLife() > 0
            and object:getCoalition() == self.coalition
    end)
    return ok and live
end

local function radioRole(row)
    return row and (row.role == 'ConnectionNode' or row.role == 'CommandCenter')
end

function EscalationIadsTopology:selectRadio(alive, powered)
    local parents, adjacency, edges, seen = {}, {}, {}, {}
    local function key(name) return self.rows[name].data.topologyKey or name end
    local function available(name) return alive[name] and powered[name] end
    local function root(name)
        while parents[name] ~= name do
            parents[name] = parents[parents[name]]
            name = parents[name]
        end
        return name
    end
    for _, name in ipairs(self.ordered) do
        local row = self.rows[name]
        if radioRole(row) and row.data.radioCandidates ~= nil and available(name) then
            parents[name], adjacency[name] = name, {}
        end
    end
    for _, name in ipairs(self.ordered) do
        if parents[name] then
            for _, candidate in ipairs(self.rows[name].data.radioCandidates) do
                local other = candidate.name
                if parents[other] and other ~= name then
                    local low, high = name, other
                    if key(low) > key(high) then low, high = high, low end
                    seen[low] = seen[low] or {}
                    if not seen[low][high] then
                        seen[low][high] = true
                        edges[#edges+1] = {low=low, high=high, distance=candidate.distance}
                    end
                end
            end
        end
    end
    table.sort(edges, function(a, b)
        if a.distance ~= b.distance then return a.distance < b.distance end
        if key(a.high) ~= key(b.high) then return key(a.high) < key(b.high) end
        return key(a.low) < key(b.low)
    end)
    for _, edge in ipairs(edges) do
        local a, b = root(edge.low), root(edge.high)
        if a ~= b then
            parents[b] = a
            table.insert(adjacency[edge.low], edge.high)
            table.insert(adjacency[edge.high], edge.low)
        end
    end
    local components = {}
    for _, name in ipairs(self.ordered) do
        if parents[name] then
            local component = root(name)
            components[component] = components[component] or {}
            table.insert(components[component], name)
        end
    end
    self.radioParents, self.routerRoots = {}, {}
    for _, members in pairs(components) do
        table.sort(members, function(a, b) return key(a) < key(b) end)
        local command, commands = nil, {}
        for _, name in ipairs(members) do
            if self.rows[name].role == 'CommandCenter' then
                command = command or name
                commands[name] = true
            end
        end
        local first = command or members[1]
        local visited, pending = {[first]=true}, {first}
        while #pending > 0 do
            local current = table.remove(pending)
            self.routerRoots[current] = commands
            table.sort(adjacency[current], function(a, b) return key(a) < key(b) end)
            for _, neighbor in ipairs(adjacency[current]) do
                if not visited[neighbor] then
                    visited[neighbor] = true
                    self.radioParents[neighbor] = current
                    pending[#pending+1] = neighbor
                end
            end
        end
    end
    for _, name in ipairs(self.ordered) do
        local row = self.rows[name]
        if row.data.radioCandidates ~= nil and not radioRole(row)
            and not row.data.powerOnly and available(name) then
            for _, candidate in ipairs(row.data.radioCandidates) do
                if next(self.routerRoots[candidate.name] or {}) then
                    self.radioParents[name] = candidate.name
                    break
                end
            end
        end
    end
end

function EscalationIadsTopology:refresh()
    local alive, powered, signature = {}, {}, {}
    for _, name in ipairs(self.ordered) do alive[name] = self:alive(name) end
    for _, name in ipairs(self.ordered) do
        local row = self.rows[name]
        local power = row.data.PowerSource or {}
        powered[name] = row.role == 'PowerSource' or (not row.data.requiresPower and #power == 0)
        for _, source in ipairs(power) do
            if alive[source] then powered[name] = true; break end
        end
        for _, generator in ipairs(row.data.localPowerSources or {}) do
            if self:generatorAlive(generator) then powered[name] = true; break end
        end
        signature[#signature+1] = (alive[name] and powered[name]) and '1' or '0'
    end
    signature = table.concat(signature)
    if signature == self.signature then return false end
    self.signature, self.aliveNodes, self.powered = signature, alive, powered
    self:selectRadio(alive, powered)
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
                        if row.data.radioCandidates ~= nil then
                            local parent = self.radioParents[current]
                            local roots = self.routerRoots[current] or self.routerRoots[parent] or {}
                            for command in pairs(roots) do reached[command] = true end
                        else
                            if row.role == 'CommandCenter' then reached[current] = true end
                            for _, role in ipairs({'CommandCenter', 'ConnectionNode'}) do
                                for _, neighbor in ipairs(row.data[role] or {}) do
                                    local target = self.rows[neighbor]
                                    if radioRole(target) then pending[#pending+1] = neighbor end
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
    if row.data.powerOnly then return self.aliveNodes[name] and self.powered[name] end
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

function EscalationIadsTopology:staticDestroyed(element)
    local name = self:elementName(element)
    local row = self.rows[name]
    if row and row.data.staticMembers then return not self:alive(name) end
    return nil
end

function EscalationIadsTopology:canExchange(left, right)
    if not self:connected(left) or not self:connected(right) then return false end
    local a, b = self:elementName(left), self:elementName(right)
    if (self.rows[a] and self.rows[a].data.powerOnly)
        or (self.rows[b] and self.rows[b].data.powerOnly) then return false end
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
            if self.rows[name] or self.rows[string.gsub(name, ' object$', '')]
                or self.staticMembers[string.gsub(name, ' object$', '')]
                or self.localPower[name] then return true end
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
