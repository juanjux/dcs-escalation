from dcs.unittype import ShipType

from game.modsupport import shipmod


# Pack 3.3.0 also ships an "L61SP" hull. It is the same ship with an alarm-state
# animation added for single player, so it is deliberately not declared here: a second
# Juan Carlos I in every ship list buys nothing.
@shipmod
class L61(ShipType):
    id = "L61"
    name = "L61 Juan Carlos I"
    plane_num = 40
    helicopter_num = 36
    parking = 4
    detection_range = 300000
    # carries no weapon system at all -- a threat ring here is a lie
    threat_range = 0
    air_weapon_dist = 0


@shipmod
class F100(ShipType):
    id = "F100"
    name = "F100 Álvaro de Bazán"
    helicopter_num = 1
    parking = 1
    detection_range = 160000
    # MK41 with SM-2MR; the mod shipped 45 km for the one hull that has area SAMs
    threat_range = 150000
    air_weapon_dist = 150000


@shipmod
class F105(ShipType):
    id = "F105"
    name = "F105 Cristobal Colon"
    helicopter_num = 1
    parking = 1
    detection_range = 160000
    # as the F100, plus two Phalanx
    threat_range = 150000
    air_weapon_dist = 150000


@shipmod
class L52(ShipType):
    id = "L52"
    name = "L52 Castilla"
    helicopter_num = 2
    parking = 2
    detection_range = 300000
    # two Phalanx and nothing else, so a CIWS bubble
    threat_range = 3000
    air_weapon_dist = 3000


@shipmod
class L02(ShipType):
    id = "L02"
    name = "L02 Canberra"
    plane_num = 40
    helicopter_num = 36
    parking = 4
    detection_range = 300000
    # Canberra, same class as the L61 and likewise unarmed
    threat_range = 0
    air_weapon_dist = 0


@shipmod
class DDG39(ShipType):
    id = "DDG39"
    name = "HMAS HOBART DDG39"
    helicopter_num = 1
    parking = 1
    detection_range = 160000
    # Hobart is the same Aegis/SM-2 design and had the same 45 km
    threat_range = 150000
    air_weapon_dist = 150000
