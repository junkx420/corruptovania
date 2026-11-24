"""Lern-/Logmodus (SPEC E19): protokolliert neu gesetzte Flag-Bytes, wenn ItemPercentage steigt.

Ablauf je Abfrage (``update``):
1. Bytes, die seit der letzten Abfrage derselben Welt von 0 auf ungleich 0 gesprungen sind, kommen mit Zeitpunkt in
   eine Liste ``recent``.
2. Steigt ``ItemPercentage`` (jeder Pickup gibt +1, AP_MEMORY_MAP.md Abschnitt 5), wird ein Ereignis eröffnet.
3. ``after`` Sekunden nach dem Anstieg wird das Ereignis abgeschlossen: alle Bytes aus ``recent`` im Fenster
   ``[Anstieg - before, Anstieg + after]`` werden mit Welt, Raum (falls bekannt) und Zeitpunkt in die Logdatei
   geschrieben (eine JSON-Zeile je Ereignis) und gegen die Tabelle geprüft:
   - Byte gesetzt, aber keinem Ort zugeordnet  -> Warnung ``unknown_byte``
   - Pickup eingesammelt ohne erwartetes Byte  -> Warnung ``pickup_without_byte``
   Das Fenster reicht zurück (``before``), weil bei SpecialFunction-Orten das Memory Relay schon zu Beginn der
   Sequenz gesetzt werden kann (AP_SAVW_FORMAT.md, Ort 43).
4. Orts-Bytes, die ohne ItemPercentage-Anstieg gesetzt wurden, werden als ``location_byte_without_pickup`` protokolliert.

Der Raum ist nur für Bytes bekannt, die laut Tabelle zu einem Ort gehören (der aktuelle Raum wird nicht gelesen,
seine Adresse ist unbekannt, AP_MEMORY_MAP.md Abschnitt 7).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from .checks import LocationTable


@dataclass
class _ByteChange:
    t: float
    wall: str
    byte: int
    value: int
    consumed: bool = False


@dataclass
class _PickupEvent:
    t: float
    wall: str
    world_id: int
    old: int
    new: int
    blocks: tuple[int, ...] = ()
    notes: list[str] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="milliseconds")


class LearningMode:
    def __init__(self, table: LocationTable, log_path: str | None, logger: logging.Logger, enabled: bool = True,
                 before: float = 8.0, after: float = 2.0, clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], str] = _now_iso) -> None:
        self.table = table
        self.log_path = log_path
        self.logger = logger
        self.enabled = enabled
        self.before = before
        self.after = after
        self.clock = clock
        self.wall_clock = wall_clock
        self.entries_written = 0
        self.warnings = 0
        self._world: int | None = None
        self._prev_flags: bytes | None = None
        self._prev_percentage: int | None = None
        self._recent: list[_ByteChange] = []
        self._pending: list[_PickupEvent] = []
        self._last_disagree: tuple[int, ...] = ()

    # ---- Steuerung ------------------------------------------------------------------------------------------- #

    def reset(self) -> None:
        """Menü/Laden: offene Ereignisse abschließen, Vergleichsbasis verwerfen."""
        self.flush()
        self._world = None
        self._prev_flags = None
        self._prev_percentage = None
        self._recent = []

    def flush(self) -> None:
        for event in list(self._pending):
            self._finalize(event)
        self._pending = []
        self._report_unclaimed(force=True)

    # ---- Abfrage --------------------------------------------------------------------------------------------- #

    def update(self, world_id: int, flags: bytes, item_percentage: int | None, inventory_valid: bool,
               blocks: tuple[int, ...] = (), disagree: tuple[int, ...] = ()) -> None:
        if not self.enabled:
            return
        now = self.clock()
        if world_id != self._world:
            self.flush()
            self._world = world_id
            self._prev_flags = None
            self._recent = []
        if self._prev_flags is not None:
            wall = self.wall_clock()
            for i, (old, new) in enumerate(zip(self._prev_flags, flags)):
                if new and not old:
                    self._recent.append(_ByteChange(now, wall, i, new))
        self._prev_flags = bytes(flags)

        if disagree != self._last_disagree:
            self._last_disagree = disagree
            if disagree:
                self._write({"kind": "blocks_disagree", "world": self.table.world_name(world_id),
                             "blocks": [f"0x{a:08X}" for a in blocks], "bytes": list(disagree)})

        if inventory_valid and item_percentage is not None:
            if self._prev_percentage is not None and item_percentage > self._prev_percentage:
                self._pending.append(_PickupEvent(now, self.wall_clock(), world_id, self._prev_percentage,
                                                  item_percentage, blocks))
            self._prev_percentage = item_percentage
        else:
            self._prev_percentage = None  # Inventar noch leer (Intro/Laden): kein Anstieg ableitbar

        for event in [e for e in self._pending if now - e.t >= self.after]:
            self._finalize(event)
        self._report_unclaimed()

    # ---- Auswertung ------------------------------------------------------------------------------------------ #

    def _finalize(self, event: _PickupEvent) -> None:
        if event in self._pending:
            self._pending.remove(event)
        changes = [c for c in self._recent
                   if not c.consumed and event.t - self.before <= c.t <= event.t + self.after]
        entries = []
        warnings = []
        has_location = False
        for change in changes:
            change.consumed = True
            info = self.table.describe(event.world_id, change.byte)
            entries.append({"byte": change.byte, "value": change.value, "time": change.wall, "role": info.role,
                            "location": info.pickup_index, "location_name": info.location_name,
                            "room": info.room, "status": info.status})
            if info.role == "location":
                has_location = True
            elif info.role == "unknown":
                warnings.append(f"Byte {change.byte} gesetzt, aber keinem Ort zugeordnet")
        if not has_location:
            warnings.append("Pickup eingesammelt (ItemPercentage gestiegen) ohne erwartetes Orts-Byte")
        world = self.table.world_name(event.world_id)
        self._write({"kind": "pickup", "time": event.wall, "world": world, "world_id": f"0x{event.world_id:016X}",
                     "room": next((e["room"] for e in entries if e["role"] == "location"), None),
                     "item_percentage": [event.old, event.new], "blocks": [f"0x{a:08X}" for a in event.blocks],
                     "bytes": entries, "warnings": warnings})
        summary = ", ".join(
            f"Byte {e['byte']}" + (f" = Ort {e['location']} ({e['room']})" if e["role"] == "location" else
                                   f" (Zusatz-Byte von Ort {e['location']})" if e["role"] == "extra" else " (unbekannt)")
            for e in entries) or "keine neuen Bytes"
        self.logger.info(f"[Lernmodus] {world}: ItemPercentage {event.old} -> {event.new}: {summary}")
        for warning in warnings:
            self.warnings += 1
            self.logger.warning(f"[Lernmodus] {world}: {warning}")

    def _report_unclaimed(self, force: bool = False) -> None:
        """Orts-Bytes, die ohne ItemPercentage-Anstieg gesetzt wurden (nach Ablauf aller Fenster)."""
        now = self.clock()
        horizon = self.before + self.after
        keep = []
        for change in self._recent:
            in_use = any(e.t - self.before <= change.t <= e.t + self.after for e in self._pending)
            if not force and (now - change.t < horizon or in_use):
                keep.append(change)
                continue
            if not change.consumed and self._world is not None:
                info = self.table.describe(self._world, change.byte)
                if info.role == "location":
                    world = self.table.world_name(self._world)
                    self._write({"kind": "location_byte_without_pickup", "time": change.wall, "world": world,
                                 "byte": change.byte, "location": info.pickup_index,
                                 "location_name": info.location_name, "room": info.room})
                    self.warnings += 1
                    self.logger.warning(f"[Lernmodus] {world}: Byte {change.byte} (Ort {info.pickup_index}) gesetzt, "
                                        f"ohne dass ItemPercentage gestiegen ist")
        self._recent = keep

    def _write(self, record: dict) -> None:
        record.setdefault("time", self.wall_clock())
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.entries_written += 1
        except OSError as exc:
            self.logger.error(f"[Lernmodus] Logdatei {self.log_path} nicht schreibbar: {exc}")
