"""Entry point.

In the Archipelago folder: ``python -m worlds.metroidprime3.patcher --patch ... --iso ... --out ...``.
Without Archipelago (any Python >= 3.10, stdlib only): ``python apworld/metroidprime3/patcher --patch ...``.
"""

import sys

if __package__:
    from .cli import main
else:
    # Run as a folder script: make this folder importable as the package "patcher" without importing the World
    # (apworld/metroidprime3/__init__.py needs Archipelago).
    from pathlib import Path

    sys.path[0] = str(Path(__file__).resolve().parent.parent)
    from patcher.cli import main  # type: ignore[no-redef]

sys.exit(main())
