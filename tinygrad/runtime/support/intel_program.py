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
class IntelRelocation:
  symbol: str
  offset: int
  rel_type: int
  addend: int = 0

  def __post_init__(self):
    if self.offset < 0: raise ValueError("Intel relocation offset cannot be negative")
    if self.rel_type not in (1, 2, 3, 4, 7): raise ValueError(f"unsupported Intel relocation type {self.rel_type}")

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
  local_id_channels: int = 0
  offset_to_skip_per_thread_data_load: int = 0

  def __post_init__(self):
    if self.simd_size not in (8, 16, 32): raise ValueError(f"unsupported Intel SIMD size: {self.simd_size}")
    if self.grf_count <= 0: raise ValueError(f"invalid Intel GRF count: {self.grf_count}")
    if min(self.slm_size, self.barrier_count, self.inline_data_payload_size, self.private_size, self.spill_size,
           self.actual_kernel_start_offset, self.per_thread_payload_size, self.local_id_channels,
           self.offset_to_skip_per_thread_data_load) < 0: raise ValueError("Intel kernel metadata values cannot be negative")
    if self.local_id_channels > 3: raise ValueError("Intel kernels can request at most three local ID channels")
    if self.per_thread_payload_size != self.local_id_channels * 64:
      raise ValueError("Intel per-thread payload must contain one 64-byte GRF per local ID channel")
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
  relocations: tuple[IntelRelocation, ...] = ()

  def __post_init__(self):
    if not self.code: raise ValueError("Intel program image has no kernel code")
    if self.metadata.actual_kernel_start_offset >= len(self.code): raise ValueError("Intel kernel start offset is outside its code")
    if self.metadata.actual_kernel_start_offset & 0x3F: raise ValueError("Intel kernel start offset must be 64-byte aligned")
    skipped_start = self.metadata.actual_kernel_start_offset + self.metadata.offset_to_skip_per_thread_data_load
    if self.metadata.local_id_channels and skipped_start >= len(self.code): raise ValueError("Intel local-ID kernel start is outside its code")
    for reloc in self.relocations:
      if reloc.symbol != "__INTEL_PATCH_CROSS_THREAD_OFFSET_OFF_R0": raise ValueError(f"unsupported Intel relocation symbol {reloc.symbol!r}")
      if reloc.offset + (8 if reloc.rel_type == 1 else 4) > len(self.code): raise ValueError("Intel relocation is outside its code")

  def encode(self) -> bytes:
    raw = asdict(self.metadata)
    raw["relocations"] = [asdict(reloc) for reloc in self.relocations]
    metadata = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    return struct.pack("<8sII", INTEL_PROGRAM_MAGIC, len(metadata), len(self.code)) + metadata + self.code

  @staticmethod
  def decode(blob:bytes) -> IntelProgramImage:
    if len(blob) < 16: raise ValueError("truncated Intel program container")
    magic, metadata_size, code_size = struct.unpack_from("<8sII", blob)
    if magic != INTEL_PROGRAM_MAGIC: raise ValueError("invalid Intel program container magic")
    if len(blob) != 16 + metadata_size + code_size: raise ValueError("invalid Intel program container length")
    raw = json.loads(blob[16:16+metadata_size])
    relocations = tuple(IntelRelocation(**reloc) for reloc in raw.pop("relocations", ()))
    raw["required_work_group_size"] = tuple(raw.get("required_work_group_size", (0, 0, 0)))
    raw["payload_arguments"] = tuple(IntelKernelArg(**arg) for arg in raw.get("payload_arguments", ()))
    return IntelProgramImage(IntelKernelMetadata(**raw), blob[16+metadata_size:], relocations)

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
    per_thread_args = kernel["per_thread_payload_arguments"]
    unsupported_per_thread = [str(arg.get("arg_type", "")) for arg in per_thread_args if arg.get("arg_type") != "local_id"]
    if unsupported_per_thread: raise ValueError(f"unsupported Intel per-thread payload arguments: {', '.join(unsupported_per_thread)}")
    if any(int(arg.get("offset", 0)) != 0 for arg in per_thread_args): raise ValueError("unsupported Intel local ID payload offset")
    per_thread_size = max((int(arg.get("offset", 0)) + int(arg.get("size", 0)) for arg in per_thread_args), default=0)
    if per_thread_size % 64: raise ValueError("Intel local ID payload must occupy whole 64-byte GRFs")
    walk_order = kernel["user_attributes"].get("intel_reqd_workgroup_walk_order", [0, 1, 2])
    if walk_order != [0, 1, 2]: raise ValueError(f"unsupported Intel work-group walk order: {walk_order}")
    reqd = kernel["user_attributes"].get("reqd_work_group_size", env.get("required_work_group_size", (0, 0, 0)))
    if not isinstance(reqd, list) or len(reqd) != 3: reqd = (0, 0, 0)
    decoded.append(IntelKernelMetadata(name=kernel["name"], simd_size=int(env["simd_size"]), grf_count=int(env["grf_count"]),
      slm_size=int(env.get("slm_size", 0)), barrier_count=int(env.get("barrier_count", 0)),
      inline_data_payload_size=int(env.get("inline_data_payload_size", 0)), private_size=int(env.get("private_size", 0)),
      spill_size=int(env.get("spill_size", 0)), actual_kernel_start_offset=int(env.get("actual_kernel_start_offset", 0)),
      required_work_group_size=tuple(int(x) for x in reqd), has_dpas=bool(env.get("has_dpas", False)), payload_arguments=args,
      per_thread_payload_size=per_thread_size, local_id_channels=per_thread_size // 64,
      offset_to_skip_per_thread_data_load=int(env.get("offset_to_skip_per_thread_data_load", 0))))
  if not decoded: raise ValueError(".ze_info contains no kernels")
  return tuple(decoded)

