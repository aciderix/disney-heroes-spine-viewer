#!/usr/bin/env python3
"""
prepare_character.py — Extract & prepare a Disney Heroes: Battle Mode character
from a game archive ZIP into viewer-ready files (texture.png, skeleton.json, atlas.atlas).

Usage:
    python3 tools/prepare_character.py <character_name> <archive.zip> [--output DIR] [--force]
    python3 tools/prepare_character.py <name1,name2,name3> <archive.zip> [--output DIR]
    python3 tools/prepare_character.py --list <archive.zip>

Examples:
    python3 tools/prepare_character.py molly_mcgee /tmp/archives/world_add_326.zip
    python3 tools/prepare_character.py molly_mcgee,yokai /tmp/archives/world_add_326.zip --output characters/
    python3 tools/prepare_character.py --list /tmp/archives/world_add_326.zip

Requirements:
    - Node.js + texture2ddecoder-wasm (npm install texture2ddecoder-wasm)
    - Python: pillow, numpy
    - This script must be run from the repo root (so it can find tools/ and node_modules/)
"""

import sys
import os
import zipfile
import gzip
import json
import struct
import argparse
import subprocess
import tempfile
import shutil

# ─── Spine 3.6 binary skeleton reader ──────────────────────────────────────────
# (inlined from spine_skel_to_json.py so this script is self-contained)


class BinaryReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def readByte(self):
        b = self.data[self.pos]; self.pos += 1; return b

    def readBoolean(self):
        return self.readByte() != 0

    def readInt(self):
        r = self.readByte(); r <<= 8; r |= self.readByte(); r <<= 8; r |= self.readByte(); r <<= 8; r |= self.readByte()
        if r > 0x7FFFFFFF:
            r -= 0x100000000
        return r

    def readVarint(self, optimizePositive=True):
        b = self.readByte(); v = b & 0x7F
        if b & 0x80:
            b = self.readByte(); v |= (b & 0x7F) << 7
            if b & 0x80:
                b = self.readByte(); v |= (b & 0x7F) << 14
                if b & 0x80:
                    b = self.readByte(); v |= (b & 0x7F) << 21
                    if b & 0x80:
                        v |= (self.readByte() & 0x7F) << 28
        if not optimizePositive:
            v = (v >> 1) ^ (-(v & 1))
        return v

    def readFloat(self):
        return struct.unpack('f', struct.pack('i', self.readInt()))[0]

    def readString(self):
        length = self.readVarint(True)
        if length == 0:
            return None
        s = self.data[self.pos:self.pos + length - 1]; self.pos += length - 1
        return s.decode('utf-8', errors='replace')

    def readColor(self):
        return (self.readByte() / 255, self.readByte() / 255, self.readByte() / 255, self.readByte() / 255)

    def readCurve(self):
        t = self.readByte()
        if t == 0: return "linear"
        if t == 1: return "stepped"
        if t == 2: return [self.readFloat(), self.readFloat(), self.readFloat(), self.readFloat()]
        return "linear"

    def readFloatArray(self, n, scale=1.0):
        return [self.readFloat() * scale for _ in range(n)]

    def readShortArray(self):
        n = self.readVarint(True)
        return [self.readByte() << 8 | self.readByte() for _ in range(n)]

    def readVertices(self, vertexCount, scale=1.0):
        verticesLength = vertexCount * 2
        weighted = self.readBoolean()
        if not weighted:
            return self.readFloatArray(verticesLength, scale)
        result = []
        for _ in range(vertexCount):
            boneCount = self.readVarint(True)
            result.append(boneCount)
            for _ in range(boneCount):
                result.append(self.readVarint(True))
                result.append(self.readFloat() * scale)
                result.append(self.readFloat() * scale)
                result.append(self.readFloat())
        return result


def read_skin(r, scale, nonessential, slot_names):
    slot_count = r.readVarint(True)
    if slot_count == 0:
        return None
    skin = {}
    for i in range(slot_count):
        slot_idx = r.readVarint(True)
        att_count = r.readVarint(True)
        slot_name = slot_names[slot_idx]
        skin[slot_name] = {}
        for j in range(att_count):
            name = r.readString()
            attachment = read_attachment(r, scale, nonessential, name or f"att{j}", slot_names)
            if attachment:
                actual_name = name if name else f"att{j}"
                skin[slot_name][actual_name] = attachment
    return skin


