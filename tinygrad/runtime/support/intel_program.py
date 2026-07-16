from __future__ import annotations
import json, struct
from dataclasses import asdict, dataclass
from typing import Any
from tinygrad.runtime.support.elf import elf_sections

INTEL_PROGRAM_MAGIC = b"TGXE2\x00\x01\x00"

@dataclass(frozen=True)
class IntelKernelArg:
  arg_type: str
  offset: int
  size: int
  arg_index: int = -1
  addrmode: str = ""
  addrspace: str = ""
  access_type: str = ""

  def __post_init__(self):
    if self.offset < 0: raise ValueError(f"invalid Intel kernel argument offset: {self.offset}")
    # IGC emits zero-sized records for stateful arguments paired with a stateless/bindless payload record.
    if self.size < 0: raise ValueError(f"invalid Intel kernel argument size: {self.size}")
    if self.arg_index < -1: raise ValueError(f"invalid Intel kernel argument index: {self.arg_index}")

@dataclass(frozen=True)
class IntelKernelMetadata:
  name: str
  simd_size: int
  grf_count: int
  slm_size: int = 0
  barrier_count: int = 0
  inline_data_payload_size: int = 0
  private_size: int = 0
  spill_size: int = 0
  actual_kernel_start_offset: int = 0
  required_work_group_size: tuple[int, int, int] = (0, 0, 0)
  has_dpas: bool = False
  payload_arguments: tuple[IntelKernelArg, ...] = ()
  per_thread_payload_size: int = 0

  def __post_init__(self):
    if self.simd_size not in (8, 16, 32): raise ValueError(f"unsupported Intel SIMD size: {self.simd_size}")
    if self.grf_count <= 0: raise ValueError(f"invalid Intel GRF count: {self.grf_count}")
    if min(self.slm_size, self.barrier_count, self.inline_data_payload_size, self.private_size, self.spill_size,
           self.actual_kernel_start_offset, self.per_thread_payload_size) < 0: raise ValueError("Intel kernel metadata values cannot be negative")
    if len(self.required_work_group_size) != 3 or min(self.required_work_group_size) < 0:
      raise ValueError("invalid Intel required work-group size")

  @property
  def cross_thread_data_size(self) -> int:
    return max((arg.offset + arg.size for arg in self.payload_arguments if arg.offset >= 0 and arg.size > 0), default=0)

  @property
  def large_grf(self) -> bool: return self.grf_count > 128

@dataclass(frozen=True)
class IntelProgramImage:
  metadata: IntelKernelMetadata
  code: bytes

  def __post_init__(self):
    if not self.code: raise ValueError("Intel program image has no kernel code")
    if self.metadata.actual_kernel_start_offset >= len(self.code): raise ValueError("Intel kernel start offset is outside its code")
    if self.metadata.actual_kernel_start_offset & 0x3F: raise ValueError("Intel kernel start offset must be 64-byte aligned")

  def encode(self) -> bytes:
    metadata = json.dumps(asdict(self.metadata), sort_keys=True, separators=(",", ":")).encode()
    return struct.pack("<8sII", INTEL_PROGRAM_MAGIC, len(metadata), len(self.code)) + metadata + self.code

  @staticmethod
  def decode(blob:bytes) -> IntelProgramImage:
    if len(blob) < 16: raise ValueError("truncated Intel program container")
    magic, metadata_size, code_size = struct.unpack_from("<8sII", blob)
    if magic != INTEL_PROGRAM_MAGIC: raise ValueError("invalid Intel program container magic")
    if len(blob) != 16 + metadata_size + code_size: raise ValueError("invalid Intel program container length")
    raw = json.loads(blob[16:16+metadata_size])
    raw["required_work_group_size"] = tuple(raw.get("required_work_group_size", (0, 0, 0)))
    raw["payload_arguments"] = tuple(IntelKernelArg(**arg) for arg in raw.get("payload_arguments", ()))
    return IntelProgramImage(IntelKernelMetadata(**raw), blob[16+metadata_size:])

def _scalar(value:str) -> Any:
  value = value.strip()
  if not value: return ""
  if value[0:1] in ('"', "'") and value[-1:] == value[0]: return value[1:-1]
  if value.lower() in ("true", "false"): return value.lower() == "true"
  if value.startswith("[") and value.endswith("]"): return [_scalar(x) for x in value[1:-1].split(",") if x.strip()]
  try: return int(value, 0)
  except ValueError: return value

def _key_value(value:str) -> tuple[str, Any]:
  if ":" not in value: raise ValueError(f"invalid .ze_info entry: {value!r}")
  key, val = value.split(":", 1)
  return key.strip(), _scalar(val)

