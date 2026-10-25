"""
Character encoding table for Generation I/II Pokémon games (English/Western
version). These games do NOT store names as ASCII or Unicode -- each byte
indexes this proprietary table instead.

Source: Bulbapedia, "Character encoding (Generation I)" -- public community
documentation of the game's ROM tile-character mapping, independently
reverse-engineered and published for reimplementation. Not derived from any
existing tool's source code.

Only the core Western-language alphanumeric range is implemented -- enough
for typical English nicknames/OT names. Accented letters, contractions
(0xBA-0xBF, 0xE4-0xE5) and a few static-display codes are included since
they're common in real names; anything else decodes as "?" rather than
raising, so an unusual byte doesn't crash the whole read.
"""

TERMINATOR = 0x50  # Marks the end of a name; also used to pad shorter names
SPACE = 0x7F

GEN1_2_CHAR_MAP = {SPACE: " "}

# 0x80-0x99: A-Z
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    GEN1_2_CHAR_MAP[0x80 + _i] = _c

# 0xA0-0xB9: a-z
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    GEN1_2_CHAR_MAP[0xA0 + _i] = _c

# 0xF6-0xFF: 0-9
for _i, _c in enumerate("0123456789"):
    GEN1_2_CHAR_MAP[0xF6 + _i] = _c

GEN1_2_CHAR_MAP.update({
    0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";", 0x9E: "[", 0x9F: "]",
    0xBA: "é", 0xBB: "'d", 0xBC: "'l", 0xBD: "'s", 0xBE: "'t", 0xBF: "'v",
    0xE0: "'", 0xE1: "PK", 0xE2: "MN", 0xE3: "-",
    0xE4: "'r", 0xE5: "'m", 0xE6: "?", 0xE7: "!", 0xE8: ".",
    0xEF: "♂", 0xF5: "♀",   # verified with PKHeX
})


def decode_gen1_2_string(data: bytes) -> str:
    """Decodes a fixed-width Gen 1/2 name field into a plain Python string,
    stopping at the 0x50 terminator (or the end of the given bytes)."""
    out = []
    for b in data:
        if b == TERMINATOR:
            break
        out.append(GEN1_2_CHAR_MAP.get(b, "?"))
    return "".join(out)
