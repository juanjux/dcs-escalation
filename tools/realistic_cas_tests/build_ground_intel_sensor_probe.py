"""Build the automatic V4 fog-isolation probe for native ground knowledge."""

import argparse
from pathlib import Path

from dcs import Mission

from build_ground_intel_controller_probe import build_mission

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing mission")
    build_mission(sensor_isolation=True).save(args.output)
    Mission().load_file(str(args.output))
    print(args.output)