def parse_ze_info(text:str) -> tuple[IntelKernelMetadata, ...]:
  """Parse the strict IGC Zebin kernel metadata subset used by tinygrad."""
  kernels:list[dict[str, Any]] = []
  in_kernels, kernel_indent, section, section_indent, current_arg = False, -1, "", -1, None
  for lineno, raw_line in enumerate(text.splitlines(), 1):
    line = raw_line.split("#", 1)[0].rstrip()
    if not line or line.lstrip() in ("---", "..."): continue
    indent, value = len(line)-len(line.lstrip(" ")), line.strip()
    if indent == 0:
      key = value.split(":", 1)[0].strip()
      if key == "kernels": in_kernels = True
      elif in_kernels: break
      continue
    if not in_kernels: continue

    if value.startswith("- name"):
      name_key, name = _key_value(value[2:].strip())
      if name_key != "name" or not isinstance(name, str): raise ValueError(f"invalid .ze_info kernel name at line {lineno}")
      kernels.append({"name":name, "execution_env":{}, "user_attributes":{}, "payload_arguments":[], "per_thread_payload_arguments":[]})
      kernel_indent, section, current_arg = indent, "", None
      continue
    if not kernels or indent <= kernel_indent: continue

    if value.endswith(":") and not value.startswith("-"):
      section, section_indent, current_arg = value[:-1].strip(), indent, None
      continue
    if section in ("payload_arguments", "per_thread_payload_arguments") and value.startswith("-"):
      current_arg = {}
      kernels[-1][section].append(current_arg)
      key, val = _key_value(value[1:].strip())
      current_arg[key] = val
      continue
    key, val = _key_value(value)
    if section in ("execution_env", "user_attributes") and indent > section_indent: kernels[-1][section][key] = val
    elif section in ("payload_arguments", "per_thread_payload_arguments") and current_arg is not None: current_arg[key] = val

  decoded = []
  for kernel in kernels:
    env = kernel["execution_env"]
    missing = [key for key in ("simd_size", "grf_count") if key not in env]
    if missing: raise ValueError(f"Intel kernel {kernel['name']!r} is missing {', '.join(missing)}")
    args = tuple(IntelKernelArg(arg_type=str(arg.get("arg_type", "")), offset=int(arg.get("offset", -1)), size=int(arg.get("size", 0)),
                                arg_index=int(arg.get("arg_index", -1)), addrmode=str(arg.get("addrmode", "")),
                                addrspace=str(arg.get("addrspace", "")), access_type=str(arg.get("access_type", "")))
                 for arg in kernel["payload_arguments"])
    per_thread_size = max((int(arg.get("offset", 0)) + int(arg.get("size", 0)) for arg in kernel["per_thread_payload_arguments"]), default=0)
    reqd = kernel["user_attributes"].get("reqd_work_group_size", env.get("required_work_group_size", (0, 0, 0)))
    if not isinstance(reqd, list) or len(reqd) != 3: reqd = (0, 0, 0)
    decoded.append(IntelKernelMetadata(name=kernel["name"], simd_size=int(env["simd_size"]), grf_count=int(env["grf_count"]),
      slm_size=int(env.get("slm_size", 0)), barrier_count=int(env.get("barrier_count", 0)),
      inline_data_payload_size=int(env.get("inline_data_payload_size", 0)), private_size=int(env.get("private_size", 0)),
      spill_size=int(env.get("spill_size", 0)), actual_kernel_start_offset=int(env.get("actual_kernel_start_offset", 0)),
      required_work_group_size=tuple(int(x) for x in reqd), has_dpas=bool(env.get("has_dpas", False)), payload_arguments=args,
      per_thread_payload_size=per_thread_size))
  if not decoded: raise ValueError(".ze_info contains no kernels")
  return tuple(decoded)

def load_zebin(blob:bytes, kernel_name:str) -> IntelProgramImage:
  sections = elf_sections(blob)
  ze_info = next((section.content for section in sections if section.name == ".ze_info"), None)
  if ze_info is None: raise ValueError("Zebin has no .ze_info section")
  metadata = next((meta for meta in parse_ze_info(ze_info.rstrip(b'\0').decode()) if meta.name == kernel_name), None)
  if metadata is None: raise ValueError(f"Zebin has no metadata for kernel {kernel_name!r}")
  code = next((section.content for section in sections if section.name == f".text.{kernel_name}"), None)
  if code is None: raise ValueError(f"Zebin has no .text.{kernel_name} section")
  if metadata.actual_kernel_start_offset >= len(code): raise ValueError("Intel kernel start offset is outside its text section")
  return IntelProgramImage(metadata, code)