def read_attachment(r, scale, nonessential, attachment_name, slot_names):
    name = r.readString()
    actual_name = name if name else attachment_name
    att_type = r.readByte()

    if att_type == 0:  # REGION
        path = r.readString()
        if not path: path = actual_name
        rotation = r.readFloat(); x = r.readFloat() * scale; y = r.readFloat() * scale
        scaleX = r.readFloat(); scaleY = r.readFloat()
        width = r.readFloat() * scale; height = r.readFloat() * scale
        color = r.readColor()
        att = {"type": "region", "path": path}
        if rotation != 0: att["rotation"] = rotation
        if x != 0: att["x"] = x
        if y != 0: att["y"] = y
        if scaleX != 1: att["scaleX"] = scaleX
        if scaleY != 1: att["scaleY"] = scaleY
        att["width"] = width; att["height"] = height
        if color != (1, 1, 1, 1):
            att["color"] = f"{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}{int(color[3]*255):02x}"
        return att
    elif att_type == 1:  # BOUNDING_BOX
        vc = r.readVarint(True)
        verts = r.readVertices(vc, scale)
        att = {"type": "boundingbox", "vertexCount": vc, "vertices": verts}
        if nonessential: r.readInt()
        return att
    elif att_type == 2:  # MESH
        path = r.readString()
        if not path: path = actual_name
        color = r.readColor()
        vc = r.readVarint(True)
        uvs = r.readFloatArray(vc * 2, 1.0)
        triangles = r.readShortArray()
        verts = r.readVertices(vc, scale)
        hull = r.readVarint(True) * 2
        att = {"type": "mesh", "path": path, "uvs": uvs, "vertices": verts, "triangles": triangles, "hull": hull}
        if color != (1, 1, 1, 1):
            att["color"] = f"{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}{int(color[3]*255):02x}"
        if nonessential:
            att["edges"] = r.readShortArray()
            att["width"] = r.readFloat() * scale; att["height"] = r.readFloat() * scale
        return att
    elif att_type == 3:  # LINKED_MESH
        path = r.readString()
        if not path: path = actual_name
        color = r.readColor()
        skinName = r.readString(); parent = r.readString()
        inheritDeform = r.readBoolean()
        att = {"type": "linkedmesh", "path": path}
        if skinName: att["skin"] = skinName
        att["parent"] = parent
        if not inheritDeform: att["deform"] = inheritDeform
        if color != (1, 1, 1, 1):
            att["color"] = f"{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}{int(color[3]*255):02x}"
        if nonessential:
            att["width"] = r.readFloat() * scale; att["height"] = r.readFloat() * scale
        return att
    elif att_type == 4:  # PATH
        closed = r.readBoolean(); constantSpeed = r.readBoolean()
        vc = r.readVarint(True)
        verts = r.readVertices(vc, scale)
        ll = vc // 3
        lengths = [r.readFloat() * scale for _ in range(ll)]
        att = {"type": "path", "vertexCount": vc, "vertices": verts, "closed": closed, "constantSpeed": constantSpeed}
        att["lengths"] = lengths
        if nonessential: r.readInt()
        return att
    elif att_type == 5:  # POINT
        rotation = r.readFloat(); x = r.readFloat() * scale; y = r.readFloat() * scale
        att = {"type": "point"}
        if rotation != 0: att["rotation"] = rotation
        if x != 0: att["x"] = x
        if y != 0: att["y"] = y
        if nonessential:
            color = r.readColor()
            if color != (1, 1, 1, 1):
                att["color"] = f"{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}{int(color[3]*255):02x}"
        return att
    elif att_type == 6:  # CLIPPING
        endSlotIdx = r.readVarint(True)
        vc = r.readVarint(True)
        verts = r.readVertices(vc, scale)
        att = {"type": "clipping", "end": slot_names[endSlotIdx] if endSlotIdx < len(slot_names) else str(endSlotIdx), "vertexCount": vc, "vertices": verts}
        if nonessential: r.readInt()
        return att
    return None


