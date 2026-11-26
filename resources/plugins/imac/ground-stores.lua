-- DCS inventory categories shared by mission scripts. Unknown stores yield nil.
EscalationGroundStores = {}
function EscalationGroundStores.isGroundWeapon(desc)
    local categories = Weapon and Weapon.Category
    local missiles = Weapon and Weapon.MissileCategory
    if missiles and desc.missileCategory ~= nil then
        return desc.missileCategory ~= missiles.AAM and desc.missileCategory ~= missiles.SAM
    end
    if categories and desc.category ~= nil and desc.category ~= categories.MISSILE then
        return desc.category == categories.BOMB or desc.category == categories.ROCKET
    end
end
