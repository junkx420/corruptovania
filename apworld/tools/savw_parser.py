"""Nur-lesender Parser für die Spieldaten von Metroid Prime 3 (Wii, PAL RM3P01).

Liest aus einem entpackten ISO (Ordner ``DATA/files`` oder ein Ordner, der die
``*.pak`` direkt enthält):

- PAK (Wii-Container, wie ``PAK.cs`` im Patcher),
- MLVL (Welt: SAVW-ID, Bereiche mit MREA-ID),
- MREA (Raum: Skript-Layer mit Objekten, LZO-komprimierte Blöcke),
- SAVW (Speicher-Beschreibung der Welt, Format siehe ``docs/AP_SAVW_FORMAT.md``).

Keine Abhängigkeit von randovania. Für komprimierte MREA-Blöcke wird ``lzokay``
benutzt (in der Corruptovania-venv vorhanden). Ohne ``lzokay`` greift ein
eingebauter LZO1X-Entpacker in reinem Python.
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
# Hilfen
# --------------------------------------------------------------------------- #


class Reader:
    """Kleiner Big-Endian-Leser über einem ``bytes``-Puffer."""

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
            raise ValueError(f"Datei zu kurz: {n} Byte bei 0x{self.pos:x} erwartet")
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
    """LZO1X-1-Entpacker in reinem Python (Rückfall, wenn ``lzokay`` fehlt)."""
    out = bytearray()
    ip = 0
    n = len(src)

    def copy_match(dist: int, length: int) -> None:
        start = len(out) - dist
        if start < 0:
            raise ValueError("LZO: ungültige Distanz")
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
                break  # Ende-Marke
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
        raise ValueError(f"LZO: {len(out)} statt {out_len} Byte entpackt")
    return bytes(out)


def lzo_decompress(src: bytes, out_len: int) -> bytes:
    try:
        import lzokay  # type: ignore[import-not-found]
    except ImportError:
        return _lzo1x_decompress_py(src, out_len)
    return lzokay.decompress(src, out_len)


def decompress_mrea_block(data: bytes, uncompressed_size: int) -> bytes:
    """Entpackt einen MREA-Block: Segmente mit ``i16``-Länge (negativ = roh),
    je Segment höchstens 0x4000 Byte (``Compression.decompress_mrea_block``)."""
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
        raise ValueError("MREA-Block hat falsche Länge")
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
    offset: int  # absoluter Dateioffset


class Pak:
    """Wii-PAK: 0x40 Kopf, 0x40 Inhaltsverzeichnis (STRG/RSHD/DATA), dann die
    Abschnitte (``PakHeader.cs``, ``TableOfContents.cs``)."""

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
                raise ValueError(f"{path}: kein Wii-PAK")
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
            # gleiche ID kann mehrfach vorkommen; erster Eintrag gewinnt
            self.resources.setdefault(rid, PakResource(comp == 1, typ, rid, size, data_start + off))
        self.names: dict[str, tuple[str, int]] = {}
        for _ in range(strg.u32()):
            name = strg.cstr()
            typ = strg.raw(4).decode("ascii")
            self.names[name] = (typ, strg.u64())

    def read(self, asset_id: int) -> bytes:
        res = self.resources[asset_id]
        if res.compressed:
            raise NotImplementedError(f"{self.name}: Ressource 0x{asset_id:016X} ist CMPD-komprimiert")
        with open(self.path, "rb") as f:
            f.seek(res.offset)
            return f.read(res.size)


class GameFiles:
    """Alle ``*.pak`` eines entpackten ISO, mit Suche nach Asset-ID."""

    def __init__(self, root: str):
        root = os.path.abspath(root)
        for candidate in (root, os.path.join(root, "files"), os.path.join(root, "DATA", "files")):
            if os.path.isdir(candidate) and any(n.lower().endswith(".pak") for n in os.listdir(candidate)):
                self.files_dir = candidate
                break
        else:
            raise FileNotFoundError(f"Keine .pak-Dateien unter {root} (erwartet DATA/files)")
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
        raise KeyError(f"Asset 0x{asset_id:016X} ({type_}) in keinem PAK")

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
        """Asset-ID → Name aus den STRG-Tabellen der PAKs (erster Treffer)."""
        out: dict[int, str] = {}
        for pak in self.paks:
            for name, (typ, rid) in pak.names.items():
                if typ == type_:
                    out.setdefault(rid, name)
        return out


# --------------------------------------------------------------------------- #
# MLVL (Version 0x19, ``MP3MLVL.cs``)
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
        raise ValueError("kein MLVL")
    version = r.u32()
    if version != 0x19:
        raise ValueError(f"MLVL-Version 0x{version:x}, erwartet 0x19 (Corruption)")
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
# MREA (Version 0x1E, ``MREANew.cs``) und Skript-Layer (``ScriptLayer.cs``)
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class ScriptObject:
    type: str
    instance_id: int  # volle 32-Bit-ID: Layer << 26 | Bereich << 16 | ID
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
    index: int  # Index des SCLY-Abschnitts (= Layer-Nummer im Patcher)
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
        raise ValueError("kein MREA")
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
            r.pos += -compressed % 32  # Füllbytes stehen vor den Daten
            raw = decompress_mrea_block(r.raw(compressed), uncompressed)
        pos = 0
        for size in section_sizes[len(sections) : len(sections) + n_sections]:
            sections.append(raw[pos : pos + size])
            pos += size
        # Der Patcher polstert entpackte Blöcke auf 32 Byte, ohne die Abschnittsgröße
        # anzupassen (MREANew.cs). Rest am Blockende muss Null sein.
        if pos > len(raw) or len(raw) - pos >= 32 or raw[pos:].strip(b"\0"):
            raise ValueError(f"MREA 0x{asset_id:016X}: Block passt nicht zu den Abschnittsgrößen")
    if len(sections) != section_count:
        raise ValueError(f"MREA 0x{asset_id:016X}: {len(sections)} statt {section_count} Abschnitte")
    first = labels.get("SOBJ")
    layers = []
    if first is not None:
        for i in range(script_layer_count):
            sec = sections[first + i]
            if len(sec) >= 14 and sec[:4] == b"SCLY":
                layers.append(_parse_script_layer(i, sec))
    return Mrea(asset_id, version, tuple(sections), labels, tuple(layers))


# --------------------------------------------------------------------------- #
# SAVW (Version 6)
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class SavwEntry:
    """Ein Eintrag der GUID-Listen: 16 Byte GUID + 32-Bit-Instanz-ID.

    Ein Eintrag aus 20 Nullbytes ist ein Leerplatz (Platz bleibt belegt)."""

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
    lists: tuple[tuple[SavwEntry, ...], ...]  # Listen 0, 1, 2 (vor den Scans)
    scans: tuple[SavwScan, ...]
    unknown_list: tuple[bytes, ...]  # Abschnitt nach den Scans, in PAL immer leer
    variables: tuple[SavwVariable, ...]
    objects: tuple[SavwEntry, ...]  # letzter Abschnitt (Pickups u. a.)
    trailing: bytes  # 0xFF-Füllung auf 64 Byte


def _entries(r: Reader) -> tuple[SavwEntry, ...]:
    out = []
    for _ in range(r.u32()):
        guid = r.raw(16)
        out.append(SavwEntry(guid, r.u32()))
    return tuple(out)


def parse_savw(data: bytes, asset_id: int = 0) -> Savw:
    r = Reader(data)
    if r.u32() != SAVW_MAGIC:
        raise ValueError("kein SAVW")
    version = r.u32()
    if version != 6:
        raise ValueError(f"SAVW-Version {version}, erwartet 6")
    area_count = r.u32()
    lists = tuple(_entries(r) for _ in range(3))
    scans = []
    for _ in range(r.u32()):
        scan_id = r.u64()
        scans.append(SavwScan(scan_id, r.u32()))
    n_unknown = r.u32()
    if n_unknown:
        raise NotImplementedError(f"SAVW 0x{asset_id:016X}: unbekannter Abschnitt mit {n_unknown} Einträgen")
    variables = []
    for _ in range(r.u32()):
        name = r.cstr()
        variables.append(SavwVariable(name, (r.u32(), r.u32(), r.u32())))
    objects = _entries(r)
    trailing = data[r.pos :]
    if trailing.strip(b"\xff"):
        raise ValueError(f"SAVW 0x{asset_id:016X}: {len(trailing)} unerwartete Byte am Ende")
    return Savw(asset_id, version, area_count, lists, tuple(scans), (), tuple(variables), objects, trailing)
