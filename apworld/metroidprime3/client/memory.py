"""Speicherzugriff auf Dolphin/PrimeHack (T06, SPEC E6).

``MemoryAccess`` kapselt jeden Zugriff auf den Wii-Speicher. Die Spiellogik des Clients benutzt nur diese Klasse.
Unterklassen ersetzen die vier Primitive ``_hook``, ``_unhook``, ``_is_hooked``, ``_read`` (und ``_write``):
``DolphinMemory`` spricht über ``dolphin-memory-engine`` mit Dolphin oder PrimeHack, die Tests benutzen einen
Fake-Speicher (``test/fake_memory.py``).

Regeln:
- Gelesen und geschrieben wird erst, wenn die Game-ID ``RM3P01`` geprüft ist (``connect``). Bei falscher ID wird
  sofort getrennt und nichts geschrieben.
- Adressen außerhalb von MEM1/MEM2 werden abgelehnt (``AddressError``), statt Dolphin danach zu fragen.
- Jeder Fehler des Backends beim Lesen/Schreiben gilt als Verbindungsabbruch (``ConnectionLost``); der Aufrufer
  verbindet danach neu.
"""

from __future__ import annotations

import enum
import struct
from dataclasses import dataclass

MEM1_START = 0x80000000
MEM1_SIZE = 0x01800000
MEM2_START = 0x90000000
MEM2_SIZE = 0x04000000

GAME_ID_ADDRESS = 0x80000000
EXPECTED_GAME_ID = b"RM3P01"  # Metroid Prime 3 Wii PAL (SPEC E7)

SCAN_CHUNK = 0x100000  # 1 MiB je Lesezugriff beim Durchsuchen (so auch die T10-Snapshots)


class MemoryAccessError(Exception):
    """Basisklasse aller Speicherfehler."""


class NotConnected(MemoryAccessError):
    """Zugriff ohne geprüfte Verbindung."""


class ConnectionLost(MemoryAccessError):
    """Das Backend hat beim Lesen/Schreiben einen Fehler gemeldet (Dolphin beendet, Emulation gestoppt, ...)."""


class AddressError(MemoryAccessError):
    """Adresse liegt nicht in MEM1/MEM2."""


class ConnectStatus(enum.Enum):
    CONNECTED = "connected"
    NO_DOLPHIN = "no_dolphin"  # kein Dolphin/PrimeHack gefunden
    NO_GAME = "no_game"  # Dolphin läuft, aber es wird nichts emuliert
    WRONG_GAME = "wrong_game"  # anderes Spiel oder andere Region


@dataclass(frozen=True)
class ConnectResult:
    status: ConnectStatus
    game_id: bytes = b""

    @property
    def message(self) -> str:
        if self.status is ConnectStatus.CONNECTED:
            return f"Mit Dolphin verbunden, Spiel {EXPECTED_GAME_ID.decode()} erkannt."
        if self.status is ConnectStatus.NO_DOLPHIN:
            return "Dolphin/PrimeHack nicht gefunden. Bitte den Emulator starten."
        if self.status is ConnectStatus.NO_GAME:
            return "Dolphin läuft, aber es wird kein Spiel emuliert. Bitte das gepatchte MP3-ISO starten."
        shown = self.game_id.decode("ascii", "replace") if self.game_id else "?"
        return (f"Falsches Spiel in Dolphin: Game-ID {shown!r}, erwartet {EXPECTED_GAME_ID.decode()!r} "
                f"(Metroid Prime 3 PAL). Der Client liest und schreibt nichts.")


def in_ram(address: int, size: int = 1) -> bool:
    end = address + size
    return (MEM1_START <= address and end <= MEM1_START + MEM1_SIZE) or (
        MEM2_START <= address and end <= MEM2_START + MEM2_SIZE)


