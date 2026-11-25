"""Metroid Prime 3 Client (T06, T07): Dolphin/PrimeHack <-> Archipelago server. Docs: docs/AP_CLIENT.md.

Modules:
- ``memory``     wrapped memory access (``MemoryAccess``, ``DolphinMemory``), game ID check
- ``game``       game state (ingame/menu, world, ItemPercentage)
- ``flag_block`` signature search of the flag block per world (E8)
- ``checks``     flag byte -> location (E12), debouncing
- ``learning``   learning mode (E19)
- ``inventory``  effect table item -> slots, slot limits, target values and write plan (E9, E11)
- ``give``       item giving per poll: settling, writing, read-back, throttling
- ``seed_check`` seed ID in RAM against seed/slot of the server (T18 part 2)
- ``goal``       goal detection (interface, open until T17)
- ``context``    CommonClient context, poll loop, ``main``

``context`` imports CommonClient and is therefore only loaded on start.
"""


def launch(*args: str) -> None:
    from .context import main
    main(*args)
