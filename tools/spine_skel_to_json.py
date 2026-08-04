#!/usr/bin/env python3
"""Convert Spine 3.6 binary skeleton (.skel) to JSON format."""

import struct, json, sys

class BinaryReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
    def readByte(self):
        b = self.data[self.pos]; self.pos += 1; return b
    def readBoolean(self): return self.readByte() != 0
    def readInt(self):
        r = self.readByte(); r <<= 8; r |= self.readByte(); r <<= 8; r |= self.readByte(); r <<= 8; r |= self.readByte()
        if r > 0x7FFFFFFF: r -= 0x100000000
        return r
    def readVarint(self, optimizePositive=True):
        b = self.readByte(); v = b & 0x7F
        if b & 0x80:
            b = self.readByte(); v |= (b & 0x7F) << 7
            if b & 0x80:
                b = self.readByte(); v |= (b & 0x7F) << 14
                if b & 0x80:
                    b = self.readByte(); v |= (b & 0x7F) << 21
                    if b & 0x80: v |= (self.readByte() & 0x7F) << 28
        if not optimizePositive: v = (v >> 1) ^ (-(v & 1))
        return v
    def readFloat(self):
        return struct.unpack('f', struct.pack('i', self.readInt()))[0]
    def readString(self):
        length = self.readVarint(True)
        if length == 0: return None
        s = self.data[self.pos:self.pos + length - 1]; self.pos += length - 1
        return s.decode('utf-8', errors='replace')
    def readColor(self):
        return (self.readByte()/255, self.readByte()/255, self.readByte()/255, self.readByte()/255)
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
        """Returns a flat array matching the Spine JSON format."""
        verticesLength = vertexCount * 2
        weighted = self.readBoolean()
        if not weighted:
            return self.readFloatArray(verticesLength, scale)
        # Weighted: interleave [boneCount, boneIdx, x, y, weight, ...]
        result = []
        for _ in range(vertexCount):
            boneCount = self.readVarint(True)
            result.append(boneCount)
            for _ in range(boneCount):
                result.append(self.readVarint(True))  # bone index
                result.append(self.readFloat() * scale)  # x
                result.append(self.readFloat() * scale)  # y
                result.append(self.readFloat())  # weight
        return result


def convert_skel_to_json(skel_path, scale=1.0):
    with open(skel_path, 'rb') as f:
        data = f.read()
    r = BinaryReader(data)
    result = {}

    # Skeleton metadata — JSON uses "spine" key
    hash_val = r.readString(); version = r.readString()
    width = r.readFloat(); height = r.readFloat()
    nonessential = r.readBoolean()
    skeleton_info = {"hash": hash_val or "", "spine": version or "", "width": width, "height": height}
    if nonessential: r.readFloat(); r.readString()
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
        if color != (1,1,1,1):
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
        oR = r.readFloat(); oX = r.readFloat()*scale; oY = r.readFloat()*scale
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
        if sMode in (0,1): sp *= scale
        rMix = r.readFloat(); tMix = r.readFloat()
        pc = {"name": name, "bones": [bone_names[idx] for idx in bone_indices], "target": slot_names[slot_idx]}
        if order != 0: pc["order"] = order
        pc["positionMode"] = ["fixed","percent"][pMode] if pMode < 2 else "fixed"
        pc["spacingMode"] = ["length","fixed","percent"][sMode] if sMode < 3 else "length"
        pc["rotateMode"] = ["tangent","chain","chainScale"][rMode] if rMode < 3 else "tangent"
        pc["offsetRotation"] = oR; pc["position"] = pos; pc["spacing"] = sp
        pc["rotateMix"] = rMix; pc["translateMix"] = tMix
        pc_list.append(pc); pc_names.append(name)
    if pc_list: result["path"] = pc_list

    # Skins — keyed by slot NAME
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


