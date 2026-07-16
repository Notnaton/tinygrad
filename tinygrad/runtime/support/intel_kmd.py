from __future__ import annotations
import os, pathlib
from dataclasses import dataclass
from tinygrad.runtime.autogen import xe_drm
from tinygrad.runtime.support.hcq import FileIOInterface
from tinygrad.runtime.support.intel import (INTEL_VENDOR_ID, XeConfig, XeEngine, XeMemoryRegion, make_query,
                                            parse_query_config, parse_query_engines, parse_query_mem_regions)

@dataclass(frozen=True)
class XeRenderNode:
  path: str
  sysfs_path: str
  device_id: int
  driver: str

def discover_xe_render_nodes(sysfs_root:str="/sys/class/drm", dev_root:str="/dev/dri") -> tuple[XeRenderNode, ...]:
  nodes = []
  for entry in sorted(pathlib.Path(sysfs_root).glob("renderD*")):
    device = entry / "device"
    try:
      vendor, device_id = int((device / "vendor").read_text().strip(), 0), int((device / "device").read_text().strip(), 0)
      driver = (device / "driver").resolve(strict=True).name
    except (FileNotFoundError, OSError, ValueError): continue
    node = pathlib.Path(dev_root) / entry.name
    if vendor == INTEL_VENDOR_ID and driver == "xe" and (node.exists() or dev_root != "/dev/dri"):
      nodes.append(XeRenderNode(str(node), str(entry), device_id, driver))
  return tuple(nodes)

class XeKmdDevice:
  """Small read-only wrapper around the stable DRM Xe query UAPI."""
  def __init__(self, node:XeRenderNode, io:FileIOInterface|None=None):
    if node.driver != "xe": raise ValueError(f"Intel render node uses {node.driver!r}, not 'xe'")
    self.node, self.io = node, io or FileIOInterface(node.path, os.O_RDWR)

  def query(self, query_id:int) -> bytes:
    request, _ = make_query(query_id)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_DEVICE_QUERY, request)
    if request.size <= 0: raise RuntimeError(f"Xe query {query_id} returned invalid size {request.size}")
    request, storage = make_query(query_id, request.size)
    allocated = request.size
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_DEVICE_QUERY, request)
    if request.size > allocated: raise RuntimeError(f"Xe query {query_id} grew from {allocated} to {request.size} bytes")
    if storage is None: raise RuntimeError("Xe query allocation failed")
    return storage.raw[:request.size]

  def config(self) -> XeConfig: return parse_query_config(self.query(xe_drm.DRM_XE_DEVICE_QUERY_CONFIG))
  def engines(self) -> tuple[XeEngine, ...]: return parse_query_engines(self.query(xe_drm.DRM_XE_DEVICE_QUERY_ENGINES))
  def memory_regions(self) -> tuple[XeMemoryRegion, ...]: return parse_query_mem_regions(self.query(xe_drm.DRM_XE_DEVICE_QUERY_MEM_REGIONS))
