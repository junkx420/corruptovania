import importlib.util
from pathlib import Path
from types import ModuleType

from test.bases import WorldTestBase

from ..items import GAME_NAME

# apworld/tools/playthrough_sim.py (T20). Only present in a source checkout of the corruptovania repo; resolve()
# follows the junction/symlink from Archipelago/worlds/metroidprime3 back into the repo.
SIM_PATH = Path(__file__).resolve().parents[2] / "tools" / "playthrough_sim.py"


def load_playthrough_sim() -> ModuleType | None:
    if not SIM_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_mp3_playthrough_sim", SIM_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MP3TestBase(WorldTestBase):
    game = GAME_NAME
