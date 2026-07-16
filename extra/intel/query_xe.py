#!/usr/bin/env python3
"""Read stable DRM Xe configuration, engine, and memory-region queries."""
from __future__ import annotations
import argparse, json, pathlib, sys
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tinygrad.runtime.support.intel_kmd import XeKmdDevice, discover_xe_render_nodes  # noqa: E402

def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--index", type=int, default=0, help="index within discovered Intel Xe render nodes")
  parser.add_argument("--sysfs-root", default="/sys/class/drm")
  parser.add_argument("--dev-root", default="/dev/dri")
  args = parser.parse_args()
  nodes = discover_xe_render_nodes(args.sysfs_root, args.dev_root)
  if not nodes: raise RuntimeError("no Intel render node bound to the Xe driver was found")
  if args.index < 0 or args.index >= len(nodes): raise RuntimeError(f"Xe node index {args.index} is out of range for {len(nodes)} nodes")
  device = XeKmdDevice(nodes[args.index])
  result = {"node":asdict(device.node), "config":asdict(device.config()),
            "engines":[asdict(engine) for engine in device.engines()],
            "memory_regions":[asdict(region) for region in device.memory_regions()]}
  print(json.dumps(result, indent=2, sort_keys=True))
  return 0

if __name__ == "__main__":
  try: raise SystemExit(main())
  except (OSError, RuntimeError, ValueError) as error:
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(2) from None
