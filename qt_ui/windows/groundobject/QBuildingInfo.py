import os
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout

from game.config import REWARDS
from game.theater import TheaterUnit
from qt_ui.widgets.coordinatelabel import CoordinateLabel


class QBuildingInfo(QGroupBox):
    def __init__(
        self,
        building: TheaterUnit,
        ground_object,
        on_repair: Callable[[TheaterUnit, float], None],
        settings: Any = None,
    ):
        super(QBuildingInfo, self).__init__()
        self.building = building
        self.ground_object = ground_object
        self.on_repair = on_repair
        self.settings = settings
        self.init_ui()

    def init_ui(self):
        icon_path = os.path.join(
            "./resources/ui/units/buildings/" + self.building.icon + ".png"
        )
        # SceneryUnit.icon is always "missing", so a missing icon means there is
        # no real picture: skip the header instead of showing the cyan "Missing
        # Recon Picture" placeholder, leaving a compact name + value card.
        has_real_icon = self.building.icon != "missing" and os.path.isfile(icon_path)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        if not self.building.alive:
            header = QLabel()
            header.setPixmap(QPixmap("./resources/ui/units/buildings/dead.png"))
            layout.addWidget(header)
        elif has_real_icon:
            header = QLabel()
            header.setPixmap(QPixmap(icon_path))
            layout.addWidget(header)

        name_label = QLabel(self.building.short_name)
        name_label.setProperty("style", "small")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        layout.addWidget(CoordinateLabel(self.building.position, self.settings))

        if self.ground_object.category in REWARDS:
            income_label_text = (
                "Value: " + str(REWARDS[self.ground_object.category]) + "M"
            )
            if not self.building.alive:
                income_label_text = "<s>" + income_label_text + "</s>"
            self.reward = QLabel(income_label_text)
            layout.addWidget(self.reward)

        if not self.building.alive:
            if self.building.repair_turns_remaining is not None:
                layout.addWidget(
                    QLabel(
                        "Repairing (" f"{self.building.repair_turns_remaining} turns)"
                    )
                )
            elif self.ground_object.control_point.captured.is_blue:
                price = self.ground_object.repair_cost()
                if price > 0:
                    repair = QPushButton(f"Repair [{price}M]")
                    repair.setProperty("style", "btn-success")
                    repair.clicked.connect(
                        lambda checked=False, u=self.building, p=price: self.on_repair(
                            u, p
                        )
                    )
                    layout.addWidget(repair)
            else:
                layout.addWidget(QLabel("Destroyed"))

        self.setLayout(layout)
