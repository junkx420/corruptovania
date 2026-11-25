"""Read-only parser for the game data of Metroid Prime 3 (Wii PAL RM3P01 and NTSC-U RM3E01).

Reads from an extracted ISO (folder ``DATA/files`` or a folder that contains the
``*.pak`` directly):

- PAK (Wii container, like ``PAK.cs`` in the patcher),
- MLVL (world: SAVW ID, areas with MREA ID),
- MREA (room: script layers with objects, LZO-compressed blocks),
- SAVW (save description of the world, format see ``docs/AP_SAVW_FORMAT.md``).

No dependency on randovania. For compressed MREA blocks ``lzokay`` is used
(available in the Corruptovania venv). Without ``lzokay`` a built-in pure-Python
LZO1X decompressor takes over.
"""

from __future__ import annotations

import dataclasses
import os
import struct
from collections.abc import Iterator

SAVW_MAGIC = 0xC001D00D
MLVL_MAGIC = 0xDEAFBABE
MREA_MAGIC = 0xDEADBEEF


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class Reader:
    """Small big-endian reader over a ``bytes`` buffer."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        (v,) = struct.unpack_from(">H", self.data, self.pos)
        self.pos += 2
        return v

    def u32(self) -> int:
        (v,) = struct.unpack_from(">I", self.data, self.pos)
        self.pos += 4
        return v

    def u64(self) -> int:
        (v,) = struct.unpack_from(">Q", self.data, self.pos)
        self.pos += 8
        return v

    def raw(self, n: int) -> bytes:
        v = self.data[self.pos : self.pos + n]
        if len(v) != n:
            raise ValueError(f"File too short: expected {n} bytes at 0x{self.pos:x}")
        self.pos += n
        return v

    def cstr(self) -> str:
        end = self.data.index(b"\0", self.pos)
        v = self.data[self.pos : end].decode("utf-8")
        self.pos = end + 1
        return v

    def align(self, n: int) -> None:
        self.pos += -self.pos % n


def _lzo1x_decompress_py(src: bytes, out_len: int) -> bytes:
    """Pure-Python LZO1X-1 decompressor (fallback when ``lzokay`` is missing)."""
    out = bytearray()
    ip = 0
    n = len(src)

    def copy_match(dist: int, length: int) -> None:
        start = len(out) - dist
        if start < 0:
            raise ValueError("LZO: invalid distance")
        for i in range(length):
            out.append(out[start + i])

    state = 0
    t = src[ip]
    if t > 17:
        ip += 1
        t -= 17
        out += src[ip : ip + t]
        ip += t
        state = 4 if t >= 4 else t
    while ip < n:
        t = src[ip]
        ip += 1
        if t < 16:
            if state == 0:
                if t == 0:
                    while src[ip] == 0:
                        t += 255
                        ip += 1
                    t += 15 + src[ip]
                    ip += 1
                t += 3
                out += src[ip : ip + t]
                ip += t
                state = 4
                continue
            if state == 4:
                dist = (1 + 0x0800) + (t >> 2) + (src[ip] << 2)
                ip += 1
                copy_match(dist, 3)
            else:
                dist = 1 + (t >> 2) + (src[ip] << 2)
                ip += 1
                copy_match(dist, 2)
            state = t & 3
            out += src[ip : ip + state]
            ip += state
            continue
        if t >= 64:
            dist = 1 + ((t >> 2) & 7) + (src[ip] << 3)
            ip += 1
            length = (t >> 5) - 1 + 2
        elif t >= 32:
            length = t & 31
            if length == 0:
                while src[ip] == 0:
                    length += 255
                    ip += 1
                length += 31 + src[ip]
                ip += 1
            length += 2
            dist = 1 + ((src[ip] | (src[ip + 1] << 8)) >> 2)
            state = src[ip] & 3
            ip += 2
            copy_match(dist, length)
            out += src[ip : ip + state]
            ip += state
            continue
        else:
            length = t & 7
            if length == 0:
                while src[ip] == 0:
                    length += 255
                    ip += 1
                length += 7 + src[ip]
                ip += 1
            length += 2
            dist = (t & 8) << 11
            v = src[ip] | (src[ip + 1] << 8)
            state = src[ip] & 3
            ip += 2
            dist += v >> 2
            if dist == 0:
                break  # end marker
            dist += 0x4000
            copy_match(dist, length)
            out += src[ip : ip + state]
            ip += state
            continue
        copy_match(dist, length)
        state = t & 3
        out += src[ip : ip + state]
        ip += state
    if len(out) != out_len:
        raise ValueError(f"LZO: decompressed {len(out)} instead of {out_len} bytes")
    return bytes(out)


def lzo_decompress(src: bytes, out_len: int) -> bytes:
    try:
        import lzokay  # type: ignore[import-not-found]
    except ImportError:
        return _lzo1x_decompress_py(src, out_len)
    return lzokay.decompress(src, out_len)


def decompress_mrea_block(data: bytes, uncompressed_size: int) -> bytes:
    """Decompresses an MREA block: segments with ``i16`` length (negative = raw),
    at most 0x4000 bytes per segment (``Compression.decompress_mrea_block``)."""
    r = Reader(data)
    out = bytearray()
    while len(out) < uncompressed_size:
        (length,) = struct.unpack_from(">h", data, r.pos)
        r.pos += 2
        if length < 0:
            out += r.raw(-length)
        else:
            seg = min(0x4000, uncompressed_size - len(out))
            out += lzo_decompress(r.raw(length), seg)
    if len(out) != uncompressed_size:
        raise ValueError("MREA block has wrong length")
    return bytes(out)


# --------------------------------------------------------------------------- #
# PAK
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class PakResource:
    compressed: bool
    type: str
    asset_id: int
    size: int
    offset: int  # absolute file offset


class Pak:
    """Wii PAK: 0x40 header, 0x40 table of contents (STRG/RSHD/DATA), then the
    sections (``PakHeader.cs``, ``TableOfContents.cs``)."""

    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        with open(path, "rb") as f:
            head = f.read(0x80)
            toc = Reader(head, 0x40)
            n_sections = toc.u32()
            sections: dict[bytes, tuple[int, int]] = {}
            pos = 0x80
            for _ in range(n_sections):
                cc = toc.raw(4)
                size = toc.u32()
                sections[cc] = (pos, size)
                pos += size
            if b"DATA" not in sections or b"RSHD" not in sections:
                raise ValueError(f"{path}: not a Wii PAK")
            f.seek(sections[b"RSHD"][0])
            rshd = Reader(f.read(sections[b"RSHD"][1]))
            f.seek(sections[b"STRG"][0])
            strg = Reader(f.read(sections[b"STRG"][1]))
        data_start = sections[b"DATA"][0]
        self.resources: dict[int, PakResource] = {}
        for _ in range(rshd.u32()):
            comp = rshd.u32()
            typ = rshd.raw(4).decode("ascii")
            rid = rshd.u64()
            size = rshd.u32()
            off = rshd.u32()
            # the same ID can occur several times; the first entry wins
            self.resources.setdefault(rid, PakResource(comp == 1, typ, rid, size, data_start + off))
        self.names: dict[str, tuple[str, int]] = {}
        for _ in range(strg.u32()):
            name = strg.cstr()
            typ = strg.raw(4).decode("ascii")
            self.names[name] = (typ, strg.u64())

    def read(self, asset_id: int) -> bytes:
        res = self.resources[asset_id]
        if res.compressed:
            raise NotImplementedError(f"{self.name}: resource 0x{asset_id:016X} is CMPD-compressed")
        with open(self.path, "rb") as f:
            f.seek(res.offset)
            return f.read(res.size)


class GameFiles:
    """All ``*.pak`` of an extracted ISO, with lookup by asset ID."""

    def __init__(self, root: str):
        root = os.path.abspath(root)
        for candidate in (root, os.path.join(root, "files"), os.path.join(root, "DATA", "files")):
            if os.path.isdir(candidate) and any(n.lower().endswith(".pak") for n in os.listdir(candidate)):
                self.files_dir = candidate
                break
        else:
            raise FileNotFoundError(f"No .pak files under {root} (expected DATA/files)")
        self.paks = [
            Pak(os.path.join(self.files_dir, n))
            for n in sorted(os.listdir(self.files_dir))
            if n.lower().endswith(".pak")
        ]

    def find(self, asset_id: int, type_: str | None = None) -> tuple[Pak, PakResource]:
        for pak in self.paks:
            res = pak.resources.get(asset_id)
            if res is not None and (type_ is None or res.type == type_):
                return pak, res
        raise KeyError(f"Asset 0x{asset_id:016X} ({type_}) not in any PAK")

    def read(self, asset_id: int, type_: str | None = None) -> bytes:
        pak, _ = self.find(asset_id, type_)
        return pak.read(asset_id)

    def iter_type(self, type_: str) -> Iterator[tuple[Pak, PakResource]]:
        seen: set[int] = set()
        for pak in self.paks:
            for res in pak.resources.values():
                if res.type == type_ and res.asset_id not in seen:
                    seen.add(res.asset_id)
                    yield pak, res

    def names(self, type_: str) -> dict[int, str]:
        """Asset ID → name from the STRG tables of the PAKs (first hit)."""
        out: dict[int, str] = {}
        for pak in self.paks:
            for name, (typ, rid) in pak.names.items():
                if typ == type_:
                    out.setdefault(rid, name)
        return out


# --------------------------------------------------------------------------- #
# MLVL (version 0x19, ``MP3MLVL.cs``)
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class MlvlArea:
    index: int
    name_id: int
    mrea_id: int
    internal_id: int
    internal_name: str


@dataclasses.dataclass(frozen=True)
class Mlvl:
    asset_id: int
    version: int
    world_name_id: int
    savw_id: int
    areas: tuple[MlvlArea, ...]


def parse_mlvl(data: bytes, asset_id: int = 0) -> Mlvl:
    r = Reader(data)
    if r.u32() != MLVL_MAGIC:
        raise ValueError("not an MLVL")
    version = r.u32()
    if version != 0x19:
        raise ValueError(f"MLVL version 0x{version:x}, expected 0x19 (Corruption)")
    world_name_id = r.u64()
    r.u32()  # temple_key_world_index
    savw_id = r.u64()
    r.u64()  # skybox
    areas = []
    for i in range(r.u32()):
        name_id = r.u64()
        r.raw(48 + 24)  # Transform, Bounding Box
        mrea_id = r.u64()
        internal_id = r.u64()
        r.raw(2 * r.u32())  # attached areas (u16)
        for _ in range(r.u32()):  # docks
            r.raw(8 * r.u32())  # connecting docks (area, dock)
            r.raw(12 * r.u32())  # dock coordinates
        areas.append(MlvlArea(i, name_id, mrea_id, internal_id, r.cstr()))
    return Mlvl(asset_id, version, world_name_id, savw_id, tuple(areas))


# --------------------------------------------------------------------------- #
# MREA (version 0x1E, ``MREANew.cs``) and script layers (``ScriptLayer.cs``)
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class ScriptObject:
    type: str
    instance_id: int  # full 32-bit ID: layer << 26 | area << 16 | ID
    connections: tuple[tuple[str, str, int], ...]
    properties: bytes

    @property
    def layer(self) -> int:
        return self.instance_id >> 26

    @property
    def area(self) -> int:
        return (self.instance_id >> 16) & 0x3FF

    @property
    def local_id(self) -> int:
        return self.instance_id & 0xFFFF


@dataclasses.dataclass(frozen=True)
class ScriptLayer:
    index: int  # index of the SCLY section (= layer number in the patcher)
    header: bytes
    objects: tuple[ScriptObject, ...]


@dataclasses.dataclass(frozen=True)
class Mrea:
    asset_id: int
    version: int
    sections: tuple[bytes, ...]
    labels: dict[str, int]
    script_layers: tuple[ScriptLayer, ...]

    def objects(self) -> Iterator[tuple[int, ScriptObject]]:
        for layer in self.script_layers:
            for obj in layer.objects:
                yield layer.index, obj


def _parse_script_layer(index: int, data: bytes) -> ScriptLayer:
    r = Reader(data)
    header = r.raw(10)
    objects = []
    for _ in range(r.u32()):
        typ = r.raw(4).decode("ascii", "replace")
        size = r.u16()
        start = r.pos
        inst = r.u32()
        conns = []
        for _ in range(r.u16()):
            state = r.raw(4).decode("ascii", "replace")
            msg = r.raw(4).decode("ascii", "replace")
            target = r.u32()
            conns.append((state, msg, target))
        props = r.raw(size - (r.pos - start))
        objects.append(ScriptObject(typ, inst, tuple(conns), props))
    return ScriptLayer(index, header, tuple(objects))


def parse_mrea(data: bytes, asset_id: int = 0) -> Mrea:
    r = Reader(data)
    if r.u32() != MREA_MAGIC:
        raise ValueError("not an MREA")
    version = r.u32()
    r.raw(48)  # Transform
    r.u32()  # world model count
    script_layer_count = r.u32()
    section_count = r.u32()
    block_count = r.u32()
    label_count = r.u32()
    r.raw(20)
    section_sizes = [r.u32() for _ in range(section_count)]
    r.align(32)
    blocks = [(r.u32(), r.u32(), r.u32(), r.u32()) for _ in range(block_count)]
    r.align(32)
    labels: dict[str, int] = {}
    for _ in range(label_count):
        name = r.raw(4).decode("ascii", "replace")
        labels[name] = r.u32()
    r.align(32)
    sections: list[bytes] = []
    for _buffer, uncompressed, compressed, n_sections in blocks:
        if compressed == 0:
            raw = r.raw(uncompressed)
        else:
            r.pos += -compressed % 32  # padding bytes come before the data
            raw = decompress_mrea_block(r.raw(compressed), uncompressed)
        pos = 0
        for size in section_sizes[len(sections) : len(sections) + n_sections]:
            sections.append(raw[pos : pos + size])
            pos += size
        # The patcher pads decompressed blocks to 32 bytes without adjusting the section
        # size (MREANew.cs). The rest at the end of the block must be zero.
        if pos > len(raw) or len(raw) - pos >= 32 or raw[pos:].strip(b"\0"):
            raise ValueError(f"MREA 0x{asset_id:016X}: block does not match the section sizes")
    if len(sections) != section_count:
        raise ValueError(f"MREA 0x{asset_id:016X}: {len(sections)} instead of {section_count} sections")
    first = labels.get("SOBJ")
    layers = []
    if first is not None:
        for i in range(script_layer_count):
            sec = sections[first + i]
            if len(sec) >= 14 and sec[:4] == b"SCLY":
                layers.append(_parse_script_layer(i, sec))
    return Mrea(asset_id, version, tuple(sections), labels, tuple(layers))


# --------------------------------------------------------------------------- #
# SAVW (version 6)
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class SavwEntry:
    """An entry of the GUID lists: 16-byte GUID + 32-bit instance ID.

    An entry of 20 zero bytes is an empty slot (the slot stays occupied)."""

    guid: bytes
    instance_id: int

    @property
    def empty(self) -> bool:
        return self.guid == bytes(16) and self.instance_id == 0


@dataclasses.dataclass(frozen=True)
class SavwScan:
    scan_id: int
    category: int


@dataclasses.dataclass(frozen=True)
class SavwVariable:
    name: str
    values: tuple[int, int, int]


@dataclasses.dataclass(frozen=True)
class Savw:
    asset_id: int
    version: int
    area_count: int
    lists: tuple[tuple[SavwEntry, ...], ...]  # lists 0, 1, 2 (before the scans)
    scans: tuple[SavwScan, ...]
    unknown_list: tuple[bytes, ...]  # section after the scans, always empty in PAL
    variables: tuple[SavwVariable, ...]
    objects: tuple[SavwEntry, ...]  # last section (pickups and others)
    trailing: bytes  # 0xFF padding to 64 bytes


def _entries(r: Reader) -> tuple[SavwEntry, ...]:
    out = []
    for _ in range(r.u32()):
        guid = r.raw(16)
        out.append(SavwEntry(guid, r.u32()))
    return tuple(out)


def parse_savw(data: bytes, asset_id: int = 0) -> Savw:
    r = Reader(data)
    if r.u32() != SAVW_MAGIC:
        raise ValueError("not a SAVW")
    version = r.u32()
    if version != 6:
        raise ValueError(f"SAVW version {version}, expected 6")
    area_count = r.u32()
    lists = tuple(_entries(r) for _ in range(3))
    scans = []
    for _ in range(r.u32()):
        scan_id = r.u64()
        scans.append(SavwScan(scan_id, r.u32()))
    n_unknown = r.u32()
    if n_unknown:
        raise NotImplementedError(f"SAVW 0x{asset_id:016X}: unknown section with {n_unknown} entries")
    variables = []
    for _ in range(r.u32()):
        name = r.cstr()
        variables.append(SavwVariable(name, (r.u32(), r.u32(), r.u32())))
    objects = _entries(r)
    trailing = data[r.pos :]
    if trailing.strip(b"\xff"):
        raise ValueError(f"SAVW 0x{asset_id:016X}: {len(trailing)} unexpected bytes at the end")
    return Savw(asset_id, version, area_count, lists, tuple(scans), (), tuple(variables), objects, trailing)