class MemoryAccess:
    """Gekapselter Wii-Speicher. Unterklassen implementieren nur die Primitive."""

    expected_game_id: bytes = EXPECTED_GAME_ID

    def __init__(self) -> None:
        self.verified = False
        self.last_game_id = b""

    # ---- Primitive (Unterklassen) ---------------------------------------------------------------------------- #

    def _hook(self) -> None:
        raise NotImplementedError

    def _unhook(self) -> None:
        raise NotImplementedError

    def _is_hooked(self) -> bool:
        raise NotImplementedError

    def _read(self, address: int, size: int) -> bytes:
        raise NotImplementedError

    def _write(self, address: int, data: bytes) -> None:
        raise NotImplementedError

    # ---- Verbindung ------------------------------------------------------------------------------------------ #

    @property
    def connected(self) -> bool:
        if not self.verified:
            return False
        try:
            return self._is_hooked()
        except Exception:  # noqa: BLE001 - Backend-Fehler = getrennt
            self.verified = False
            return False

    def connect(self) -> ConnectResult:
        """Hook an Dolphin und prüft die Game-ID. Bei jeder Abweichung wird wieder getrennt."""
        self.verified = False
        try:
            if not self._is_hooked():
                self._hook()
            if not self._is_hooked():
                return ConnectResult(ConnectStatus.NO_DOLPHIN)
            game_id = self._read(GAME_ID_ADDRESS, len(self.expected_game_id))
        except Exception:  # noqa: BLE001 - dme wirft RuntimeError, wenn nichts emuliert wird
            self._safe_unhook()
            return ConnectResult(ConnectStatus.NO_GAME)
        self.last_game_id = bytes(game_id)
        if not any(game_id):
            self._safe_unhook()
            return ConnectResult(ConnectStatus.NO_GAME)
        if game_id != self.expected_game_id:
            self._safe_unhook()
            return ConnectResult(ConnectStatus.WRONG_GAME, bytes(game_id))
        self.verified = True
        return ConnectResult(ConnectStatus.CONNECTED, bytes(game_id))

    def disconnect(self) -> None:
        self.verified = False
        self._safe_unhook()

    def _safe_unhook(self) -> None:
        try:
            self._unhook()
        except Exception:  # noqa: BLE001
            pass

    def check_game_id(self) -> bool:
        """Liest die Game-ID erneut (Spielwechsel im laufenden Dolphin). Bei Abweichung: trennen, ``False``."""
        game_id = self.read(GAME_ID_ADDRESS, len(self.expected_game_id))
        if game_id != self.expected_game_id:
            self.last_game_id = bytes(game_id)
            self.disconnect()
            return False
        return True

    # ---- Lesen / Schreiben ----------------------------------------------------------------------------------- #

    def read(self, address: int, size: int) -> bytes:
        if not self.verified:
            raise NotConnected("Speicherzugriff ohne geprüfte Verbindung")
        if size <= 0 or not in_ram(address, size):
            raise AddressError(f"Bereich 0x{address:08X}+0x{size:X} liegt nicht in MEM1/MEM2")
        try:
            data = self._read(address, size)
        except Exception as exc:  # noqa: BLE001
            self.verified = False
            raise ConnectionLost(f"Lesen bei 0x{address:08X} fehlgeschlagen: {exc}") from exc
        if len(data) != size:
            self.verified = False
            raise ConnectionLost(f"Lesen bei 0x{address:08X}: {len(data)} statt {size} Byte")
        return bytes(data)

    def write(self, address: int, data: bytes) -> None:
        """Schreiben (erst ab T07 benutzt). Prüft vorher noch einmal die Game-ID."""
        if not self.verified:
            raise NotConnected("Schreiben ohne geprüfte Verbindung")
        if not data or not in_ram(address, len(data)):
            raise AddressError(f"Bereich 0x{address:08X}+0x{len(data):X} liegt nicht in MEM1/MEM2")
        if not self.check_game_id():
            raise NotConnected("Game-ID hat sich geändert, Schreiben abgebrochen")
        try:
            self._write(address, bytes(data))
        except Exception as exc:  # noqa: BLE001
            self.verified = False
            raise ConnectionLost(f"Schreiben bei 0x{address:08X} fehlgeschlagen: {exc}") from exc

    def read_u32(self, address: int) -> int:
        return struct.unpack(">I", self.read(address, 4))[0]

    def read_u64(self, address: int) -> int:
        return struct.unpack(">Q", self.read(address, 8))[0]

    def read_pointer(self, address: int) -> int | None:
        """4-Byte-Zeiger lesen. ``None``, wenn er nicht in MEM1/MEM2 zeigt (z. B. 0 im Menü)."""
        value = self.read_u32(address)
        return value if in_ram(value) else None

    def iter_chunks(self, start: int, size: int, overlap: int = 0, chunk: int = SCAN_CHUNK):
        """Liest ``[start, start+size)`` stückweise. Liefert ``(adresse, daten)``; aufeinanderfolgende Stücke
        überlappen um ``overlap`` Byte, damit Muster an Stückgrenzen gefunden werden."""
        pos = start
        end = start + size
        while pos < end:
            n = min(chunk, end - pos)
            data = self.read(pos, n)
            if pos + n < end and overlap:
                data += self.read(pos + n, min(overlap, end - pos - n))
            yield pos, data
            pos += n


class DolphinMemory(MemoryAccess):
    """Echter Zugriff über ``dolphin-memory-engine`` (Dolphin und PrimeHack)."""

    def __init__(self) -> None:
        super().__init__()
        try:
            import dolphin_memory_engine
        except ImportError as exc:  # pragma: no cover - nur ohne Abhängigkeit
            raise ImportError(
                "Das Paket 'dolphin-memory-engine' fehlt. Installieren mit: "
                "python -m pip install \"dolphin-memory-engine>=1.3.0\"") from exc
        self._dme = dolphin_memory_engine

    def _hook(self) -> None:
        self._dme.hook()

    def _unhook(self) -> None:
        self._dme.un_hook()

    def _is_hooked(self) -> bool:
        return bool(self._dme.is_hooked())

    def _read(self, address: int, size: int) -> bytes:
        return self._dme.read_bytes(address, size)

    def _write(self, address: int, data: bytes) -> None:
        self._dme.write_bytes(address, data)
