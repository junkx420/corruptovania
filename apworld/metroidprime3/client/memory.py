"""Memory access to Dolphin/PrimeHack (T06, SPEC E6).

``MemoryAccess`` wraps every access to Wii memory. The client logic only uses this class. Subclasses replace the four
primitives ``_hook``, ``_unhook``, ``_is_hooked``, ``_read`` (and ``_write``): ``DolphinMemory`` talks to Dolphin or
PrimeHack through ``dolphin-memory-engine``, the tests use a fake memory (``test/fake_memory.py``).

Rules:
- Nothing is read or written before the game ID ``RM3P01`` has been checked (``connect``). On a wrong ID the client
  disconnects at once and writes nothing.
- Addresses outside MEM1/MEM2 are rejected (``AddressError``) instead of asking Dolphin for them.
- Any backend error while reading/writing counts as a lost connection (``ConnectionLost``); the caller reconnects.
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

SCAN_CHUNK = 0x100000  # 1 MiB per read while scanning (same as the T10 snapshots)


class MemoryAccessError(Exception):
    """Base class of all memory errors."""


class NotConnected(MemoryAccessError):
    """Access without a verified connection."""


class ConnectionLost(MemoryAccessError):
    """The backend reported an error while reading/writing (Dolphin closed, emulation stopped, ...)."""


class AddressError(MemoryAccessError):
    """Address is not in MEM1/MEM2."""


class ConnectStatus(enum.Enum):
    CONNECTED = "connected"
    NO_DOLPHIN = "no_dolphin"  # no Dolphin/PrimeHack found
    NO_GAME = "no_game"  # Dolphin runs, but nothing is emulated
    WRONG_GAME = "wrong_game"  # other game or other region


@dataclass(frozen=True)
class ConnectResult:
    status: ConnectStatus
    game_id: bytes = b""

    @property
    def message(self) -> str:
        if self.status is ConnectStatus.CONNECTED:
            return f"Connected to Dolphin, game {EXPECTED_GAME_ID.decode()} detected."
        if self.status is ConnectStatus.NO_DOLPHIN:
            return "Dolphin/PrimeHack not found. Please start the emulator."
        if self.status is ConnectStatus.NO_GAME:
            return "Dolphin is running, but no game is being emulated. Please start the patched MP3 ISO."
        shown = self.game_id.decode("ascii", "replace") if self.game_id else "?"
        return (f"Wrong game in Dolphin: game ID {shown!r}, expected {EXPECTED_GAME_ID.decode()!r} "
                f"(Metroid Prime 3 PAL). The client reads and writes nothing.")


def in_ram(address: int, size: int = 1) -> bool:
    end = address + size
    return (MEM1_START <= address and end <= MEM1_START + MEM1_SIZE) or (
        MEM2_START <= address and end <= MEM2_START + MEM2_SIZE)


class MemoryAccess:
    """Wrapped Wii memory. Subclasses only implement the primitives."""

    expected_game_id: bytes = EXPECTED_GAME_ID

    def __init__(self) -> None:
        self.verified = False
        self.last_game_id = b""

    # ---- primitives (subclasses) ------------------------------------------------------------------------------- #

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

    # ---- connection -------------------------------------------------------------------------------------------- #

    @property
    def connected(self) -> bool:
        if not self.verified:
            return False
        try:
            return self._is_hooked()
        except Exception:  # noqa: BLE001 - backend error = disconnected
            self.verified = False
            return False

    def connect(self) -> ConnectResult:
        """Hooks Dolphin and checks the game ID. Any mismatch disconnects again."""
        self.verified = False
        try:
            if not self._is_hooked():
                self._hook()
            if not self._is_hooked():
                return ConnectResult(ConnectStatus.NO_DOLPHIN)
            game_id = self._read(GAME_ID_ADDRESS, len(self.expected_game_id))
        except Exception:  # noqa: BLE001 - dme raises RuntimeError when nothing is emulated
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
        """Reads the game ID again (game switched in a running Dolphin). On a mismatch: disconnect, ``False``."""
        game_id = self.read(GAME_ID_ADDRESS, len(self.expected_game_id))
        if game_id != self.expected_game_id:
            self.last_game_id = bytes(game_id)
            self.disconnect()
            return False
        return True

    # ---- read / write ------------------------------------------------------------------------------------------ #

    def read(self, address: int, size: int) -> bytes:
        if not self.verified:
            raise NotConnected("memory access without a verified connection")
        if size <= 0 or not in_ram(address, size):
            raise AddressError(f"range 0x{address:08X}+0x{size:X} is not in MEM1/MEM2")
        try:
            data = self._read(address, size)
        except Exception as exc:  # noqa: BLE001
            self.verified = False
            raise ConnectionLost(f"read at 0x{address:08X} failed: {exc}") from exc
        if len(data) != size:
            self.verified = False
            raise ConnectionLost(f"read at 0x{address:08X}: {len(data)} instead of {size} bytes")
        return bytes(data)

    def write(self, address: int, data: bytes) -> None:
        """Write (used for item giving, T07). Checks the game ID once more first."""
        if not self.verified:
            raise NotConnected("write without a verified connection")
        if not data or not in_ram(address, len(data)):
            raise AddressError(f"range 0x{address:08X}+0x{len(data):X} is not in MEM1/MEM2")
        if not self.check_game_id():
            raise NotConnected("game ID changed, write aborted")
        try:
            self._write(address, bytes(data))
        except Exception as exc:  # noqa: BLE001
            self.verified = False
            raise ConnectionLost(f"write at 0x{address:08X} failed: {exc}") from exc

    def read_u32(self, address: int) -> int:
        return struct.unpack(">I", self.read(address, 4))[0]

    def read_u64(self, address: int) -> int:
        return struct.unpack(">Q", self.read(address, 8))[0]

    def read_pointer(self, address: int) -> int | None:
        """Read a 4-byte pointer. ``None`` if it does not point into MEM1/MEM2 (e.g. 0 in the menu)."""
        value = self.read_u32(address)
        return value if in_ram(value) else None

    def iter_chunks(self, start: int, size: int, overlap: int = 0, chunk: int = SCAN_CHUNK):
        """Reads ``[start, start+size)`` in chunks. Yields ``(address, data)``; consecutive chunks overlap by
        ``overlap`` bytes so that patterns across chunk borders are found."""
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
    """Real access through ``dolphin-memory-engine`` (Dolphin and PrimeHack)."""

    def __init__(self) -> None:
        super().__init__()
        try:
            import dolphin_memory_engine
        except ImportError as exc:  # pragma: no cover - only without the dependency
            raise ImportError(
                "The package 'dolphin-memory-engine' is missing. Install it with: "
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
