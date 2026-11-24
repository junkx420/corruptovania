"""Layout string ("seed") for MP3Randomizer: one letter per pickup index plus a 5-character checksum.

Own copy for the APWorld, which must not depend on Randovania at runtime (SPEC 3a).
Origin: ``randovania/games/prime3/patcher/gollop_corruption_patcher.py`` (Corruptovania, branch ``archipelago``,
state of commit ``f348f00bf`` / T16): ``LAYOUT_LETTERS``, ``LETTER_TO_ITEM_MAPPING``,
``ITEM_NAME_TO_LETTER_MAPPING`` and ``layout_string_for_items`` are copied unchanged, ``AP_ITEM`` comes from
``randovania/games/prime3/patcher/corruption_items.py``. ``test/test_patcher_layout.py`` compares this copy with the
original, so any change there shows up as a failing test.
"""

from __future__ import annotations

import hashlib

# Display name of the neutral Archipelago placeholder (T16, ItemName.APItem in the C# patcher, letter "A").
AP_ITEM = "Archipelago Item"

LAYOUT_LETTERS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ(){}[]<>=,.!#^-+?"

LETTER_TO_ITEM_MAPPING = {
    "0": ["Power Beam"],
    "1": ["Plasma Beam"],
    "2": ["Nova Beam"],
    "3": ["Charge Beam"],
    "4": ["Missile Expansion"],
    "5": ["Ice Missile"],
    "6": ["Seeker Missile"],
    "7": ["Grapple Lasso"],
    "8": ["Grapple Swing"],
    "9": ["Grapple Voltage"],
    "a": ["Morph Ball Bombs"],
    "b": ["Combat Visor"],
    "c": ["Scan Visor"],
    "d": ["Command Visor"],
    "e": ["X-Ray Visor"],
    "f": ["Space Jump Boots"],
    "g": ["Screw Attack"],
    "h": ["Hazard Shield"],
    # "i": ["Energy"],
    # "j": ["HyperModeEnergy"],
    "k": ["Energy Tank"],
    # "l": ["ItemPercentage"],
    # "m": ["Fuses"],
    "n": ["Energy Cell 1"],
    "o": ["Energy Cell 2"],
    "p": ["Energy Cell 3"],
    "q": ["Energy Cell 4"],
    "r": ["Energy Cell 5"],
    "s": ["Energy Cell 6"],
    "t": ["Energy Cell 7"],
    "u": ["Energy Cell 8"],
    "v": ["Energy Cell 9"],
    "w": ["Morph Ball"],
    "x": ["Boost Ball"],
    "y": ["Spider Ball"],
    "z": ["Hypermode"],
    # "A" was the unused slot HyperModeBeam; the patcher decodes it as ItemName.APItem.
    "A": [AP_ITEM],
    "B": ["Hyper Missile"],
    "C": ["Hyper Ball"],
    "D": ["Hyper Grapple"],
    # "E": ["HyperModePermanent"],
    # "F": ["HyperModePhaaze"],
    # "G": ["HyperModeOriginal"],
    "H": ["Ship Grapple"],
    "I": ["Ship Missile Expansion"],
    # "J": ["FaceCorruptionLevel"],
    # "K": ["PhazonBall"],
    "L": ["CannonBall"],
    # "M": ["ActivateMorphballBoost"],
    # "N": ["HyperShot"],
    # "O": ["CommandVisorJammed"],
    # "P": ["Stat_Enemies_Killed"],
    # "Q": ["Stat_ShotsFired"],
    # "R": ["Stat_DamageReceived"],
    # "S": ["Stat_DataSaves"],
    # "T": ["Stat_HypermodeUses"],
    # "U": ["Stat_CommandoKills"],
    # "V": ["Stat_TinCanHighScore"],
    # "W": ["Stat_TinCanCurrentScore"],
    "X": ["Missile Expansion"] * 2,
    "Y": ["Missile Expansion"] * 3,
    "Z": ["Missile Expansion"] * 4,
    "(": ["Missile Expansion"] * 5,
    ")": ["Missile Expansion"] * 6,
    "{": ["Progressive Missile"],
    "}": ["Progressive Beam"],
    "[": ["Energy Tank", "Energy Tank"],
    "]": ["Energy Tank", "Energy Tank", "Energy Tank"],
    "<": ["Ship Missile Expansion", "Ship Missile Expansion"],
    ">": ["Missile Expansion", "Energy Tank"],
    "=": ["Energy Tank", "Missile Expansion"],
    ",": ["Missile Expansion", "Energy Tank", "Missile Expansion"],
    ".": ["Missile Expansion", "Ship Missile Expansion"],
    "!": ["Ship Missile Expansion", "Missile Expansion"],
    "#": ["Missile Launcher"],
    "^": ["Ship Missile"],
    "-": ["Ship Missile Expansion", "Energy Tank"],
    "+": ["Energy Tank", "Ship Missile Expansion"],
    "?": ["Missile Expansion", "Ship Missile Expansion", "Missile Expansion"],
}
ITEM_NAME_TO_LETTER_MAPPING = {items[0]: letter for letter, items in LETTER_TO_ITEM_MAPPING.items() if len(items) == 1}


def layout_string_for_items(item_names: list[str]) -> str:
    letters = [LAYOUT_LETTERS[0]] * 2
    for item in item_names:
        letters.append(ITEM_NAME_TO_LETTER_MAPPING[item])

    result = "".join(letters)
    sha = hashlib.sha256(result.encode("ascii"))
    result += sha.hexdigest()[:5]

    return result


# --- AP additions (not part of the Randovania copy) ---------------------------------------------------------------

# Number of pickup indices the patcher decodes (0-99). Index 0 is never patched (SPEC E13).
PICKUP_COUNT = 100
# Letter for index 0: its vanilla item (Hypermode, data/locations.py UNPATCHED_LOCATION). The patcher ignores it.
LOCATION_0_ITEM = "Hypermode"

# Letters the C# decoder (MP3Permalink.cs) does not know: "0" (Power Beam) and "L" (CannonBall), see
# docs/AP_PATCHER_NOTES.md 1.5. A pickup showing one of these would not decode, so the patch tool rejects them.
UNDECODABLE_ITEMS = frozenset({"Power Beam", "CannonBall"})

# Item names a pickup may show in an AP patch: every single-item letter the patcher can decode.
DISPLAYABLE_ITEMS = frozenset(name for name in ITEM_NAME_TO_LETTER_MAPPING if name not in UNDECODABLE_ITEMS)


def layout_string_for_pickups(pickups: dict[int, str], location_0_item: str = LOCATION_0_ITEM) -> str:
    """Layout string from ``{pickup index 1-99: display item name}``; index 0 gets ``location_0_item``."""
    missing = [index for index in range(1, PICKUP_COUNT) if index not in pickups]
    extra = sorted(set(pickups) - set(range(1, PICKUP_COUNT)))
    if missing or extra:
        raise ValueError(f"pickups must cover exactly the indices 1-99 (missing {missing}, unexpected {extra})")
    names = [location_0_item] + [pickups[index] for index in range(1, PICKUP_COUNT)]
    return layout_string_for_items(names)
