"""
One-shot inspector: prints both the raw hex dump AND the full decoded
output for a .pk1, .pk2, or .pk3 file, in a single command. Auto-detects
which decoder to use from the file extension.

Usage:
    python3 inspect_pk.py 
    python3 inspect_pk.py path/to/file.pk1
    python3 inspect_pk.py path/to/file.pk2
    python3 inspect_pk.py path/to/file.pk3
    python3 inspect_pk.py "/path/to/folder" > results.txt
    python3 inspect_pk.py "/path/to/folder" > name your file.txt !THIS ENDS UP IN THE FOLDER DIRECTORY IN TERMINAL, NOT THE FOLDER OF THE .PK FILES!

This replaces running the hex-dump one-liner and test_pk*.py as two
separate steps -- point it at a file once and get everything.
"""
import sys
import glob
import os

from pk_reader import read_pk_file
from pk_reader.species_data import dex_type, met_location_name, move_name, egg_location_name


def print_hex_dump(raw: bytes):
    print(f"--- Hex dump ({len(raw)} bytes) ---")
    for i in range(0, len(raw), 16):
        chunk = raw[i:i + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        print(f"{i:04d}: {hex_part}")


def print_decoded(data: dict):
    print("\n--- Decoded ---")
    gen = data["generation"]

    print(f"Generation:       {gen}")
    if "pid" in data:
        print(f"PID:              {data['pid']:#010x}")
    print(f"National Dex #:   {data['national_dex']} - {data.get('species_name') or '(name not in reference table)'}")

    if gen == 1:
        print(f"Internal index:   {data['internal_index']}")
    elif gen >= 3:
        print(f"Internal index:   {data['internal_index']}")
        print(f"Checksum valid:   {data['checksum_valid']}  (self-check: recomputed checksum matches the stored one)")
        print(f"Is egg:           {data['is_egg']}")

    type1 = data.get("type1_name") or data.get("type1")
    type2 = data.get("type2_name") or data.get("type2")
    if type1 is None and data.get("national_dex") and data.get("species_confident", True):
        type1, type2 = dex_type(data["national_dex"])
    if type1 is not None:
        type_str = type1 if (type2 is None or type2 == type1) else f"{type1} / {type2}"
        print(f"Type:             {type_str}")
    else:
        print("Type:             (not in reference table for this species yet)")

    if data.get("nature"):
        print(f"Nature:           {data['nature']}")

    if data.get("ability"):
        id_str = f"  (ID {data['ability_id']})" if "ability_id" in data else ""
        hidden_str = "  [Hidden Ability]" if data.get("hidden_ability") else ""
        print(f"Ability:          {data['ability']}{id_str}{hidden_str}")

    if "gender" in data:
        print(f"Gender:           {data['gender']}")

    if "level" in data:
        print(f"Level:            {data['level']}" + (f" (party copy: {data['party_level']})" if "party_level" in data else ""))
    if "hp_current" in data or "hp_max" in data:
        hp_cur = data.get('hp_current', '?')
        hp_max = data.get('hp_max', '(not computed)')
        print(f"HP current/max:   {hp_cur} / {hp_max}")

    if gen == 1:
        print(f"Stats (atk/def/spe/spc): {data['stat_atk']}/{data['stat_def']}/{data['stat_spe']}/{data['stat_spc']}")
    elif any(k in data for k in ('stat_atk', 'stat_spa')):
        atk = data.get('stat_atk', '?')
        def_ = data.get('stat_def', '?')
        spe = data.get('stat_spe', '?')
        spa = data.get('stat_spa', '?')
        spd = data.get('stat_spd', '?')
        print(f"Stats (atk/def/spe/spa/spd): {atk}/{def_}/{spe}/{spa}/{spd}")

    if "status_condition" in data:
        print(f"Status condition: {data['status_condition']}")
    if "catch_rate" in data:
        print(f"Catch rate:       {data['catch_rate']}")
    if "held_item" in data:
        print(f"Held item:        {data.get('held_item_name') or 'None'}  (ID {data['held_item']})")

    if "ball" in data:
        print(f"Poké Ball:        {data.get('ball_name', data['ball'])}")

    if "origin_game" in data:
        print(f"Game of origin:   {data['origin_game']}")

    names = [n for n in (data.get("move_names") or [move_name(m) for m in data["moves"] if m]) if n]
    print(f"Moves:            {data['moves']}  {names}")
    print(f"Move PP:          {data['move_pp']}")
    print(f"Move PP Ups:      {data['move_pp_ups']}")

    print(f"Trainer ID:       {data['trainer_id']}" + (f" / Secret ID: {data['secret_id']}" if "secret_id" in data else ""))
    print(f"Experience:       {data['experience']}")

    if gen >= 3:
        print(f"EVs (hp/atk/def/spe/spa/spd): {data['ev_hp']}/{data['ev_atk']}/{data['ev_def']}/{data['ev_spe']}/{data['ev_spa']}/{data['ev_spd']}")
        print(f"IVs (hp/atk/def/spe/spa/spd): {data['iv_hp']}/{data['iv_atk']}/{data['iv_def']}/{data['iv_spe']}/{data['iv_spa']}/{data['iv_spd']}")
        if data.get("hyper_trained"):
            print(f"Hyper Trained:    {', '.join(data['hyper_trained'])}")
    else:
        print(f"EVs (hp/atk/def/spe/spc): {data['ev_hp']}/{data['ev_atk']}/{data['ev_def']}/{data['ev_spe']}/{data['ev_spc']}")
        print(f"IVs (hp/atk/def/spe/spc): {data['iv_hp']}/{data['iv_atk']}/{data['iv_def']}/{data['iv_spe']}/{data['iv_spc']}")

    if "is_shiny" in data:
        print(f"Shiny:            {data['is_shiny']}")

    if "friendship" in data:
        print(f"Friendship:       {data['friendship']}")
    if "pokerus_strain" in data:
        print(f"Pokerus:          strain {data['pokerus_strain']}, {data['pokerus_days']} days")
    if "ribbons" in data:
        print(f"Ribbons:          {', '.join(data['ribbons']) or 'None'}")
        if data.get("ribbons_unknown_bits"):
            print(f"Unknown ribbon bits: {', '.join(data['ribbons_unknown_bits'])}")
    if "met_level" in data:
        loc_name = met_location_name(data)
        loc_str = f"{data.get('met_location')}" + (f" = {loc_name}" if loc_name else "")
        if data.get("met_loc_source"):
            loc_str += f" (from {data['met_loc_source']})"
        tod = ""
        if "met_time_of_day_name" in data:   # Gen 2 (Crystal) only
            tod = f", time of day: {data['met_time_of_day_name'] or 'not recorded'}"
        print(f"Met level:        {data['met_level']} (met location: {loc_str}{tod})")

    if data.get("egg_date"):
        ey, em, ed = data["egg_date"]
        egg_loc = egg_location_name(data)
        print(f"Egg received:     {ey}-{em:02d}-{ed:02d}" + (f" at {egg_loc}" if egg_loc else ""))
        if data.get("met_date") and not data.get("is_egg"):
            hy, hm, hd = data["met_date"]
            hatch_loc = met_location_name(data)
            print(f"Hatched:          {hy}-{hm:02d}-{hd:02d}" + (f" at {hatch_loc}" if hatch_loc else ""))

    print(f"OT name:          {data['ot_name']!r}")
    if data.get("is_ns_pokemon"):
        print("N's Pokémon:      Yes")
    if gen == 1:
        print(f"OT trash bytes:   {data['ot_trash']!r}  (leftover menu-selection garbage, not real data)")
    elif gen == 2:
        print(f"Unidentified field: {data.get('unidentified_field')!r}  (not yet confirmed what this is for Gen 2)")
    print(f"Nickname:         {data['nickname']!r}")
    if data.get("home_location"):   # Gen 6/7
        console = f" (3DS region: {data['console_region_name']})" if data.get("console_region_name") else ""
        print(f"Trainer's home:   {data['home_location']}{console}")
    if data.get("ot_memory"):
        print(f"OT memory:        {data['ot_memory']}")
    if data.get("handler_name"):
        print(f"Last other trainer: {data['handler_name']!r}" + (f", friendship {data['ht_friendship']}" if "ht_friendship" in data else ""))
    if data.get("ht_memory"):
        print(f"Their memory:     {data['ht_memory']}")
    if data.get("geolocations"):
        print(f"Places it lived:  {' / '.join(data['geolocations'])}")
    if gen < 3:
        print(f"All text strings found: {data['text_strings']!r}")
        if data.get("trailing_noise"):
            print(f"Trailing noise (likely not real text): {data['trailing_noise']!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 inspect_pk.py file1.pk3 [file2.pk2 ...]  (or a folder)")
        sys.exit(1)

    paths = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            paths.extend(sorted(glob.glob(os.path.join(arg, "*.pk[0-9]"))))
        else:
            paths.append(arg)

    for path in paths:
        print("=" * 60)
        print(f"FILE: {path}")
        print("=" * 60)
        try:
            with open(path, "rb") as f:
                raw = f.read()
            print_hex_dump(raw)
            data = read_pk_file(path)
            print_decoded(data)
        except Exception as e:
            print(f"\n--- Failed: {e} ---")
        print()