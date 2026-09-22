# Requires German Military Assets for DCS by Currenthill:
# https://www.currenthill.com/germany
#


from dcs import unittype

from game.modsupport import shipmod, vehiclemod


# Armour
@vehiclemod
class CH_Leopard2A7V(unittype.VehicleType):
    id = "CH_Leopard2A7V"
    name = "[CH] Leopard 2A7V MBT"
    detection_range = 0
    threat_range = 8000
    air_weapon_dist = 8000
    eplrs = True


@vehiclemod
class CH_Marder1A5(unittype.VehicleType):
    id = "CH_Marder1A5"
    name = "[CH] Marder 1A5 IFV"
    detection_range = 6000
    threat_range = 3000
    air_weapon_dist = 3000
    eplrs = True


@vehiclemod
class CH_PumaA1(unittype.VehicleType):
    id = "CH_PumaA1"
    name = "[CH] Puma A1 IFV"
    detection_range = 0
    threat_range = 3000
    air_weapon_dist = 3000
    eplrs = True


@vehiclemod
class CH_Boxer(unittype.VehicleType):
    id = "CH_Boxer"
    name = "[CH] Boxer AFV"
    detection_range = 0
    threat_range = 1800
    air_weapon_dist = 1800
    eplrs = True


@vehiclemod
class CH_BoxerCRV(unittype.VehicleType):
    id = "CH_BoxerCRV"
    name = "[CH] Boxer IFV"
    detection_range = 0
    threat_range = 3000
    air_weapon_dist = 3000
    eplrs = True


@vehiclemod
class CH_Wiesel1A4(unittype.VehicleType):
    id = "CH_Wiesel1A4"
    name = "[CH] Wiesel 1A4 AWC"
    detection_range = 6000
    threat_range = 3000
    air_weapon_dist = 3000
    eplrs = True


@vehiclemod
class CH_EagleIV(unittype.VehicleType):
    id = "CH_EagleIV"
    name = "[CH] Eagle IV MRAP"
    detection_range = 0
    threat_range = 1800
    air_weapon_dist = 1800
    eplrs = True


# Artillery
@vehiclemod
class CH_PZH2000_M1711(unittype.VehicleType):
    id = "CH_PZH2000_M1711"
    name = "[CH] PzH 2000 SPG M1711"
    detection_range = 0
    threat_range = 40000
    air_weapon_dist = 0
    eplrs = True


@vehiclemod
class CH_PZH2000_M982(unittype.VehicleType):
    id = "CH_PZH2000_M982"
    name = "[CH] PzH 2000 SPG M982 Excalibur"
    detection_range = 0
    threat_range = 50000
    air_weapon_dist = 0
    eplrs = True


# Air defence
@vehiclemod
class CH_BoxerSkyranger(unittype.VehicleType):
    id = "CH_BoxerSkyranger"
    name = "[CH] Boxer SPAAGM"
    detection_range = 20000
    threat_range = 8000
    air_weapon_dist = 8000
    eplrs = True


@vehiclemod
class CH_FlaRakRad(unittype.VehicleType):
    id = "CH_FlaRakRad"
    name = "[CH] FlaRakRad SHORAD"
    detection_range = 18500
    threat_range = 8000
    air_weapon_dist = 8000
    eplrs = True


@vehiclemod
class CH_Wiesel2Ozelot(unittype.VehicleType):
    id = "CH_Wiesel2Ozelot"
    name = "[CH] Wiesel 2 Ozelot VSHORAD"
    detection_range = 20000
    threat_range = 8000
    air_weapon_dist = 8000
    eplrs = True


@vehiclemod
class CH_SkynexHX(unittype.VehicleType):
    id = "CH_SkynexHX"
    name = "[CH] Skynex HX SPAAG"
    detection_range = 50000
    threat_range = 3500
    air_weapon_dist = 3500
    eplrs = True


@vehiclemod
class CH_Skyshield_FCU(unittype.VehicleType):
    id = "CH_Skyshield_FCU"
    name = "[CH] Skyshield C-RAM STR"
    detection_range = 20000
    threat_range = 0
    air_weapon_dist = 0
    eplrs = True


@vehiclemod
class CH_Skyshield_Gun(unittype.VehicleType):
    id = "CH_Skyshield_Gun"
    name = "[CH] Skyshield C-RAM Gun"
    detection_range = 0
    threat_range = 3500
    air_weapon_dist = 3500
    eplrs = True


# The Patriot KAT1 battery, which the mod moved here from the USA pack in 1.5.0.
@vehiclemod
class CH_MIM104_M901_PAC2_KAT1(unittype.VehicleType):
    id = "CH_MIM104_M901_PAC2_KAT1"
    name = "[CH] MIM-104 M901 PAC-2 GEM LN (KAT1)"
    detection_range = 0
    threat_range = 150000
    air_weapon_dist = 150000
    eplrs = True


@vehiclemod
class CH_MIM104_ANMPQ53_KAT1(unittype.VehicleType):
    id = "CH_MIM104_ANMPQ53_KAT1"
    name = "[CH] MIM-104 AN/MPQ-53 STR (KAT1)"
    detection_range = 160000
    threat_range = 0
    air_weapon_dist = 0
    eplrs = True


@vehiclemod
class CH_MIM104_ECS_KAT1(unittype.VehicleType):
    id = "CH_MIM104_ECS_KAT1"
    name = "[CH] MIM-104 ECS (HX)"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0
    eplrs = True


@vehiclemod
class CH_MIM104_EPP_KAT1(unittype.VehicleType):
    id = "CH_MIM104_EPP_KAT1"
    name = "[CH] MIM-104 EPP (HX)"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0
    eplrs = True


# Logistics
@vehiclemod
class CH_HX60(unittype.VehicleType):
    id = "CH_HX60"
    name = "[CH] HX60 Truck"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


@vehiclemod
class CH_HX77(unittype.VehicleType):
    id = "CH_HX77"
    name = "[CH] HX77 Truck"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


@vehiclemod
class CH_HX81(unittype.VehicleType):
    id = "CH_HX81"
    name = "[CH] HX81 Tank Transporter"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


@vehiclemod
class CH_HX81_Tractor(unittype.VehicleType):
    id = "CH_HX81_Tractor"
    name = "[CH] HX81 Tractor"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


@vehiclemod
class CH_Zetros6x6(unittype.VehicleType):
    id = "CH_Zetros6x6"
    name = "[CH] Zetros 6x6 Truck"
    detection_range = 0
    threat_range = 0
    air_weapon_dist = 0


# Ships
@shipmod
class CH_F124(unittype.ShipType):
    id = "CH_F124"
    name = "[CH] F124 Sachsen Frigate"
    helicopter_num = 2
    parking = 2
    detection_range = 400000
    threat_range = 160000
    air_weapon_dist = 160000
