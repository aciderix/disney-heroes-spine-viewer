# Pipeline d'extraction de personnages — Disney Heroes: Battle Mode

## Format des assets

Le jeu utilise **Spine 3.6** (format binaire `.skel`) avec des textures **ETC1 compressées** (format PKM, gzip). Chaque personnage a 3 fichiers dans l'archive :

```
ETC1/world/units/<name>/spine/
  ├── <name>.skel                    # Skeleton binaire Spine 3.6
  ├── unit-DEFAULT-untrimmed.atlas    # Atlas (référence les régions de texture)
  └── unit-DEFAULT-untrimmed.etc1     # Texture ETC1 compressée (gzip → PKM)
```

## Format PKM ETC1

Le fichier `.etc1` est compressé en gzip. Une fois décompressé, on obtient un fichier PKM avec un header de 20 bytes :

| Offset | Taille | Description |
|--------|--------|-------------|
| 0-3    | 4B     | Version (`\x00\x10\x00\x10`) |
| 4-7    | 4B     | Magic (`PKM `) |
| 8-9    | 2B     | Version string |
| 10-11  | 2B     | Flags |
| 12-13  | 2B     | Width (big-endian) |
| 14-15  | 2B     | Height (big-endian) |
| 16-17  | 2B     | Original width |
| 18-19  | 2B     | Original height |
| 20+    | ...    | Données ETC1 brutes |

### Split alpha/RGB

La hauteur dans le header est **le double** de la hauteur réelle. La texture est divisée en deux moitiés :

- **Moitié supérieure** → canal alpha (grayscale, encodé en ETC1)
- **Moitié inférieure** → canaux RGB (encodés en ETC1)

La texture finale fait `width × (height/2)`.

### Décodeur ETC1

On utilise `texture2ddecoder-wasm` (npm) qui expose `decode_etc1(data, width, height)` et retourne du RGBA.

**⚠️ Important :** `texture2ddecoder-wasm` sort les canaux en **BGRA**, pas RGBA. Il faut swapper R et B :

```javascript
rgba[i*4+0] = bottom[i*4+2];  // R = B (swapé)
rgba[i*4+1] = bottom[i*4+1];  // G = G
rgba[i*4+2] = bottom[i*4+0];  // B = R (swapé)
rgba[i*4+3] = top[i*4+0];    // A = R de la moitié alpha
```

Sans ce swap, les personnages ont la **peau bleue** (R et B inversés).

## Pipeline complet

```
Archive ZIP (world_add_XXX.zip)
    │
    ├── 1. Extraire .skel, .atlas, .etc1 du ZIP
    │
    ├── 2. Décompresser .etc1 (gzip → PKM)
    │
    ├── 3. Décoder PKM → texture PNG
    │       ├── Split en 2 moitiés (alpha + RGB)
    │       ├── decode_etc1() via texture2ddecoder-wasm
    │       ├── Swap BGR → RGB
    │       └── Combiner en RGBA → PNG (via Pillow)
    │
    ├── 4. Convertir .skel → skeleton.json
    │       └── spine_skel_to_json.py (BinaryReader Spine 3.6)
    │
    ├── 5. Fixer l'atlas
    │       └── Remplacer ".etc1" par "texture.png" dans le fichier atlas
    │
    └── 6. Output: characters/<name>/
            ├── texture.png
            ├── skeleton.json
            └── atlas.atlas
```

## Dépendances

```bash
# Node.js
npm install texture2ddecoder-wasm

# Python
pip install pillow numpy
```

## Utilisation

```bash
# Extraire un personnage depuis une archive
python3 tools/prepare_character.py molly_mcgee /tmp/archives/world_add_326.zip

# Extraire plusieurs personnages
python3 tools/prepare_character.py molly_mcgee,yokai /tmp/archives/world_add_326.zip

# Spécifier le dossier de sortie
python3 tools/prepare_character.py molly_mcgee /tmp/archives/world_add_326.zip --output characters/

# Lister les personnages disponibles dans une archive
python3 tools/prepare_character.py --list /tmp/archives/world_add_326.zip

# Forcer la re-décompression (écrase les fichiers existants)
python3 tools/prepare_character.py molly_mcgee /tmp/archives/world_add_326.zip --force
```

## Notes

- Les archives viennent de `archive.org` (Internet Archive)
- Versions : `world_initial_XXX.zip` + `world_add_XXX.zip`
- Le viewer (`index.html`) charge `texture.png`, `skeleton.json`, `atlas.atlas`
- L'atlas peut avoir plusieurs lignes de référence ; le script gère le remplacement `.etc1` → `texture.png` ligne par ligne
- Le runtime Spine utilise `spine-webgl.js` (fork avec fix signed draw-order offsets)