def read_skin(r, scale, nonessential, slot_names):
    slot_count = r.readVarint(True)
    if slot_count == 0: return None
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
        rotation = r.readFloat(); x = r.readFloat()*scale; y = r.readFloat()*scale
        scaleX = r.readFloat(); scaleY = r.readFloat()
        width = r.readFloat()*scale; height = r.readFloat()*scale
        color = r.readColor()
        att = {"type": "region", "path": path}
        if rotation != 0: att["rotation"] = rotation
        if x != 0: att["x"] = x
        if y != 0: att["y"] = y
        if scaleX != 1: att["scaleX"] = scaleX
        if scaleY != 1: att["scaleY"] = scaleY
        att["width"] = width; att["height"] = height
        if color != (1,1,1,1):
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
        if color != (1,1,1,1):
            att["color"] = f"{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}{int(color[3]*255):02x}"
        if nonessential:
            att["edges"] = r.readShortArray()
            att["width"] = r.readFloat()*scale; att["height"] = r.readFloat()*scale
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
        if color != (1,1,1,1):
            att["color"] = f"{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}{int(color[3]*255):02x}"
        if nonessential:
            att["width"] = r.readFloat()*scale; att["height"] = r.readFloat()*scale
        return att

    elif att_type == 4:  # PATH
        closed = r.readBoolean(); constantSpeed = r.readBoolean()
        vc = r.readVarint(True)
        verts = r.readVertices(vc, scale)
        ll = vc // 3
        lengths = [r.readFloat()*scale for _ in range(ll)]
        att = {"type": "path", "vertexCount": vc, "vertices": verts, "closed": closed, "constantSpeed": constantSpeed}
        att["lengths"] = lengths
        if nonessential: r.readInt()
        return att

    elif att_type == 5:  # POINT
        rotation = r.readFloat(); x = r.readFloat()*scale; y = r.readFloat()*scale
        att = {"type": "point"}
        if rotation != 0: att["rotation"] = rotation
        if x != 0: att["x"] = x
        if y != 0: att["y"] = y
        if nonessential:
            color = r.readColor()
            if color != (1,1,1,1):
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
                    if f < fc-1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                slots_data.setdefault(sn, {})["color"] = frames
            elif tt == 2:
                frames = []
                for f in range(fc):
                    time = r.readFloat(); light = r.readColor(); dark = r.readColor()
                    fr = {"time": time, "light": f"{int(light[0]*255):02x}{int(light[1]*255):02x}{int(light[2]*255):02x}{int(light[3]*255):02x}"}
                    fr["dark"] = f"{int(dark[1]*255):02x}{int(dark[2]*255):02x}{int(dark[3]*255):02x}"
                    if f < fc-1: fr["curve"] = r.readCurve()
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
                    if f < fc-1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                bones_data.setdefault(bn, {})["rotate"] = frames
            elif tt in (1,2,3):
                ts = scale if tt == 1 else 1.0
                kn = ["translate","scale","shear"][tt-1]
                frames = []
                for f in range(fc):
                    time = r.readFloat(); x = r.readFloat()*ts; y = r.readFloat()*ts
                    fr = {"time": time, "x": x, "y": y}
                    if f < fc-1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                bones_data.setdefault(bn, {})[kn] = frames
    if bones_data: anim["bones"] = bones_data

    # IK timelines — keyed by constraint name
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
            if f < fc-1: fr["curve"] = r.readCurve()
            frames.append(fr)
        ik_data[ik_names[idx]] = frames
    if ik_data: anim["ik"] = ik_data

    # Transform timelines — keyed by constraint name
    tcc = r.readVarint(True)
    tc_data = {}
    for i in range(tcc):
        idx = r.readVarint(True); fc = r.readVarint(True)
        frames = []
        for f in range(fc):
            time = r.readFloat()
            fr = {"time": time, "rotateMix": r.readFloat(), "translateMix": r.readFloat(), "scaleMix": r.readFloat(), "shearMix": r.readFloat()}
            if f < fc-1: fr["curve"] = r.readCurve()
            frames.append(fr)
        tc_data[tc_names[idx]] = frames
    if tc_data: anim["transform"] = tc_data

    # Path timelines — keyed by constraint name
    pcc = r.readVarint(True)
    pc_data = {}
    for i in range(pcc):
        idx = r.readVarint(True); tlc = r.readVarint(True)
        for j in range(tlc):
            tt = r.readByte(); fc = r.readVarint(True)
            if tt in (0,1):
                kn = "position" if tt == 0 else "spacing"
                frames = []
                for f in range(fc):
                    time = r.readFloat(); val = r.readFloat()
                    fr = {"time": time, kn: val}
                    if f < fc-1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                pc_data.setdefault(pc_names[idx], {})[kn] = frames
            elif tt == 2:
                frames = []
                for f in range(fc):
                    time = r.readFloat()
                    fr = {"time": time, "rotateMix": r.readFloat(), "translateMix": r.readFloat()}
                    if f < fc-1: fr["curve"] = r.readCurve()
                    frames.append(fr)
                pc_data.setdefault(pc_names[idx], {})["mix"] = frames
    if pc_data: anim["path"] = pc_data

    # Deform timelines — nested: skin_name -> slot_name -> attachment_name
    dc = r.readVarint(True)
    deform_data = {}
    for i in range(dc):
        skin_idx = r.readVarint(True)
        skin_name = skin_names[skin_idx] if skin_idx < len(skin_names) else f"skin_{skin_idx}"
        sc = r.readVarint(True)
        for j in range(sc):
            si = r.readVarint(True)
            sn = slot_names[si]
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
                    if f < fc-1: fr["curve"] = r.readCurve()
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


if __name__ == "__main__":
    skel_path = sys.argv[1]
    json_path = sys.argv[2] if len(sys.argv) > 2 else skel_path.replace('.skel', '.json')
    print(f"Converting {skel_path} -> {json_path}")
    result = convert_skel_to_json(skel_path)
    with open(json_path, 'w') as f:
        json.dump(result, f, separators=(',', ':'))
    print(f"Done! Bones: {len(result.get('bones',[]))}, Slots: {len(result.get('slots',[]))}, Animations: {len(result.get('animations',{}))}")
    print(f"Anim: {list(result.get('animations',{}).keys())[:20]}")
