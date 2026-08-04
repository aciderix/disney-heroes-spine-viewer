#!/usr/bin/env python3
"""Extract ALL Disney Heroes characters for the Spine web viewer.
GitHub Actions version — archives are in /tmp/, char_index in /tmp/."""

import os, sys, json, struct, zipfile, gzip, time
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spine_skel_to_json import convert_skel_to_json

ARCHIVES = {
    "COMPLETE_LIVE_WORLD_ADDITIONAL_XHDPI_ETC1_325.zip": "/tmp/world_add_325.zip",
    "COMPLETE_LIVE_WORLD_INITIAL_INTERNAL_XHDPI_ETC1_325.zip": "/tmp/world_initial_325.zip",
}

CHARACTERS_DIR = "characters"
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
    # BGR swap
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
    if lines:
        lines[0] = 'texture.png'
    return '\n'.join(lines)

def pick_file(paths, preferred='unit-DEFAULT-untrimmed'):
    for p in paths:
        if preferred in p and 'smallcombat' not in p:
            return p
    for p in paths:
        if 'unit-DEFAULT' in p and 'smallcombat' not in p:
            return p
    return paths[0] if paths else None

def extract_character(name, info, zips):
    char_dir = os.path.join(CHARACTERS_DIR, name)
    os.makedirs(char_dir, exist_ok=True)
    if all(os.path.exists(os.path.join(char_dir, f)) for f in ['skeleton.json', 'atlas.atlas', 'texture.png']):
        return "skip"
    arch_path = ARCHIVES.get(info['archive'])
    if not arch_path or arch_path not in zips:
        return "no archive"
    zf = zips[arch_path]
    # skel
    try:
        skel_data = zf.read(info['skel'])
    except KeyError:
        return "skel not found"
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
        os.remove(tmp)
    # etc1
    etc1_path = pick_file(info.get('etc1', []))
    if not etc1_path:
        return "no etc1"
    try:
        texture = decode_etc1_to_texture(zf.read(etc1_path))
        texture.save(os.path.join(char_dir, 'texture.png'))
    except Exception as e:
        return f"etc1 error: {e}"
    # atlas
    atlas_path = pick_file(info.get('atlas', []))
    if not atlas_path:
        return "no atlas"
    try:
        atlas_text = fix_atlas(zf.read(atlas_path).decode('utf-8'))
        with open(os.path.join(char_dir, 'atlas.atlas'), 'w') as f:
            f.write(atlas_text)
    except Exception as e:
        return f"atlas error: {e}"
    nb = len(skeleton.get('bones', []))
    ns = len(skeleton.get('slots', []))
    na = len(skeleton.get('animations', {}))
    return f"ok ({nb}b/{ns}s/{na}a)"

def main():
    with open('/tmp/char_index.json') as f:
        ci = json.load(f)
    print(f"Total: {len(ci)}")
    zips = {}
    for name, path in ARCHIVES.items():
        if os.path.exists(path):
            zips[path] = zipfile.ZipFile(path)
            print(f"  {path}: {len(zips[path].namelist())} files")
    if not zips:
        print("No archives!"); return
    ok, skip, fail = 0, 0, 0
    t0 = time.time()
    for i, (name, info) in enumerate(sorted(ci.items())):
        result = extract_character(name, info, zips)
        if result == "skip": skip += 1
        elif result.startswith("ok"): ok += 1
        else: fail += 1
        print(f"[{i+1}/{len(ci)}] {name}: {result} ({time.time()-t0:.1f}s)", flush=True)
    print(f"\nDONE: OK={ok} Skip={skip} Fail={fail} Time={time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