def read_animation(r, bone_names, slot_names, ik_names, tc_names, pc_names, skin_names, scale, event_names=None):
    anim = {}

    # Slot timelines
    stc = r.readVarint(True)
    slots_data = {}
    for i in range(stc):
        si = r.readVarint(True); tlc = r.readVarint(True)
        sn = slot_names[si]
        for j in range(tlc):
            tt = r.readByte(); fc = r.readVarint(True)
            if tt == 0:
                frames = [{"time": r.readFloat(), "name": r.readString() or ""} for _ in range(fc)]
                slots_data.setdefault(sn, {})["attachment"] = frames
            elif tt == 1:
                frames = []
                for f in range(fc):
                    time = r.readFloat(); c = r.readColor()
                    fr = {"time": time, "color": f"{int(c[0]*255):02x}{int(c[1]*255):02x}{int(c[2]*255):02x}{int(c[3]*255):02x}"}
                    if f < fc - 1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                slots_data.setdefault(sn, {})["color"] = frames
            elif tt == 2:
                frames = []
                for f in range(fc):
                    time = r.readFloat(); light = r.readColor(); dark = r.readColor()
                    fr = {"time": time, "light": f"{int(light[0]*255):02x}{int(light[1]*255):02x}{int(light[2]*255):02x}{int(light[3]*255):02x}"}
                    fr["dark"] = f"{int(dark[1]*255):02x}{int(dark[2]*255):02x}{int(dark[3]*255):02x}"
                    if f < fc - 1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                slots_data.setdefault(sn, {})["twoColor"] = frames
    if slots_data: anim["slots"] = slots_data

    # Bone timelines
    btc = r.readVarint(True)
    bones_data = {}
    for i in range(btc):
        bi = r.readVarint(True); tlc = r.readVarint(True)
        bn = bone_names[bi]
        for j in range(tlc):
            tt = r.readByte(); fc = r.readVarint(True)
            if tt == 0:
                frames = []
                for f in range(fc):
                    time = r.readFloat(); angle = r.readFloat()
                    fr = {"time": time, "angle": angle}
                    if f < fc - 1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                bones_data.setdefault(bn, {})["rotate"] = frames
            elif tt in (1, 2, 3):
                ts = scale if tt == 1 else 1.0
                kn = ["translate", "scale", "shear"][tt - 1]
                frames = []
                for f in range(fc):
                    time = r.readFloat(); x = r.readFloat() * ts; y = r.readFloat() * ts
                    fr = {"time": time, "x": x, "y": y}
                    if f < fc - 1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                bones_data.setdefault(bn, {})[kn] = frames
    if bones_data: anim["bones"] = bones_data

    # IK timelines
    ikc = r.readVarint(True)
    ik_data = {}
    for i in range(ikc):
        idx = r.readVarint(True); fc = r.readVarint(True)
        frames = []
        for f in range(fc):
            time = r.readFloat(); mix = r.readFloat()
            bend = r.readByte()
            if bend > 127: bend -= 256
            fr = {"time": time, "mix": mix, "bendPositive": bend > 0}
            if f < fc - 1: fr["curve"] = r.readCurve()
            frames.append(fr)
        ik_data[ik_names[idx]] = frames
    if ik_data: anim["ik"] = ik_data

    # Transform timelines
    tcc = r.readVarint(True)
    tc_data = {}
    for i in range(tcc):
        idx = r.readVarint(True); fc = r.readVarint(True)
        frames = []
        for f in range(fc):
            time = r.readFloat()
            fr = {"time": time, "rotateMix": r.readFloat(), "translateMix": r.readFloat(), "scaleMix": r.readFloat(), "shearMix": r.readFloat()}
            if f < fc - 1: fr["curve"] = r.readCurve()
            frames.append(fr)
        tc_data[tc_names[idx]] = frames
    if tc_data: anim["transform"] = tc_data

    # Path timelines
    pcc = r.readVarint(True)
    pc_data = {}
    for i in range(pcc):
        idx = r.readVarint(True); tlc = r.readVarint(True)
        for j in range(tlc):
            tt = r.readByte(); fc = r.readVarint(True)
            if tt in (0, 1):
                kn = "position" if tt == 0 else "spacing"
                frames = []
                for f in range(fc):
                    time = r.readFloat(); val = r.readFloat()
                    if tt == 0: val *= scale
                    fr = {"time": time, kn: val}
                    if f < fc - 1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                pc_data.setdefault(pc_names[idx], {})[kn] = frames
            elif tt == 2:
                fc2 = r.readVarint(True)
                frames = []
                for f in range(fc2):
                    time = r.readFloat()
                    mix = [r.readFloat() for _ in range(3)]
                    fr = {"time": time, "mix": mix}
                    if f < fc2 - 1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                pc_data.setdefault(pc_names[idx], {})["mix"] = frames
    if pc_data: anim["path"] = pc_data

    # Deform timelines
    dfc = r.readVarint(True)
    deform_data = {}
    for i in range(dfc):
        skin_idx = r.readVarint(True)
        skin_name = skin_names[skin_idx] if skin_idx < len(skin_names) else "default"
        sc = r.readVarint(True)
        for j in range(sc):
            si = r.readVarint(True)
            sn = slot_names[si] if si < len(slot_names) else str(si)
            ac = r.readVarint(True)
            for k in range(ac):
                an = r.readString()
                fc = r.readVarint(True)
                frames = []
                for f in range(fc):
                    time = r.readFloat()
                    end = r.readVarint(True)
                    if end == 0:
                        fr = {"time": time}
                    else:
                        start = r.readVarint(True)
                        deform = [r.readFloat() * scale for _ in range(end)]
                        fr = {"time": time, "offset": start, "vertices": deform}
                    if f < fc - 1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                deform_data.setdefault(skin_name, {}).setdefault(sn, {})[an] = frames
    if deform_data: anim["deform"] = deform_data

    # Draw order
    doc = r.readVarint(True)
    if doc > 0:
        frames = []
        for f in range(doc):
            time = r.readFloat(); oc = r.readVarint(True)
            if oc == 0:
                frames.append({"time": time})
            else:
                offsets = []
                for j in range(oc):
                    si = r.readVarint(True); off = r.readVarint(True)
                    offsets.append({"slot": slot_names[si] if si < len(slot_names) else str(si), "offset": off})
                frames.append({"time": time, "offsets": offsets})
        anim["drawOrder"] = frames

    # Events
    ec = r.readVarint(True)
    if ec > 0:
        frames = []
        for f in range(ec):
            time = r.readFloat()
            edi = r.readVarint(True)
            iv = r.readVarint(False); fv = r.readFloat()
            hs = r.readBoolean()
            sv = r.readString() if hs else None
            ename = event_names[edi] if (event_names and edi < len(event_names)) else f"event_{edi}"
            fr = {"time": time, "name": ename, "int": iv, "float": fv}
            if sv: fr["string"] = sv
            frames.append(fr)
        anim["events"] = frames

    return anim


