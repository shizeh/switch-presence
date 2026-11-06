"""
Prépare en masse les jaquettes pour Discord.

Utilisation :
    1. Mets toutes tes images dans un dossier. Nomme chaque fichier avec le NOM DU JEU,
       par exemple : "Super Mario Odyssey.jpg", "Pokémon Épée.png"
    2. Lance :  python prepare_covers.py "C:\\chemin\\vers\\mon_dossier"
    3. Résultat :
       - assets/covers/ : images carrées 512x512, prêtes à uploader d'un coup dans Art Assets
       - games_snippet.txt : les lignes à coller dans la liste "games" de games.json
       (un " - " dans le nom de fichier devient ": " dans le titre du jeu)

Nécessite Pillow :  python -m pip install pillow
"""
import os
import re
import sys
import unicodedata

from PIL import Image

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SIZE = 512
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "covers")


def slugify(name):
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:30] or "game"


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        print(__doc__)
        sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    used, lines = {}, []
    for fn in sorted(os.listdir(sys.argv[1])):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in EXTS:
            continue
        key = slugify(stem)
        if key in used:
            print(f"! Clé en double ({key}) : « {fn} » ignoré, renomme-le.")
            continue
        used[key] = fn
        try:
            im = Image.open(os.path.join(sys.argv[1], fn)).convert("RGB")
        except Exception as e:
            print(f"! Impossible de lire {fn} : {e}")
            continue
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
        im.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(OUT, key + ".png"), optimize=True)
        # Windows interdit ":" dans un nom de fichier : " - " devient ": " (1re occurrence)
        name = stem.strip().replace('"', "'").replace(" - ", ": ", 1)
        lines.append(f'    {{ "name": "{name}", "cover": "{key}" }},')
        print(f"OK  {fn}  ->  {key}.png")

    snippet = os.path.join(os.path.dirname(OUT), "..", "games_snippet.txt")
    snippet = os.path.normpath(snippet)
    with open(snippet, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n{len(lines)} jeu(x) prêt(s).")
    print(f"1) Uploade le contenu de : {OUT}")
    print(f"2) Colle les lignes de {snippet} dans la liste \"games\" de games.json (sur GitHub)")
    print("   Attention : la toute dernière ligne collée ne doit pas finir par une virgule.")
    if len(used) > 250:
        print("Attention : Discord limite à 300 images par application.")


if __name__ == "__main__":
    main()
