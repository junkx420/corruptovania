"""Metroid Prime 3 Client (T06): Dolphin/PrimeHack <-> Archipelago-Server. Doku: docs/AP_CLIENT.md.

Module:
- ``memory``     gekapselter Speicherzugriff (``MemoryAccess``, ``DolphinMemory``), Game-ID-Prüfung
- ``game``       Spielzustand (ingame/Menü, Welt, ItemPercentage)
- ``flag_block`` Signatursuche des Flag-Blocks je Welt (E8)
- ``checks``     Flag-Byte -> Location (E12), Entprellung
- ``learning``   Lernmodus (E19)
- ``context``    CommonClient-Kontext, Polling-Schleife, ``main``

``context`` importiert CommonClient und wird deshalb erst beim Start geladen.
"""


def launch(*args: str) -> None:
    from .context import main
    main(*args)