def convert_skel_to_json(skel_data, scale=1.0):
    """Convert Spine 3.6 binary skeleton data (bytes) to JSON dict."""
    r = BinaryReader(skel_data)
    result = {}

    hash_val = r.readString(); version = r.readString()
    width = r.readFloat(); height = r.readFloat()
    nonessential = r.readBoolean()
    skeleton_info = {"hash": hash_val or "", "spine": version or "", "width": width, "height": height}
    if nonessential:
        r.readFloat(); r.readString()
    result["skeleton"] = skeleton_info

    # Bones
    bone_count = r.readVarint(True)
    bones = []; bone_names = []
    for i in range(bone_count):
        name = r.readString()
        parent_idx = r.readVarint(True) if i > 0 else -1
        rotation = r.readFloat(); x = r.readFloat() * scale; y = r.readFloat() * scale
        scaleX = r.readFloat(); scaleY = r.readFloat()
        shearX = r.readFloat(); shearY = r.readFloat()
        length = r.readFloat() * scale; mode = r.readVarint(True)
        bone = {"name": name}
        if parent_idx >= 0: bone["parent"] = bone_names[parent_idx]
        if rotation != 0: bone["rotation"] = rotation
        if x != 0: bone["x"] = x
        if y != 0: bone["y"] = y
        if scaleX != 1: bone["scaleX"] = scaleX
        if scaleY != 1: bone["scaleY"] = scaleY
        if shearX != 0: bone["shearX"] = shearX
        if shearY != 0: bone["shearY"] = shearY
        if length != 0: bone["length"] = length
        if mode != 0:
            modes = ["normal", "onlyTranslation", "noRotationOrReflection", "noScale", "noScaleOrReflection"]
            if mode < len(modes): bone["transform"] = modes[mode]
        if nonessential: r.readInt()
        bones.append(bone); bone_names.append(name)
    result["bones"] = bones

    # Slots
    slot_count = r.readVarint(True)
    slots = []; slot_names = []
    for i in range(slot_count):
        sn = r.readString(); bi = r.readVarint(True)
        color = r.readColor()
        a = r.readByte(); red = r.readByte(); g = r.readByte(); b = r.readByte()
        an = r.readString(); bm = r.readVarint(True)
        slot = {"name": sn, "bone": bone_names[bi]}
        if an: slot["attachment"] = an
        if color != (1, 1, 1, 1):
            slot["color"] = f"{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}{int(color[3]*255):02x}"
        if not (red == 0xff and g == 0xff and b == 0xff and a == 0xff):
            slot["darkColor"] = f"{red:02x}{g:02x}{b:02x}"
        blend_modes = ["normal", "additive", "multiply", "screen"]
        if bm < len(blend_modes) and bm != 0: slot["blend"] = blend_modes[bm]
        slots.append(slot); slot_names.append(sn)
    result["slots"] = slots

    # IK constraints
    ik_count = r.readVarint(True)
    ik_constraints = []; ik_names = []
    for i in range(ik_count):
        name = r.readString(); order = r.readVarint(True)
        bc = r.readVarint(True); bone_indices = [r.readVarint(True) for _ in range(bc)]
        target = r.readVarint(True); mix = r.readFloat()
        bend = r.readByte()
        if bend > 127: bend -= 256
        ik = {"name": name, "bones": [bone_names[idx] for idx in bone_indices], "target": bone_names[target]}
        if order != 0: ik["order"] = order
        if mix != 1: ik["mix"] = mix
        if bend != 1: ik["bendPositive"] = bend > 0
        ik_constraints.append(ik); ik_names.append(name)
    if ik_constraints: result["ik"] = ik_constraints

    # Transform constraints
    tc_count = r.readVarint(True)
    tc_list = []; tc_names = []
    for i in range(tc_count):
        name = r.readString(); order = r.readVarint(True)
        bc = r.readVarint(True); bone_indices = [r.readVarint(True) for _ in range(bc)]
        target = r.readVarint(True)
        local = r.readBoolean(); relative = r.readBoolean()
        oR = r.readFloat(); oX = r.readFloat() * scale; oY = r.readFloat() * scale
        oSX = r.readFloat(); oSY = r.readFloat(); oSHY = r.readFloat()
        rMix = r.readFloat(); tMix = r.readFloat(); sMix = r.readFloat(); shMix = r.readFloat()
        tc = {"name": name, "bones": [bone_names[idx] for idx in bone_indices], "target": bone_names[target]}
        if order != 0: tc["order"] = order
        if rMix != 1: tc["rotateMix"] = rMix
        if tMix != 1: tc["translateMix"] = tMix
        if sMix != 1: tc["scaleMix"] = sMix
        if shMix != 1: tc["shearMix"] = shMix
        if local: tc["local"] = local
        if relative: tc["relative"] = relative
        tc["offsetRotation"] = oR; tc["offsetX"] = oX; tc["offsetY"] = oY
        tc["offsetScaleX"] = oSX; tc["offsetScaleY"] = oSY; tc["offsetShearY"] = oSHY
        tc_list.append(tc); tc_names.append(name)
    if tc_list: result["transform"] = tc_list

    # Path constraints
    pc_count = r.readVarint(True)
    pc_list = []; pc_names = []
    for i in range(pc_count):
        name = r.readString(); order = r.readVarint(True)
        bc = r.readVarint(True); bone_indices = [r.readVarint(True) for _ in range(bc)]
        slot_idx = r.readVarint(True)
        pMode = r.readVarint(True); sMode = r.readVarint(True); rMode = r.readVarint(True)
        oR = r.readFloat(); pos = r.readFloat()
        if pMode == 0: pos *= scale
        sp = r.readFloat()
        if sMode in (0, 1): sp *= scale
        rMix = r.readFloat(); tMix = r.readFloat()
        pc = {"name": name, "bones": [bone_names[idx] for idx in bone_indices], "target": slot_names[slot_idx]}
        if order != 0: pc["order"] = order
        pc["positionMode"] = ["fixed", "percent"][pMode] if pMode < 2 else "fixed"
        pc["spacingMode"] = ["length", "fixed", "percent"][sMode] if sMode < 3 else "length"
        pc["rotateMode"] = ["tangent", "chain", "chainScale"][rMode] if rMode < 3 else "tangent"
        pc["offsetRotation"] = oR; pc["position"] = pos; pc["spacing"] = sp
        pc["rotateMix"] = rMix; pc["translateMix"] = tMix
        pc_list.append(pc); pc_names.append(name)
    if pc_list: result["path"] = pc_list

    # Skins
    skin_names_list = []
    default_skin = read_skin(r, scale, nonessential, slot_names)
    skins = {}
    if default_skin:
        skins["default"] = default_skin
        skin_names_list.append("default")
    skin_count = r.readVarint(True)
    for i in range(skin_count):
        sn = r.readString()
        s = read_skin(r, scale, nonessential, slot_names)
        if s:
            skins[sn] = s
            skin_names_list.append(sn)
    if skins: result["skins"] = skins

    # Events
    event_count = r.readVarint(True)
    events = {}; event_names = []
    for i in range(event_count):
        name = r.readString(); iv = r.readVarint(False); fv = r.readFloat(); sv = r.readString()
        ev = {"int": iv, "float": fv}
        if sv: ev["string"] = sv
        events[name] = ev; event_names.append(name)
    if events: result["events"] = events

    # Animations
    anim_count = r.readVarint(True)
    animations = {}
    for i in range(anim_count):
        name = r.readString()
        anim = read_animation(r, bone_names, slot_names, ik_names, tc_names, pc_names, skin_names_list, scale, event_names)
        if anim: animations[name] = anim
    if animations: result["animations"] = animations

    return result