def _zebin_relocations(sections, kernel_name:str) -> tuple[IntelRelocation, ...]:
  target_name = f".text.{kernel_name}"
  target_index = next((i for i, section in enumerate(sections) if section.name == target_name), None)
  if target_index is None: return ()
  out:list[IntelRelocation] = []
  for section in sections:
    # SHT_REL=9, SHT_RELA=4. Intel's current Zebins use ELF64 REL records.
    if section.header.sh_type not in (4, 9) or section.header.sh_info != target_index: continue
    if section.header.sh_link >= len(sections): raise ValueError("invalid Intel ELF relocation symbol table")
    symtab = sections[section.header.sh_link]
    if symtab.header.sh_link >= len(sections): raise ValueError("invalid Intel ELF string table")
    strtab = sections[symtab.header.sh_link].content
    if symtab.header.sh_entsize != 24: raise ValueError("unsupported Intel ELF symbol table format")
    entry_size = section.header.sh_entsize
    if entry_size not in (16, 24): raise ValueError("unsupported Intel ELF relocation format")
    if len(section.content) % entry_size: raise ValueError("truncated Intel ELF relocation table")
    for offset in range(0, len(section.content), entry_size):
      reloc_offset, info = struct.unpack_from("<QQ", section.content, offset)
      addend = struct.unpack_from("<q", section.content, offset+16)[0] if section.header.sh_type == 4 else 0
      symbol_index, rel_type = info >> 32, info & 0xFFFFFFFF
      if (symbol_index + 1) * symtab.header.sh_entsize > len(symtab.content): raise ValueError("invalid Intel ELF relocation symbol")
      name_offset = struct.unpack_from("<I", symtab.content, symbol_index * symtab.header.sh_entsize)[0]
      if name_offset >= len(strtab): raise ValueError("invalid Intel ELF symbol name")
      name_end = strtab.find(b'\0', name_offset)
      if name_end < 0: raise ValueError("unterminated Intel ELF symbol name")
      symbol = strtab[name_offset:name_end].decode()
      if symbol != "__INTEL_PATCH_CROSS_THREAD_OFFSET_OFF_R0":
        raise ValueError(f"unsupported Intel text relocation symbol {symbol!r}")
      out.append(IntelRelocation(symbol, reloc_offset, rel_type, addend))
  return tuple(out)

def load_zebin(blob:bytes, kernel_name:str) -> IntelProgramImage:
  sections = elf_sections(blob)
  ze_info = next((section.content for section in sections if section.name == ".ze_info"), None)
  if ze_info is None: raise ValueError("Zebin has no .ze_info section")
  metadata = next((meta for meta in parse_ze_info(ze_info.rstrip(b'\0').decode()) if meta.name == kernel_name), None)
  if metadata is None: raise ValueError(f"Zebin has no metadata for kernel {kernel_name!r}")
  code = next((section.content for section in sections if section.name == f".text.{kernel_name}"), None)
  if code is None: raise ValueError(f"Zebin has no .text.{kernel_name} section")
  if metadata.actual_kernel_start_offset >= len(code): raise ValueError("Intel kernel start offset is outside its text section")
  relocations = _zebin_relocations(sections, kernel_name)
  for reloc in relocations:
    if reloc.rel_type != 2: raise ValueError(f"unsupported implicit-args relocation type {reloc.rel_type}")
  return IntelProgramImage(metadata, code, relocations)
