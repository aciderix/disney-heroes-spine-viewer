#!/usr/bin/env python3
"""Extract the 9 missing Disney Heroes characters for the Spine web viewer."""

import os, sys, json, struct, zipfile, gzip, time
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spine_skel_to_json import convert_skel_to_json

ARCHIVES = {
    "326": "/tmp/archives/world_add_326.zip",
    "329": "/tmp/archives/world_add_329.zip",
    "331": "/tmp/archives/world_add_331.zip",
}

CHARACTERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "characters")

# Map: character_name -> (version, skel_path_pattern, atlas_preferred, etc1_preferred)
MISSING_CHARS = {
    "molly_mcgee":             {"ver": "326", "skel": "molly_mcgee.skel"},
    "yokai":                   {"ver": "326", "skel": "yokai.skel"},
    "captain_grime":           {"ver": "329", "skel": "captain_grime.skel"},
    "benjamin_franklin_gates": {"ver": "329", "skel": "benjamin_franklin_gates.skel"},
    "dumbo":                   {"ver": "329", "skel": "dumbo.skel"},
    "dumbo_bubble":            {"ver": "329", "skel": "dumbo_bubble.skel"},
    "mater":                   {"ver": "329", "skel": "mater.skel"},
    "mowgli":                  {"ver": "331", "skel": "mowgli.skel"},
    "scuttle":                 {"ver": "331", "skel": "scuttle.skel"},
}

TABLES = np.array([
    [2, 8, -2, -8], [5, 17, -5, -17], [9, 29, -9, -29], [13, 42, -13, -42],
    [18, 60, -18, -60], [24, 80, -24, -80], [33, 106, -33, -106], [47, 159, -47, -159]
], dtype=np.int32)

def decode_etc1_numpy(data, w, h):
    bx, by = w // 4, h // 4
    n_blocks = bx * by
    blocks = np.frombuffer(data[:n_blocks * 8], dtype=np.uint64).byteswap()
    diff = ((blocks >> 33) & 1).astype(np.int32)
    flip = ((blocks >> 32) & 1).astype(np.int32)
    t1 = ((blocks >> 37) & 7).astype(np.int32)
    t2 = ((blocks >> 34) & 7).astype(np.int32)
    pidx = (blocks & 0xFFFFFFFF).astype(np.uint32)
    r1 = ((blocks >> 60) & 0xF).astype(np.int32)
    g1 = ((blocks >> 52) & 0xF).astype(np.int32)
    b1 = ((blocks >> 44) & 0xF).astype(np.int32)
    dr = ((blocks >> 56) & 0xF).astype(np.int32)
    dg = ((blocks >> 48) & 0xF).astype(np.int32)
    db = ((blocks >> 40) & 0xF).astype(np.int32)
    dr = np.where(dr >= 8, dr - 16, dr)
    dg = np.where(dg >= 8, dg - 16, dg)
    db = np.where(db >= 8, db - 16, db)
    r2_diff = (r1 + dr) & 0xF
    g2_diff = (g1 + dg) & 0xF
    b2_diff = (b1 + db) & 0xF
    r2_ind = ((blocks >> 48) & 0xF).astype(np.int32)
    g2_ind = ((blocks >> 44) & 0xF).astype(np.int32)
    b2_ind = ((blocks >> 40) & 0xF).astype(np.int32)
    r2 = np.where(diff == 1, r2_diff, r2_ind)
    g2 = np.where(diff == 1, g2_diff, g2_ind)
    b2 = np.where(diff == 1, b2_diff, b2_ind)
    br1, bg1, bb1 = r1 * 17, g1 * 17, b1 * 17
    br2, bg2, bb2 = r2 * 17, g2 * 17, b2 * 17
    idx = np.zeros((n_blocks, 16), dtype=np.int32)
    for i in range(16):
        idx[:, i] = (pidx >> ((15 - i) * 2)) & 3
    pixel_cols = np.arange(16) % 4
    use_table1 = np.where(
        flip[:, None] == 0,
        np.arange(16)[None, :] < 8,
        pixel_cols[None, :] < 2
    )
    mods1 = TABLES[t1]
    mods2 = TABLES[t2]
    arange_blocks = np.arange(n_blocks)[:, None]
    mod = np.where(use_table1, mods1[arange_blocks, idx], mods2[arange_blocks, idx])
    base_r = np.where(use_table1, br1[:, None], br2[:, None])
    base_g = np.where(use_table1, bg1[:, None], bg2[:, None])
    base_b = np.where(use_table1, bb1[:, None], bb2[:, None])
    r = np.clip(base_b + mod, 0, 255).astype(np.uint8)
    g = np.clip(base_g + mod, 0, 255).astype(np.uint8)
    b = np.clip(base_r + mod, 0, 255).astype(np.uint8)
    r = r.reshape(by, bx, 4, 4).transpose(0, 2, 1, 3).reshape(h, w)
    g = g.reshape(by, bx, 4, 4).transpose(0, 2, 1, 3).reshape(h, w)
    b = b.reshape(by, bx, 4, 4).transpose(0, 2, 1, 3).reshape(h, w)
    return r, g, b