# ─── ETC1 texture decoder (Node.js via texture2ddecoder-wasm) ──────────────────

DECODE_JS_TEMPLATE = r"""
const t2d = require(process.argv[4]);
const fs = require('fs');

async function main() {
    await t2d.initialize();

    const pkm = fs.readFileSync(process.argv[2]);
    const w = pkm.readUInt16BE(12);
    const h = pkm.readUInt16BE(14);
    const etc1_raw = pkm.slice(20);
    const half_h = h / 2;
    const half_size = (w / 4) * (half_h / 4) * 8;

    // Decode top half (alpha) and bottom half (RGB)
    // texture2ddecoder-wasm outputs BGRA, so we swap R<->B
    const top = await t2d.decode_etc1(etc1_raw.slice(0, half_size), w, half_h);
    const bottom = await t2d.decode_etc1(etc1_raw.slice(half_size, half_size * 2), w, half_h);

    const rgba = Buffer.alloc(w * half_h * 4);
    for (let i = 0; i < w * half_h; i++) {
        rgba[i * 4 + 0] = bottom[i * 4 + 2];  // R = B (swapé BGR->RGB)
        rgba[i * 4 + 1] = bottom[i * 4 + 1];  // G = G
        rgba[i * 4 + 2] = bottom[i * 4 + 0];  // B = R (swapé BGR->RGB)
        rgba[i * 4 + 3] = top[i * 4 + 0];     // A = top.R (grayscale, canaux identiques)
    }

    fs.writeFileSync(process.argv[3], rgba);
    console.log(w + 'x' + half_h);
}

main().catch(err => { console.error(err); process.exit(1); });
"""


