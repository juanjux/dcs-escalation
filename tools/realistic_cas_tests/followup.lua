-- Event/acquisition-driven second-stage experiments, no campaign behavior.
RCAS_EXPERIMENT_FACTORY=function(ctx)
  local c=ctx.cfg.experiment
  local e={state="WAIT_POSITIVE_CONTROL",done=false,postShots=0,preShots=0}
  local function now() return timer.getTime()-ctx.started end
  local function dist(a,b) return math.sqrt((a.x-b.x)^2+(a.z-b.z)^2) end
  local function detector(target)
    local observer=assert(ctx.unit(c.observer),"observer absent")
    return {observer:getGroup():getController():isTargetDetected(assert(ctx.unit(target),target.." absent"))}
  end
  local function los(target)
    local p=ctx.unit(c.observer):getPoint()
    local q=ctx.unit(target):getPoint()
    return land.isVisible({x=p.x,y=p.y+2,z=p.z},{x=q.x,y=q.y+2,z=q.z})
  end
  local function command(scope,target,value)
    ctx.act({op="invisible",scope=scope,target=target,value=value})
  end
  function e:setState(s)
    self.state=s
    ctx.act({op="phase",label=s})
    ctx.log("EXPERIMENT_PHASE|t="..now().."|"..s)
  end
  function e:finish(s)
    self.done=true
    self:setState(s)
  end
  function e:missiles()
    local count=0
    for _,name in ipairs(c.shooters or {}) do
      local u=ctx.unit(name)
      if u then
        for _,a in ipairs(u:getAmmo() or {}) do
          if string.find(a.desc.typeName or "", "X_29T",1,true) then count=count+a.count end
        end
      end
    end
    return count
  end
  function e:onEvent(event,source,weapon)
    if self.done or c.kind~="air" or event.id~=world.event.S_EVENT_SHOT then return end
    local ours=false
    for _,n in ipairs(c.shooters) do if source==n then ours=true end end
    if not ours or not string.find(weapon,"X_29T",1,true) then return end
    if self.changed then self.postShots=self.postShots+1 else self.preShots=self.preShots+1 end
    ctx.log("QUALIFYING_SHOT|t="..now().."|source="..source.."|state="..self.state)
    if not self.firstShot then self.firstShot=now() end
  end
  function e:tick(t)
    if c.kind=="air" then
      if c.variant=="always_hidden" then
        if self.state=="WAIT_POSITIVE_CONTROL" then self:setState("SIEMPRE OCULTO; comparar control") end
        if self.firstShot then self:finish("RESULTADO: LANZO CONTRA OCULTO")
        elseif t>=720 then self:finish("FIN: sin lanzamiento; comparar control visible") end
        return
      end
      if not self.firstShot then
        if t>=480 then self:finish("INVALID: sin primer Kh-29T en 480s") end
        return
      end
      if not self.changed then
        self.remaining=self:missiles()
        if self.remaining<1 then self:finish("INVALID: sin Kh-29T restante al cambiar fase"); return end
        self.changed=t
        if c.variant=="revoke" then command("group",c.targetGroup,true) end
        self:setState(c.variant=="revoke" and "OCULTO tras primer misil" or "CONTROL: sigue VISIBLE")
        ctx.log("REVOCATION_GATE|t="..t.."|firstShot="..self.firstShot.."|remaining="..self.remaining)
      end
      if t-self.changed>=240 and not self.restored then
        self.hiddenWindowShots=self.postShots
        self.restored=t
        if c.variant=="revoke" then command("group",c.targetGroup,false) end
        self:setState("VISIBLE otra vez; sin reemitir tarea")
      end
      if self.restored and t-self.restored>=180 then self:finish("FIN MEDICION; comparar control/variante") end
      return
    end
    -- Ground experiments cannot advance until every subject is actually visible.
    if not self.acquired then
      local all=true
      for _,target in ipairs(c.targets) do
        local r=detector(target)
        if not (r[1] and r[2] and los(target)) then all=false end
      end
      if all then
        self.stable=self.stable or t
        if t-self.stable>=10 then
          self.acquired=t
          self:setState("CONTROL POSITIVO: blancos adquiridos")
        end
      else self.stable=nil end
      if t>=240 and not self.acquired then self:finish("INVALID: no adquirio todos con LOS en 240s") end
      return
    end
    local since=t-self.acquired
    if since>=15 and not self.changed then
      self.changed=t
      if c.kind=="scope" then
        if c.variant=="unit" then command("unit",c.targets[1],true)
        elseif c.variant=="group" then command("group",c.targetGroup,true) end
        self:setState("OBSERVAR: "..c.variant.."; Abrams aun HOLD")
      else
        local p=ctx.unit(c.targets[1]):getPoint()
        self.startPoint={x=p.x,y=p.y,z=p.z}
        ctx.act({op="snapshot",target=c.targets[1],id=9001})
        if c.variant=="hidden" then command("group",c.targetGroup,true) end
        self:setState("MEMORIA: "..c.variant.."; antes de mover")
      end
    end
    if not self.changed then return end
    local dt=t-self.changed
    if c.kind=="scope" then
      if dt>=30 and not self.opened then
        self.opened=t
        ctx.act({op="ground_roe",target=c.observerGroup,value="OPEN_FIRE"})
        self:setState("ABRAMS ABRE FUEGO; "..c.variant)
      end
      if dt>=180 and not self.restored then
        self.restored=t
        if c.variant=="unit" then command("unit",c.targets[1],false)
        elseif c.variant=="group" then command("group",c.targetGroup,false) end
        self:setState("TODOS VISIBLES: control final")
      end
      if dt>=300 then self:finish("FIN MEDICION: comparar deteccion y fuego por blanco") end
    else
      if dt>=10 and not self.moveAt then
        self.moveAt=t
        ctx.act({op="move",target=c.targetGroup,x=self.startPoint.x,
          z=self.startPoint.z+250,speed=5})
        self:setState("CAMION EN RUTA; "..c.variant)
      end
      if self.moveAt then
        self.moved=dist(ctx.unit(c.targets[1]):getPoint(),self.startPoint)
        if not los(c.targets[1]) then self.badLOS=true end
        if t-self.moveAt>=120 and self.moved<40 then
          self:finish("INVALID: camion no se desplazo 40m en 120s"); return
        end
      end
      if dt>=180 and not self.restored then
        self.restored=t
        if c.variant=="hidden" then command("group",c.targetGroup,false) end
        self:setState("CAMION VISIBLE: comprobar reacquisicion")
      end
      if dt>=260 then
        self:finish(self.badLOS and "INVALID COMPARACION: perdio LOS durante movimiento" or "FIN MEMORIA: comparar posiciones")
      end
    end
  end
  function e:lines(t)
    local out={"ESTADO: "..self.state}
    if c.kind=="air" then
      out[#out+1]="Kh-29T restantes="..self:missiles().." | primer tiro="..tostring(self.firstShot)
      out[#out+1]="Tiros antes cambio="..self.preShots.." | despues="..self.postShots..
        " | ventana prueba="..tostring(self.hiddenWindowShots or self.postShots)
      if self.changed then out[#out+1]="Desde cambio="..math.floor(t-self.changed).."s; restaurar +240s; FIN +420s" end
    else
      for _,name in ipairs(c.targets) do
        local u=ctx.unit(name)
        if u then
          local r=detector(name)
          out[#out+1]=name.." ("..u:getTypeName().."): det="..tostring(r[1]).." visible="..tostring(r[2]).." LOS="..tostring(los(name))
          if c.kind=="memory" then
            out[#out+1]="REAL x,y,z: "..ctx.position(u:getPoint())
            out[#out+1]="NATIVA lastPos: "..ctx.position(r[6]).." | lastTime="..tostring(r[5])
            out[#out+1]="Desplazamiento desde marca SCRIPT="..math.floor(self.moved or 0).."m"
          end
        end
      end
      if not self.acquired then out[#out+1]="Esperando 10s de contacto visible estable; timeout 240s" end
    end
    return out
  end
  ctx.log("RETURN_CONTRACT|1=detected|2=visible|3=knowType|4=knowDistance|5=lastTime|6=lastPos|7=lastVel")
  return e
end