def decode_etc1_to_texture(etc1_gz_data):
    dec = gzip.decompress(etc1_gz_data)
    if dec[4:8] != b'PKM ':
        raise ValueError("Not PKM")
    w = struct.unpack('>H', dec[12:14])[0]
    h = struct.unpack('>H', dec[14:16])[0]
    etc1_raw = dec[20:]
    half_h = h // 2
    half_size = (w // 4) * (half_h // 4) * 8
    r_a, _, _ = decode_etc1_numpy(etc1_raw[:half_size], w, half_h)
    alpha = r_a
    r_rgb, g_rgb, b_rgb = decode_etc1_numpy(etc1_raw[half_size:half_size*2], w, half_h)
    rgba = np.zeros((half_h, w, 4), dtype=np.uint8)
    rgba[:, :, 0] = r_rgb
    rgba[:, :, 1] = g_rgb
    rgba[:, :, 2] = b_rgb
    rgba[:, :, 3] = alpha
    return Image.frombytes('RGBA', (w, half_h), rgba.tobytes())

def fix_atlas(atlas_text):
    lines = atlas_text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().endswith('.etc1'):
            lines[i] = 'texture.png'
    return '\n'.join(lines)

def pick_file(paths, preferred='unit-DEFAULT-untrimmed'):
    for p in paths:
        if preferred in p and 'smallcombat' not in p:
            return p
    for p in paths:
        if 'unit-DEFAULT' in p and 'smallcombat' not in p:
            return p
    return paths[0] if paths else None

def extract_character(name, ver, skel_name, zf):
    prefix = f"ETC1/world/units/{name}/spine/"
    char_dir = os.path.join(CHARACTERS_DIR, name)
    os.makedirs(char_dir, exist_ok=True)
    
    # Find files in the zip for this character
    all_files = zf.namelist()
    char_files = [f for f in all_files if f.startswith(prefix)]
    
    if not char_files:
        return f"no files found at {prefix}"
    
    # Find skel
    skel_path = f"{prefix}{skel_name}"
    if skel_path not in char_files:
        # Try to find any .skel
        skels = [f for f in char_files if f.endswith('.skel')]
        if not skels:
            return "no .skel found"
        skel_path = skels[0]
    
    # Find atlas (prefer unit-DEFAULT-untrimmed, not smallcombat)
    atlas_path = pick_file([f for f in char_files if f.endswith('.atlas')])
    if not atlas_path:
        return "no .atlas found"
    
    # Find etc1 (same base name as atlas, but .etc1)
    etc1_base = atlas_path.replace('.atlas', '.etc1')
    if etc1_base not in char_files:
        # Try any .etc1
        etc1s = [f for f in char_files if f.endswith('.etc1') and 'unit-DEFAULT' in f and 'smallcombat' not in f]
        if not etc1s:
            return "no .etc1 found"
        etc1_base = etc1s[0]
    
    print(f"  skel:  {skel_path}")
    print(f"  atlas: {atlas_path}")
    print(f"  etc1:  {etc1_base}")
    
    # 1. Convert skel to JSON
    skel_data = zf.read(skel_path)
    tmp = os.path.join(char_dir, 't.skel')
    with open(tmp, 'wb') as f:
        f.write(skel_data)
    try:
        skeleton = convert_skel_to_json(tmp)
        with open(os.path.join(char_dir, 'skeleton.json'), 'w') as f:
            json.dump(skeleton, f, separators=(',', ':'))
    except Exception as e:
        return f"skel error: {e}"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    
    # 2. Convert ETC1 to PNG
    try:
        texture = decode_etc1_to_texture(zf.read(etc1_base))
        texture.save(os.path.join(char_dir, 'texture.png'))
    except Exception as e:
        return f"etc1 error: {e}"
    
    # 3. Fix atlas
    try:
        atlas_text = fix_atlas(zf.read(atlas_path).decode('utf-8'))
        with open(os.path.join(char_dir, 'atlas.atlas'), 'w') as f:
            f.write(atlas_text)
    except Exception as e:
        return f"atlas error: {e}"
    
    nb = len(skeleton.get('bones', []))
    ns = len(skeleton.get('slots', []))
    na = len(skeleton.get('animations', {}))
    w, h = texture.size
    return f"OK ({nb} bones, {ns} slots, {na} anims, {w}x{h}px)"

def main():
    zips = {}
    for ver, path in ARCHIVES.items():
        if os.path.exists(path):
            zips[ver] = zipfile.ZipFile(path)
            print(f"Loaded v{ver}: {len(zips[ver].namelist())} files")
        else:
            print(f"WARNING: v{ver} archive not found at {path}")
    
    if not zips:
        print("No archives found!"); return
    
    print(f"\nExtracting {len(MISSING_CHARS)} characters to {CHARACTERS_DIR}\n")
    
    ok, fail = 0, 0
    for name, info in MISSING_CHARS.items():
        ver = info['ver']
        skel_name = info['skel']
        print(f"[{name}] (v{ver}, skel: {skel_name})")
        if ver not in zips:
            print(f"  SKIP: archive v{ver} not loaded")
            fail += 1
            continue
        result = extract_character(name, ver, skel_name, zips[ver])
        print(f"  -> {result}\n")
        if result.startswith("OK"):
            ok += 1
        else:
            fail += 1
    
    print(f"DONE: OK={ok} Fail={fail}")

if __name__ == "__main__":
    main()