def decode_etc1_texture(pkm_data, output_png_path):
    """Decode ETC1 PKM data to PNG using texture2ddecoder-wasm (Node.js)."""
    from PIL import Image
    import numpy as np

    # Write PKM to temp file
    tmpdir = tempfile.mkdtemp(prefix="etc1_")
    pkm_path = os.path.join(tmpdir, "input.pkm")
    raw_path = os.path.join(tmpdir, "output.raw")

    with open(pkm_path, 'wb') as f:
        f.write(pkm_data)

    # Write the JS decoder script
    js_path = os.path.join(tmpdir, "decode.js")
    with open(js_path, 'w') as f:
        f.write(DECODE_JS_TEMPLATE)

    # Find texture2ddecoder-wasm module path
    # Try: script dir, cwd, parent dirs
    module_path = None
    search_dirs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'node_modules', 'texture2ddecoder-wasm'),
        os.path.join(os.getcwd(), 'node_modules', 'texture2ddecoder-wasm'),
        os.path.join(os.getcwd(), '..', 'node_modules', 'texture2ddecoder-wasm'),
    ]
    for sd in search_dirs:
        if os.path.isdir(sd):
            module_path = os.path.abspath(sd)
            break

    if not module_path:
        # Try npm root to find global modules
        try:
            npm_root = subprocess.check_output(['npm', 'root'], text=True).strip()
            candidate = os.path.join(npm_root, 'texture2ddecoder-wasm')
            if os.path.isdir(candidate):
                module_path = candidate
        except Exception:
            pass

    if not module_path:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(
            "texture2ddecoder-wasm not found! Install it with: npm install texture2ddecoder-wasm"
        )

    result = subprocess.run(
        ['node', js_path, pkm_path, raw_path, module_path],
        capture_output=True, text=True, env=os.environ.copy()
    )

    if result.returncode != 0:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"texture2ddecoder-wasm failed: {result.stderr}")

    # Read dimensions from stdout (e.g. "1024x1024")
    dims = result.stdout.strip()
    if 'x' not in dims:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"Unexpected decoder output: {result.stdout}")

    w_str, h_str = dims.split('x')
    w, h = int(w_str), int(h_str)

    # Convert raw RGBA to PNG
    with open(raw_path, 'rb') as f:
        raw_data = f.read()

    expected = w * h * 4
    if len(raw_data) != expected:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"Raw size mismatch: {len(raw_data)} != {expected}")

    img = Image.frombytes('RGBA', (w, h), raw_data)
    img.save(output_png_path)

    shutil.rmtree(tmpdir, ignore_errors=True)
    return w, h


