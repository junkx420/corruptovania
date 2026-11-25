"""T19/T15: Bitbreite und Persistenz der Inventar-Slots (PAL RM3P01), live über dolphin-memory-engine.

Schreibt ausschließlich in den PrimeHack-/Dolphin-RAM, und dort nur in das Inventar-Array
``PS + 0x54 + slot*0xC`` (Anzahl, Kapazität; ``PS = [[0x80680234]+0x24]``) und nur, wenn das Spiel ingame ist.
Ergebnisse (Snapshots, Logs) gehen nach ``--out`` (Standard: ``../out/t19`` neben dem Repo, nicht ins Repo).

Befehle (Repo-Wurzel, venv):

    venv\\Scripts\\python.exe -I apworld\\tools\\live\\slot_probe.py dol ..\\pal_extract\\DATA\\sys\\main.dol
    venv\\Scripts\\python.exe -I apworld\\tools\\live\\slot_probe.py status
    venv\\Scripts\\python.exe -I apworld\\tools\\live\\slot_probe.py snap NAME
    venv\\Scripts\\python.exe -I apworld\\tools\\live\\slot_probe.py apply pass1|pass2
    venv\\Scripts\\python.exe -I apworld\\tools\\live\\slot_probe.py check pass1|pass2
    venv\\Scripts\\python.exe -I apworld\\tools\\live\\slot_probe.py restore NAME [--slots 1,2,...]
    venv\\Scripts\\python.exe -I apworld\\tools\\live\\slot_probe.py watch [--interval 0.1]

``dol`` liest die Powerup-Tabelle aus der main.dol (je Slot: Namenszeiger, Maximum, Flags; PAL ``0x8057D5F8``)
und vergleicht sie mit ``SLOT_TABLE`` unten. ``apply`` merkt sich vorher den Ist-Zustand (``pre_<plan>.json``),
schreibt den Plan und liest nach 0,5 s und 3 s zurück (``live_<plan>.json``). ``check`` liest nach dem Neuladen und
vergleicht mit zwei Hypothesen: ``mod`` (Speichern behält die unteren ``bits`` Bit) und ``clamp`` (auf Maximum).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path

GAME_ID = b"RM3P01"
GAME_STATE_POINTER = 0x80680234
CSTATE_MANAGER_GLOBAL = 0x805C7570
CPLAYER_VTABLE = 0x80595238
OFF_PLAYER_STATE = 0x24
OFF_INVENTORY = 0x54
SLOT_SIZE = 0xC
SLOT_COUNT = 70
MEM1 = (0x80000000, 0x81800000)

# PAL main.dol, Tabelle ab 0x8057D5F8 (Dateioffset 0x5796D8), 70 Einträge zu 12 Byte: u32 Namenszeiger, u32 Maximum,
# u32 Flags. Mit `slot_probe.py dol <main.dol>` reproduzierbar. Original- und T01-ISO sind hier byte-identisch.
SLOT_TABLE: list[tuple[str, int, int]] = [
    ("PowerBeam", 1, 0xC0000000), ("PlasmaBeam", 1, 0xC0000000), ("NovaBeam", 1, 0xC0000000),
    ("ChargeUpgrade", 1, 0xC0000000), ("Missile", 255, 0xC0000000), ("IceMissile", 1, 0xC0000000),
    ("SeekerMissile", 1, 0xC0000000), ("GrappleBeamPull", 1, 0xC0000000), ("GrappleBeamSwing", 1, 0xC0000000),
    ("GrappleBeamVoltage", 1, 0xC0000000), ("Bomb", 1, 0xC0000000), ("CombatVisor", 1, 0xC0000000),
    ("ScanVisor", 1, 0xC0000000), ("CommandVisor", 1, 0xC0000000), ("XRayVisor", 1, 0xC0000000),
    ("DoubleJump", 1, 0xC0000000), ("ScrewAttack", 1, 0xC0000000), ("SuitType", 6, 0xC0000000),
    ("Energy", 1499, 0x00000000), ("HypermodeEnergy", 0, 0x00000000), ("EnergyTank", 14, 0xC0000000),
    ("ItemPercentage", 255, 0x80000000), ("Fuses", 9, 0xC0000000), ("Fuse1", 1, 0xC0000000),
    ("Fuse2", 1, 0xC0000000), ("Fuse3", 1, 0xC0000000), ("Fuse4", 1, 0xC0000000), ("Fuse5", 1, 0xC0000000),
    ("Fuse6", 1, 0xC0000000), ("Fuse7", 1, 0xC0000000), ("Fuse8", 1, 0xC0000000), ("Fuse9", 1, 0xC0000000),
    ("MorphBall", 1, 0xC0000000), ("BoostBall", 1, 0xC0000000), ("SpiderBall", 1, 0xC0000000),
    ("HyperModeTank", 1, 0xC0000000), ("HyperModeBeam", 1, 0xC0000000), ("HyperModeMissile", 1, 0xC0000000),
    ("HyperModeBall", 1, 0xC0000000), ("HyperModeGrapple", 1, 0xC0000000), ("HyperModePermanent", 1, 0x80000000),
    ("HyperModePhaaze", 1, 0x80000000), ("HyperModeOriginal", 1, 0xC0000000), ("HyperModeCharge", 1, 0xC0000000),
    ("ShipGrapple", 1, 0xC0000000), ("ShipMissile", 11, 0xC0000000), ("FaceCorruptionLevel", 4, 0xC0000000),
    ("PhazonBall", 1, 0x00000000), ("CannonBall", 1, 0x00000000), ("ActivateMorphballBoost", 1, 0x00000000),
    ("HyperShot", 2, 0x00000000), ("CommandVisorJammed", 1, 0x80000000), ("FusesUsed", 9, 0x80000000),
    ("Fuse1Used", 1, 0x80000000), ("Fuse2Used", 1, 0x80000000), ("Fuse3Used", 1, 0x80000000),
    ("Fuse4Used", 1, 0x80000000), ("Fuse5Used", 1, 0x80000000), ("Fuse6Used", 1, 0x80000000),
    ("Fuse7Used", 1, 0x80000000), ("Fuse8Used", 1, 0x80000000), ("Fuse9Used", 1, 0x80000000),
    ("Stat_EnemiesKilled", 99999, 0xC0000000), ("Stat_ShotsFired", 99999, 0xC0000000),
    ("Stat_DamageReceived", 99999, 0xC0000000), ("Stat_DataSaves", 99999, 0xC0000000),
    ("Stat_HypermodeUses", 99999, 0xC0000000), ("Stat_CommandoKills", 99999, 0xC0000000),
    ("Stat_TinCanHighScore", 99999, 0xC0000000), ("Stat_TinCanCurrentScore", 99999, 0x00000000),
]
DOL_TABLE_ADDRESS = 0x8057D5F8

# Höchster Wert, den der volle AP-Pool (apworld/metroidprime3/data/items.py) plus Startitems im Slot ergeben kann,
# gerechnet mit den Pickup-Mengen aus Item.cs (amount = capacity). Slot 21: Start 100 + 99 Orte.
POOL_MAX: dict[int, int] = {
    0: 1, 1: 1, 2: 1, 3: 1, 4: 5 + 48 * 5, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1, 10: 1, 11: 1, 12: 1, 13: 1, 14: 1,
    15: 1, 16: 1, 17: 6 + 5, 20: 14, 21: 100 + 99, 22: 9, **{s: 1 for s in range(23, 32)}, 32: 1, 33: 1, 34: 1,
    35: 1, 36: 1, 37: 1, 38: 1, 39: 1, 44: 1, 45: 3 + 8, 68: 48 * 5,
}

# Slots, die der Test nicht anfasst (Story-/Zustandsflags, Lebensenergie, Statistik).
SKIP = {18, 19, 40, 41, 42, 46, 48, 49, 50, 51, 62, 63, 64, 65, 66, 67}
# Slots, deren Verlust das Spiel unbedienbar machen könnte: in pass2 nur Werte, die bei 1 Bit wieder 1 ergeben.
CRITICAL = {0, 11, 12, 15, 32}


def bits(slot: int) -> int:
    return SLOT_TABLE[slot][1].bit_length()


def saved(slot: int) -> bool:
    return bool(SLOT_TABLE[slot][2] & 0x80000000)


def plan(name: str) -> dict[int, tuple[int, int]]:
    """Schreibwerte (Anzahl, Kapazität) je Slot.

    pass2 (Anzahl > Kapazität, Suit-Anzahl 13, ItemPercentage 257) ließ PrimeHack live einfrieren, noch vor dem
    Speichern. pass2s ist die entschärfte Fassung: Anzahl = Kapazität = 2^bits, Suit-Anzahl bleibt 5.
    """
    if name == "pass2s":
        safe: dict[int, tuple[int, int]] = {}
        for slot in range(SLOT_COUNT):
            if slot in SKIP:
                continue
            n = bits(slot)
            if not saved(slot):
                safe[slot] = (0, 2) if slot == 47 else (9, 9)
            elif slot in CRITICAL:
                safe[slot] = (1, 1)
            elif slot == 17:
                safe[slot] = (5, 8)
            elif SLOT_TABLE[slot][2] == 0x80000000 and n == 1:  # Fuse*Used: Anzahl/Kapazität getrennt
                safe[slot] = (2, 3) if slot % 2 else (3, 2)
            else:
                safe[slot] = (1 << n, 1 << n)
        return safe
    out: dict[int, tuple[int, int]] = {}
    for slot in range(SLOT_COUNT):
        if slot in SKIP:
            continue
        n = bits(slot)
        if not saved(slot):  # Flag ohne Bit 31: Erwartung „nicht gespeichert“
            out[slot] = (1, 1) if name == "pass1" else (0, 2)
            if slot == 69:
                out[slot] = (8, 8) if name == "pass1" else (9, 9)
            continue
        if n == 1:
            if SLOT_TABLE[slot][2] == 0x80000000:  # Fuse*Used: Anzahl und Kapazität getrennt prüfen
                if name == "pass1":
                    out[slot] = (1, 0) if slot % 2 else (0, 1)
                else:
                    out[slot] = (3, 2) if slot % 2 else (2, 3)
            elif name == "pass1":
                out[slot] = (1, 1)
            else:
                out[slot] = (3, 3) if slot in CRITICAL else (3, 2)
            continue
        top = (1 << n) - 1
        if name == "pass1":
            amount = min(POOL_MAX.get(slot, top), top)
            if slot == 17:
                amount = 5  # Anzahl wie Hazard-Shield-Pickup (T11)
            out[slot] = (amount, top)
        else:
            amount = (1 << n) + 1
            if slot == 17:
                amount = 8 + 5  # mod 8 = 5: Anzug bleibt Hazard
            out[slot] = (amount, 1 << n)
    return out


def expected(slot: int, value: int, mode: str) -> int:
    if not saved(slot):
        return 0
    if mode == "mod":
        return value & ((1 << bits(slot)) - 1)
    return min(value, SLOT_TABLE[slot][1])


# --------------------------------------------------------------------------------------------------- Speicher


class Game:
    def __init__(self) -> None:
        import dolphin_memory_engine as dme

        self.dme = dme
        if not dme.is_hooked():
            dme.hook()
        if not dme.is_hooked():
            sys.exit("Dolphin/PrimeHack nicht gefunden (Spiel gestartet?)")
        game_id = dme.read_bytes(0x80000000, 6)
        if game_id != GAME_ID:
            sys.exit(f"Falsche Game-ID {game_id!r}, erwartet {GAME_ID!r}")

    def u32(self, address: int) -> int:
        return struct.unpack(">I", self.dme.read_bytes(address, 4))[0]

    def ptr(self, address: int) -> int | None:
        value = self.u32(address)
        return value if MEM1[0] <= value < MEM1[1] else None

    def player_state(self) -> int | None:
        holder = self.ptr(CSTATE_MANAGER_GLOBAL + 0x28)
        cplayer = self.ptr(holder + 0x2184) if holder else None
        if cplayer is None or self.u32(cplayer) != CPLAYER_VTABLE:
            return None
        gs = self.ptr(GAME_STATE_POINTER)
        ps = self.ptr(gs + OFF_PLAYER_STATE) if gs else None
        if ps is None or self.slots(ps)[0][1] == 0:  # PowerBeam.capacity 0 = Inventar nicht befüllt
            return None
        return ps

    def world(self) -> int | None:
        gs = self.ptr(GAME_STATE_POINTER)
        return struct.unpack(">Q", self.dme.read_bytes(gs + 8, 8))[0] if gs else None

    def slots(self, ps: int) -> list[tuple[int, int]]:
        raw = self.dme.read_bytes(ps + OFF_INVENTORY, SLOT_COUNT * SLOT_SIZE)
        return [struct.unpack_from(">II", raw, i * SLOT_SIZE) for i in range(SLOT_COUNT)]

    def write_slot(self, ps: int, slot: int, amount: int, capacity: int) -> None:
        assert 0 <= slot < SLOT_COUNT
        address = ps + OFF_INVENTORY + slot * SLOT_SIZE
        assert MEM1[0] <= address and address + 8 <= MEM1[1]
        self.dme.write_bytes(address, struct.pack(">II", amount, capacity))


def need_ingame(game: Game) -> int:
    ps = game.player_state()
    if ps is None:
        sys.exit("Nicht ingame (Menü/Laden oder Inventar leer) – nichts gelesen/geschrieben")
    return ps


def dump(out: Path, name: str, game: Game, ps: int, extra: dict | None = None) -> dict:
    data = {
        "name": name,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "player_state": hex(ps),
        "world": hex(game.world() or 0),
        "slots": {str(i): list(v) for i, v in enumerate(game.slots(ps))},
    }
    if extra:
        data.update(extra)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def load(out: Path, name: str) -> dict:
    return json.loads((out / f"{name}.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------- Befehle


def cmd_dol(path: Path) -> int:
    d = path.read_bytes()
    offs = struct.unpack(">18I", d[0:72])
    addrs = struct.unpack(">18I", d[72:144])
    sizes = struct.unpack(">18I", d[144:216])

    def a2f(a: int) -> int:
        for i in range(18):
            if sizes[i] and addrs[i] <= a < addrs[i] + sizes[i]:
                return offs[i] + a - addrs[i]
        raise ValueError(hex(a))

    base = a2f(DOL_TABLE_ADDRESS)
    bad = 0
    for slot in range(SLOT_COUNT):
        name_ptr, maximum, flags = struct.unpack_from(">3I", d, base + slot * 12)
        o = a2f(name_ptr)
        name = d[o : d.index(b"\0", o)].decode()
        ok = (name, maximum, flags) == SLOT_TABLE[slot]
        bad += not ok
        print(f"{slot:2} {name:24} max {maximum:6} bits {maximum.bit_length():2} flags {flags:#010x} {'' if ok else '<-- ABWEICHUNG'}")
    print("Tabelle stimmt mit SLOT_TABLE überein" if not bad else f"{bad} Abweichungen")
    return 1 if bad else 0


def cmd_status(game: Game) -> int:
    ps = need_ingame(game)
    print(f"PS {ps:#x}  Welt {game.world():#018x}")
    for i, (a, c) in enumerate(game.slots(ps)):
        print(f"{i:2} {SLOT_TABLE[i][0]:24} {a:7}/{c:<7}")
    return 0


def cmd_apply(game: Game, out: Path, name: str) -> int:
    ps = need_ingame(game)
    p = plan(name)
    dump(out, f"pre_{name}", game, ps)
    for slot, (a, c) in p.items():
        game.write_slot(ps, slot, a, c)
    print(f"{len(p)} Slots geschrieben ({name})")
    reads = {}
    for delay in (0.5, 3.0):
        time.sleep(delay if delay == 0.5 else delay - 0.5)
        cur = game.slots(ps)
        reads[str(delay)] = {str(s): list(cur[s]) for s in p}
        drift = {s: cur[s] for s in p if tuple(cur[s]) != p[s]}
        print(f"nach {delay} s: {len(drift)} Slots abweichend " + ", ".join(f"{s}={v[0]}/{v[1]}" for s, v in drift.items()))
    dump(out, f"live_{name}", game, ps, {"plan": {str(s): list(v) for s, v in p.items()}, "reads": reads})
    return 0


def cmd_check(game: Game, out: Path, name: str) -> int:
    ps = need_ingame(game)
    live = load(out, f"live_{name}")
    after = dump(out, f"loaded_{name}", game, ps)
    print(f"{'slot':>4} {'name':24} {'geschrieben':>15} {'vor Speichern':>15} {'nach Laden':>15} {'mod':>10} {'clamp':>10}")
    counts = {"mod": 0, "clamp": 0, "n": 0}
    for s, (wa, wc) in sorted((int(k), v) for k, v in live["plan"].items()):
        la, lc = live["reads"]["3.0"][str(s)]
        aa, ac = after["slots"][str(s)]
        em = (expected(s, la, "mod"), expected(s, lc, "mod"))
        ec = (expected(s, la, "clamp"), expected(s, lc, "clamp"))
        counts["n"] += 1
        counts["mod"] += (aa, ac) == em
        counts["clamp"] += (aa, ac) == ec
        flag = "" if (aa, ac) in (em, ec) else "  <-- weder mod noch clamp"
        print(f"{s:4} {SLOT_TABLE[s][0]:24} {f'{wa}/{wc}':>15} {f'{la}/{lc}':>15} {f'{aa}/{ac}':>15} "
              f"{f'{em[0]}/{em[1]}':>10} {f'{ec[0]}/{ec[1]}':>10}{flag}")
    print(f"Treffer: mod {counts['mod']}/{counts['n']}, clamp {counts['clamp']}/{counts['n']}")
    return 0


def cmd_restore(game: Game, out: Path, name: str, only: set[int] | None) -> int:
    ps = need_ingame(game)
    snap = load(out, name)
    source = load(out, f"live_{name[4:]}")["plan"] if name.startswith("pre_") else snap["slots"]
    targets = sorted(int(s) for s in source if only is None or int(s) in only)
    for s in targets:
        a, c = snap["slots"][str(s)]
        game.write_slot(ps, s, a, c)
    print(f"{len(targets)} Slots aus {name} zurückgeschrieben: {targets}")
    return 0


def cmd_watch(game: Game, out: Path, interval: float) -> int:
    out.mkdir(parents=True, exist_ok=True)
    log = out / f"watch_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    print(f"Log: {log}", flush=True)
    last: list | None = None
    last_state = None
    with log.open("a", encoding="utf-8") as f:
        while True:
            try:
                ps = game.player_state()
                state = "ingame" if ps else "nicht ingame"
                if state != last_state:
                    rec = {"t": time.strftime("%H:%M:%S"), "state": state, "world": hex(game.world() or 0)}
                    f.write(json.dumps(rec) + "\n")
                    print(rec, flush=True)
                    last_state = state
                if ps:
                    cur = game.slots(ps)
                    if last is not None:
                        ch = {i: (last[i], cur[i]) for i in range(SLOT_COUNT) if cur[i] != last[i]}
                        if ch:
                            rec = {"t": time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03}",
                                   "changes": {f"{i} {SLOT_TABLE[i][0]}": [list(o), list(n)] for i, (o, n) in ch.items()}}
                            f.write(json.dumps(rec) + "\n")
                            f.flush()
                            print(rec, flush=True)
                    else:
                        f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "baseline": [list(v) for v in cur]}) + "\n")
                    last = cur
                else:
                    last = None
            except RuntimeError as e:  # Lesefehler, z. B. beim Laden
                print(f"Lesefehler: {e}", flush=True)
                last = None
            time.sleep(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[4] / "out" / "t19")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dol").add_argument("path", type=Path)
    sub.add_parser("status")
    sub.add_parser("snap").add_argument("name")
    sub.add_parser("plan").add_argument("name", choices=["pass1", "pass2", "pass2s"])
    sub.add_parser("apply").add_argument("name", choices=["pass1", "pass2", "pass2s"])
    sub.add_parser("check").add_argument("name", choices=["pass1", "pass2", "pass2s"])
    r = sub.add_parser("restore")
    r.add_argument("name")
    r.add_argument("--slots", default=None)
    sub.add_parser("watch").add_argument("--interval", type=float, default=0.1)
    args = ap.parse_args()

    if args.cmd == "dol":
        return cmd_dol(args.path)
    if args.cmd == "plan":
        for s, (a, c) in plan(args.name).items():
            print(f"{s:2} {SLOT_TABLE[s][0]:24} bits {bits(s):2} {'saved' if saved(s) else 'flag0'} -> {a}/{c}")
        return 0
    game = Game()
    if args.cmd == "status":
        return cmd_status(game)
    if args.cmd == "snap":
        ps = need_ingame(game)
        dump(args.out, args.name, game, ps)
        print(f"Snapshot {args.name} -> {args.out}")
        return 0
    if args.cmd == "apply":
        return cmd_apply(game, args.out, args.name)
    if args.cmd == "check":
        return cmd_check(game, args.out, args.name)
    if args.cmd == "restore":
        only = {int(x) for x in args.slots.split(",")} if args.slots else None
        return cmd_restore(game, args.out, args.name, only)
    if args.cmd == "watch":
        return cmd_watch(game, args.out, args.interval)
    return 2


if __name__ == "__main__":
    sys.exit(main())
