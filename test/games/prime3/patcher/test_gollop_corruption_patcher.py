from __future__ import annotations

import hashlib
import re
from pathlib import Path

from randovania.games.prime3.patcher import gollop_corruption_patcher
from randovania.games.prime3.patcher.corruption_items import AP_ITEM

_DECODER = (
    Path(__file__).parents[4] / "tools" / "prime3_patcher" / "MP3Randomizer" / "MP3Randomizer" / "MP3Permalink.cs"
)


def test_ap_item_letter() -> None:
    assert gollop_corruption_patcher.LETTER_TO_ITEM_MAPPING["A"] == [AP_ITEM]
    assert gollop_corruption_patcher.ITEM_NAME_TO_LETTER_MAPPING[AP_ITEM] == "A"
    assert "A" in gollop_corruption_patcher.LAYOUT_LETTERS


def test_layout_string_with_ap_item() -> None:
    items = ["Plasma Beam", AP_ITEM, "Missile Expansion"] + ["Missile Expansion"] * 97

    result = gollop_corruption_patcher.layout_string_for_items(items)

    body = "00" + "1A4" + "4" * 97
    assert result == body + hashlib.sha256(body.encode("ascii")).hexdigest()[:5]


def test_layout_string_without_ap_item_unchanged() -> None:
    # Reference value computed before T16 (seed IVG2J7OR, docs/AP_DEV_SETUP.md section 4).
    seed = "00kk44g44xtk944sdk444Cko{4rk^44}{4D447h44444444448uy44vk4Ik4444II44IIp4qk444B444kzII}44e#I4kk44H4k4n4kc602b"
    mapping = gollop_corruption_patcher.LETTER_TO_ITEM_MAPPING
    letter_to_single = {letter: items[0] for letter, items in mapping.items() if len(items) == 1}

    items = [letter_to_single[letter] for letter in seed[2:-5]]

    assert gollop_corruption_patcher.layout_string_for_items(items) == seed


def test_ap_mode_arguments() -> None:
    assert gollop_corruption_patcher.ap_mode_arguments(True) == ("--ap-mode",)
    assert gollop_corruption_patcher.ap_mode_arguments(False) == ()


def test_python_letters_are_known_to_the_csharp_decoder() -> None:
    decoder_letters = set(re.findall(r"case '(.)':", _DECODER.read_text(encoding="utf-8")))

    python_letters = set(gollop_corruption_patcher.LETTER_TO_ITEM_MAPPING)

    # "0" (Power Beam) and "L" (CannonBall) are known gaps of the C# decoder (docs/AP_PATCHER_NOTES.md, 1.5).
    assert python_letters - decoder_letters == {"0", "L"}
    assert "A" in decoder_letters