# ─── Archive helpers ──────────────────────────────────────────────────────────

def find_character_files(zf, char_name):
    """Find .skel, .atlas, .etc1 files for a character in the archive."""
    prefix = f"ETC1/world/units/{char_name}/spine/"
    files = [f for f in zf.namelist() if f.startswith(prefix)]

    if not files:
        return None

    # .skel — prefer <char_name>.skel, fallback to any .skel
    skel_path = f"{prefix}{char_name}.skel"
    if skel_path not in files:
        skels = [f for f in files if f.endswith('.skel')]
        skel_path = skels[0] if skels else None

    # .etc1 — prefer unit-DEFAULT-untrimmed, exclude smallcombat
    etc1s = [f for f in files if f.endswith('.etc1') and 'unit-DEFAULT' in f and 'smallcombat' not in f]
    if not etc1s:
        etc1s = [f for f in files if f.endswith('.etc1') and 'smallcombat' not in f]
    if not etc1s:
        etc1s = [f for f in files if f.endswith('.etc1')]
    etc1_path = etc1s[0] if etc1s else None

    # .atlas — prefer unit-DEFAULT-untrimmed, exclude smallcombat
    atlases = [f for f in files if f.endswith('.atlas') and 'unit-DEFAULT' in f and 'smallcombat' not in f]
    if not atlases:
        atlases = [f for f in files if f.endswith('.atlas') and 'smallcombat' not in f]
    if not atlases:
        atlases = [f for f in files if f.endswith('.atlas')]
    atlas_path = atlases[0] if atlases else None

    return {
        'skel': skel_path,
        'etc1': etc1_path,
        'atlas': atlas_path,
    }


def fix_atlas(atlas_text):
    """Replace .etc1 page names with texture.png in atlas text."""
    lines = atlas_text.split('\n')
    fixed = []
    for line in lines:
        stripped = line.strip()
        if stripped.endswith('.etc1'):
            fixed.append('texture.png')
        else:
            fixed.append(line)
    return '\n'.join(fixed)


def list_characters_in_archive(archive_path):
    """List all character names found in an archive."""
    zf = zipfile.ZipFile(archive_path)
    seen = set()
    for name in zf.namelist():
        if name.startswith('ETC1/world/units/') and '/spine/' in name:
            parts = name.split('/')
            if len(parts) >= 5:
                seen.add(parts[3])
    return sorted(seen)


