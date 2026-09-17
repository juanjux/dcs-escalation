from dcs.point import MovingPoint

from .pydcswaypointbuilder import PydcsWaypointBuilder


class AirAssaultIngressBuilder(PydcsWaypointBuilder):
    def add_tasks(self, waypoint: MovingPoint) -> None:
        self.register_special_ingress_points()
