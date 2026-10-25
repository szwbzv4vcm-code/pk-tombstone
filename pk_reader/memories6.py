"""Gen 6/7 memories, geolocations and home country (shared by gen6.py and gen7.py).

Offsets and tables verified with PKHeX-made files (same layout in .pk6 and .pk7):
  0x92 handler gender, 0x94-0x9D Geo1-Geo5 (region, country pairs), 0xA2 handler friendship,
  0xA3 handler affection, 0xA4 handler memory intensity, 0xA5 handler memory, 0xA6 handler
  feeling, 0xA8 handler memory variable (2 bytes), 0xAE fullness, 0xAF enjoyment,
  0xCB OT affection, 0xCC OT intensity, 0xCD OT memory, 0xCE OT memory variable (2 bytes),
  0xD0 OT feeling, 0xE0 country, 0xE1 region, 0xE2 3DS console region.
Text tables (memory_text_gen6_7.csv, geolocation_3ds.csv) were exported from PKHeX's English text.
"""
import csv
import os
import struct

from .species_data import dex_name, move_name, item_name_gen

_DIR = os.path.dirname(__file__)

_MEM = {}        # (kind, id) -> text; kinds: memory, feeling, intensity, general_location, specific_location
_MEM_VAR = {}    # memory id -> what {2} stands for (GeneralLocation, SpecificLocation, Species, Move, Item, None)
with open(os.path.join(_DIR, "memory_text_gen6_7.csv"), newline="", encoding="utf-8-sig") as _f:
    for _row in csv.DictReader(_f):
        _MEM[(_row["kind"], int(_row["id"]))] = _row["text"]
        if _row["kind"] == "memory":
            _MEM_VAR[int(_row["id"])] = _row["variable_type"]

_COUNTRY, _REGION = {}, {}
with open(os.path.join(_DIR, "geolocation_3ds.csv"), newline="", encoding="utf-8-sig") as _f:
    for _row in csv.DictReader(_f):
        if _row["region_id"]:
            _REGION[(int(_row["country_id"]), int(_row["region_id"]))] = _row["name"]
        else:
            _COUNTRY[int(_row["country_id"])] = _row["name"]

CONSOLE_REGIONS = {0: "Japan", 1: "Americas", 2: "Europe", 4: "China", 5: "Korea", 6: "Taiwan"}


def place_name(country, region):
    """'Arkansas, United States', just the country when there is no region, or None."""
    c = _COUNTRY.get(country)
    if not c:
        return None
    r = _REGION.get((country, region))
    return f"{r}, {c}" if r and r != "—" else c


def _variable_text(memory, var):
    kind = _MEM_VAR.get(memory, "None")
    if not var:   # no place/species/item stored (common on Gen 7 trades), so that part is left out
        return ""
    if kind == "GeneralLocation":
        return _MEM.get(("general_location", var), f"(place {var})")
    if kind == "SpecificLocation":
        return _MEM.get(("specific_location", var), f"(location {var})")
    if kind == "Species":
        return dex_name(var) or f"(species {var})"
    if kind == "Move":
        return move_name(var) or f"(move {var})"
    if kind == "Item":
        return item_name_gen(6, var) or f"(item {var})"
    return ""


def memory_sentence(memory, var, feeling, intensity, nickname, trainer):
    """The memory as the game's summary screen words it, or None when there is no memory."""
    if not memory or ("memory", memory) not in _MEM:
        return None
    text = _MEM[("memory", memory)].format(
        nickname, trainer, _variable_text(memory, var),
        _MEM.get(("feeling", feeling), "?"), _MEM.get(("intensity", intensity), "The Pokémon remembers"))
    return text.replace(" .", ".")


def memory_fields(d, nickname, ot_name, handler_name):
    ot_mem, ot_var, ot_feel, ot_int = d[0xCD], struct.unpack_from("<H", d, 0xCE)[0], d[0xD0], d[0xCC]
    ht_mem, ht_var, ht_feel, ht_int = d[0xA5], struct.unpack_from("<H", d, 0xA8)[0], d[0xA6], d[0xA4]
    geos = [place_name(d[0x95 + 2 * i], d[0x94 + 2 * i]) for i in range(5)]
    return {
        "ot_memory_id": ot_mem, "ot_memory_variable": ot_var,
        "ot_memory_feeling": ot_feel, "ot_memory_intensity": ot_int,
        "ot_memory": memory_sentence(ot_mem, ot_var, ot_feel, ot_int, nickname, ot_name),
        "ht_memory_id": ht_mem, "ht_memory_variable": ht_var,
        "ht_memory_feeling": ht_feel, "ht_memory_intensity": ht_int,
        "ht_memory": memory_sentence(ht_mem, ht_var, ht_feel, ht_int, nickname, handler_name),
        "handler_gender": d[0x92],
        "ht_friendship": d[0xA2],
        "ht_affection": d[0xA3],
        "ot_affection": d[0xCB],
        "fullness": d[0xAE],
        "enjoyment": d[0xAF],
        "geolocations": [g for g in geos if g],
        "country": d[0xE0],
        "region": d[0xE1],
        "country_name": _COUNTRY.get(d[0xE0]),
        "home_location": place_name(d[0xE0], d[0xE1]),
        "console_region": d[0xE2],
        "console_region_name": CONSOLE_REGIONS.get(d[0xE2]),
    }