def prepare_character(char_name, archive_path, output_dir='characters', force=False):
    """Full pipeline: extract & prepare a character from archive to viewer-ready files."""
    print(f"\n{'='*60}")
    print(f"  Preparing: {char_name}")
    print(f"  Archive:   {archive_path}")
    print(f"  Output:    {output_dir}/{char_name}/")
    print(f"{'='*60}")

    char_dir = os.path.join(output_dir, char_name)
    texture_path = os.path.join(char_dir, 'texture.png')
    skel_json_path = os.path.join(char_dir, 'skeleton.json')
    atlas_path = os.path.join(char_dir, 'atlas.atlas')

    # Check if already exists
    if not force and os.path.exists(texture_path) and os.path.exists(skel_json_path) and os.path.exists(atlas_path):
        print(f"  ⚠ Already exists — use --force to overwrite")
        return False

    os.makedirs(char_dir, exist_ok=True)

    # 1. Open archive and find files
    print(f"\n  [1/5] Scanning archive...")
    zf = zipfile.ZipFile(archive_path)
    paths = find_character_files(zf, char_name)

    if not paths:
        print(f"  ✗ Character '{char_name}' not found in {archive_path}")
        return False

    if not paths['skel'] or not paths['etc1'] or not paths['atlas']:
        print(f"  ✗ Missing files: skel={paths['skel']}, etc1={paths['etc1']}, atlas={paths['atlas']}")
        return False

    print(f"    skel:  {paths['skel']}")
    print(f"    etc1:  {paths['etc1']}")
    print(f"    atlas: {paths['atlas']}")

    # 2. Extract & decompress .etc1 → PKM
    print(f"\n  [2/5] Decompressing ETC1 (gzip → PKM)...")
    etc1_compressed = zf.read(paths['etc1'])
    pkm_data = gzip.decompress(etc1_compressed)

    w = struct.unpack('>H', pkm_data[12:14])[0]
    h = struct.unpack('>H', pkm_data[14:16])[0]
    print(f"    PKM: {w}x{h} (visible: {w}x{h // 2})")

    # 3. Decode ETC1 → PNG
    print(f"\n  [3/5] Decoding ETC1 → PNG (texture2ddecoder-wasm)...")
    tex_w, tex_h = decode_etc1_texture(pkm_data, texture_path)
    print(f"    texture.png: {tex_w}x{tex_h}")

    # 4. Convert .skel → JSON
    print(f"\n  [4/5] Converting .skel → skeleton.json...")
    skel_data = zf.read(paths['skel'])
    skeleton = convert_skel_to_json(skel_data)
    with open(skel_json_path, 'w') as f:
        json.dump(skeleton, f, separators=(',', ':'))

    nb = len(skeleton.get('bones', []))
    ns = len(skeleton.get('slots', []))
    na = len(skeleton.get('animations', {}))
    anims = list(skeleton.get('animations', {}).keys())
    print(f"    {nb} bones, {ns} slots, {na} animations")
    print(f"    anims: {anims}")

    # 5. Fix atlas
    print(f"\n  [5/5] Fixing atlas (.etc1 → texture.png)...")
    atlas_text = zf.read(paths['atlas']).decode('utf-8')
    atlas_text = fix_atlas(atlas_text)
    with open(atlas_path, 'w') as f:
        f.write(atlas_text)
    print(f"    atlas.atlas written")

    print(f"\n  ✓ Done! → {char_dir}/")
    print(f"    texture.png  ({tex_w}x{tex_h})")
    print(f"    skeleton.json ({nb} bones, {na} anims)")
    print(f"    atlas.atlas")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Extract & prepare a Disney Heroes character from a game archive ZIP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s molly_mcgee /tmp/archives/world_add_326.zip
  %(prog)s molly_mcgee,yokai /tmp/archives/world_add_326.zip --output characters/
  %(prog)s --list /tmp/archives/world_add_326.zip
        """,
    )
    parser.add_argument('character', nargs='?', help='Character name (or comma-separated list)')
    parser.add_argument('archive', nargs='?', help='Path to the game archive ZIP')
    parser.add_argument('--output', '-o', default='characters', help='Output directory (default: characters)')
    parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing files')
    parser.add_argument('--list', '-l', action='store_true', help='List characters in archive')

    args = parser.parse_args()

    if args.list:
        archive = args.archive or args.character
        if not archive:
            parser.error("--list requires an archive path")
        chars = list_characters_in_archive(archive)
        print(f"\n{len(chars)} characters in {archive}:\n")
        for c in chars:
            print(f"  {c}")
        return

    if not args.character or not args.archive:
        parser.error("character name and archive path are required")

    names = [n.strip() for n in args.character.split(',')]
    success = 0
    for name in names:
        try:
            if prepare_character(name, args.archive, args.output, args.force):
                success += 1
        except Exception as e:
            print(f"\n  ✗ {name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"  {success}/{len(names)} characters prepared successfully")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
