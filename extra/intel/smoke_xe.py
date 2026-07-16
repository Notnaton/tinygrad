#!/usr/bin/env python3
"""Explicitly submit one MI_BATCH_BUFFER_END batch through the experimental DRM Xe interface."""
from __future__ import annotations
import argparse, json, pathlib, sys, types
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tinygrad.runtime.ops_intel import XEKMDIface  # noqa: E402
from tinygrad.runtime.support.intel_va import IntelVAAllocator  # noqa: E402
from tinygrad.runtime.support.intel_xe2 import Xe2CommandBuffer  # noqa: E402
from tinygrad.runtime.support.intel_kmd import discover_xe_render_nodes  # noqa: E402

def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--index", type=int, default=0, help="index within discovered Intel Xe render nodes")
  parser.add_argument("--submit-noop", action="store_true", help="confirm VM/queue creation, allocation, and no-op GPU submission")
  args = parser.parse_args()
  if not args.submit_noop: parser.error("refusing to submit without the explicit --submit-noop flag; use query_xe.py for a read-only probe")
  nodes = discover_xe_render_nodes()
  dev = types.SimpleNamespace(va_allocator=IntelVAAllocator(48, 0x1000))
  iface = XEKMDIface(dev, args.index, nodes=nodes)
  dev.iface = iface
  try:
    iface.submit(Xe2CommandBuffer().end().to_bytes())
    result = {"status":"no-op batch completed", "node":asdict(iface.node), "config":asdict(iface.config),
              "engine":asdict(iface.compute_engine), "memory_region":asdict(iface.memory_region), "alignment":iface.alignment}
  finally: iface.device_fini()
  print(json.dumps(result, indent=2, sort_keys=True))
  return 0

if __name__ == "__main__":
  try: raise SystemExit(main())
  except (IndexError, OSError, RuntimeError, ValueError) as error:
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(2) from None
