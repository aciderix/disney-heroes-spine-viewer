import json, math

with open('characters/aladdin/skeleton.json') as f:
    d = json.load(f)

bones_data = {b['name']: b for b in d['bones']}
order = [b['name'] for b in d['bones']]

# world transform storage
world = {}

def compute(name, depth=0):
    if name in world:
        return world[name]
    b = bones_data[name]
    parent_name = b.get('parent')
    rotation = b.get('rotation', 0)
    x = b.get('x', 0)
    y = b.get('y', 0)
    scaleX = b.get('scaleX', 1)
    scaleY = b.get('scaleY', 1)
    shearX = b.get('shearX', 0)
    shearY = b.get('shearY', 0)
    
    if parent_name is None:
        # root: world = local (assuming skeleton x,y=0, scale=1)
        wx, wy = x, y
        wrot = rotation
        wsx, wsy = scaleX, scaleY
    else:
        pwx, pwy, pwrot, pwsx, pwsy = compute(parent_name, depth+1)
        # simplified "normal" inherit mode
        rad = math.radians(pwrot)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        # apply parent scale to local x,y then rotate by parent rotation
        la = x * pwsx
        lb = y * pwsy
        wx = pwx + la*cos_r - lb*sin_r
        wy = pwy + la*sin_r + lb*cos_r
        wrot = pwrot + rotation
        wsx = pwsx * scaleX
        wsy = pwsy * scaleY
    
    world[name] = (wx, wy, wrot, wsx, wsy)
    return world[name]

for name in order:
    compute(name)

# Print world positions, sorted by distance from origin (highlight outliers)
results = [(name, *world[name]) for name in order]
results.sort(key=lambda r: -(r[1]**2+r[2]**2)**0.5 if False else -(abs(r[1])+abs(r[2])))

print("Top 15 bones by |world position| (potential outliers):")
for name, wx, wy, wrot, wsx, wsy in results[:15]:
    print(f"  {name:25s} world=({wx:8.1f},{wy:8.1f}) rot={wrot:7.1f}")

print()
print("Key bones (root, head, body-related):")
for name in ['root', 'head', 'hip', 'chest', 'sword', 'sword_handle', 'hand-f', 'victory_hand-f']:
    if name in world:
        wx, wy, wrot, wsx, wsy = world[name]
        print(f"  {name:25s} world=({wx:8.1f},{wy:8.1f}) rot={wrot:7.1f}")
    else:
        print(f"  {name:25s} NOT FOUND")
