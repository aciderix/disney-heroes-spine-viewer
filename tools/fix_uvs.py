#!/usr/bin/env python3
"""Convert mesh UVs from normalized (0-1) to region-relative pixel coordinates."""
import json, os, sys

def parse_atlas(atlas_path):
    """Parse atlas file and return {region_name: {x, y, w, h, rotate}}"""
    with open(atlas_path) as f:
        lines = f.readlines()
    regions = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Region names are non-indented, non-empty, follow a blank line, and have 'rotate:' on next line
        if line and not line.startswith(' ') and ':' not in line and i > 0:
            if i+1 < len(lines) and 'rotate:' in lines[i+1]:
                rotate = lines[i+1].strip().split(': ')[1] == 'true'
                xy = [int(x) for x in lines[i+2].strip().split(': ')[1].split(',')]
                sz = [int(x) for x in lines[i+3].strip().split(': ')[1].split(',')]
                regions[line] = {'x': xy[0], 'y': xy[1], 'w': sz[0], 'h': sz[1], 'rotate': rotate}
                i += 5  # skip rotate, xy, size, orig, offset, index
                continue
        i += 1
    return regions

def fix_uvs(json_path, atlas_path):
    with open(json_path) as f:
        data = json.load(f)
    
    regions = parse_atlas(atlas_path)
    
    fixed = 0
    for skin_name, slots in data.get('skins', {}).items():
        for slot_name, attachments in slots.items():
            for att_name, att in attachments.items():
                if att.get('type') in ('mesh', 'linkedmesh'):
                    path = att.get('path', att_name)
                    if path in regions and 'uvs' in att:
                        r = regions[path]
                        w, h = r['w'], r['h']
                        uvs = att['uvs']
                        # Convert from normalized (0-1) to pixel coordinates
                        for i in range(0, len(uvs), 2):
                            uvs[i] = uvs[i] * w
                            uvs[i+1] = uvs[i+1] * h
                        att['uvs'] = uvs
                        fixed += 1
    with open(json_path, 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    return fixed

# Process all characters
chars_dir = 'characters'
for name in sorted(os.listdir(chars_dir)):
    char_path = os.path.join(chars_dir, name)
    json_path = os.path.join(char_path, 'skeleton.json')
    atlas_path = os.path.join(char_path, 'atlas.atlas')
    if os.path.exists(json_path) and os.path.exists(atlas_path):
        fixed = fix_uvs(json_path, atlas_path)
        print(f"{name}: fixed {fixed} mesh UVs")
