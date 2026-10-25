"""Build pk_reader/palette_table.csv: the 6 main colors of each official-artwork image.

Run:  python3 make_palette_table.py [official-artwork folder]
Colors are ordered by how much of the Pokemon they cover (color_1 = biggest).
Transparent background and the dark outline are ignored.
"""
import csv
import os
import sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
# Official-artwork folder (with its "shiny" subfolder): the first argument, or where the
# README's PokeAPI download commands put it
ART = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/pokeapi-sprites/sprites/pokemon/other/official-artwork")
OUT = os.path.join(HERE, "pk_reader", "palette_table.csv")
NUM_COLORS = 6
START_CLUSTERS = 16      # find more groups first, then merge look-alikes
MERGE_DISTANCE = 45      # groups closer than this (in RGB) count as one color
OUTLINE_BRIGHTNESS = 45  # pixels darker than this are treated as outline


def kmeans(pixels, k, rounds=20):
    rng = np.random.default_rng(0)
    centers = [pixels[rng.integers(len(pixels))]]
    for _ in range(1, k):  # k-means++ start: spread the first guesses out
        d = np.min(((pixels[:, None] - np.array(centers)[None]) ** 2).sum(2), axis=1)
        centers.append(pixels[rng.choice(len(pixels), p=d / d.sum())])
    centers = np.array(centers, float)
    for _ in range(rounds):
        labels = ((pixels[:, None] - centers[None]) ** 2).sum(2).argmin(1)
        for i in range(k):
            if (labels == i).any():
                centers[i] = pixels[labels == i].mean(0)
    return centers, np.bincount(labels, minlength=k)


def palette(path):
    im = Image.open(path).convert("RGBA")
    im.thumbnail((160, 160))
    a = np.asarray(im).reshape(-1, 4).astype(float)
    px = a[a[:, 3] > 128][:, :3]
    bright = px @ [0.299, 0.587, 0.114]
    if (bright > OUTLINE_BRIGHTNESS).sum() > 50:  # keep dark pixels for all-black art
        px = px[bright > OUTLINE_BRIGHTNESS]
    if len(px) < START_CLUSTERS:
        return []
    centers, counts = kmeans(px, START_CLUSTERS)
    groups = []  # merge look-alike groups, biggest first
    for i in np.argsort(-counts):
        if counts[i] == 0:
            continue
        for g in groups:
            if np.linalg.norm(g[0] - centers[i]) < MERGE_DISTANCE:
                g[0] = (g[0] * g[1] + centers[i] * counts[i]) / (g[1] + counts[i])
                g[1] += counts[i]
                break
        else:
            groups.append([centers[i].copy(), counts[i]])
    groups.sort(key=lambda g: -g[1])
    return ["#%02X%02X%02X" % tuple(int(round(v)) for v in g[0]) for g in groups[:NUM_COLORS]]


def sort_key(name):
    num, _, rest = name.partition("-")
    return (int(num) if num.isdigit() else 99999, rest)


rows = []
for version, folder in (("normal", ART), ("shiny", os.path.join(ART, "shiny"))):
    names = sorted((f[:-4] for f in os.listdir(folder) if f.lower().endswith(".png")), key=sort_key)
    for n, name in enumerate(names, 1):
        colors = palette(os.path.join(folder, name + ".png"))
        rows.append([name, version] + colors + [""] * (NUM_COLORS - len(colors)))
        if n % 200 == 0:
            print(version, n, "of", len(names))

with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["art_key", "version"] + ["color_%d" % i for i in range(1, NUM_COLORS + 1)])
    w.writerows(rows)
print("Wrote", len(rows), "rows to", OUT)
