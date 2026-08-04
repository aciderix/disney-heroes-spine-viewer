# Disney Heroes Spine Viewer - Development & Debug Tools

This directory contains development, conversion, debugging, and headless testing scripts created for the Disney Heroes Spine viewer project.

---

## Directory Overview

```
tools/
├── fix_uvs.py
├── simulate_bones.py
├── spine_skel_to_json.py
├── upload_to_github.py
├── README.md
└── headless-tests/
    ├── debug_buzz.js
    ├── debug_jack_dash.js
    ├── debug_slots.js
    ├── debug_verts.js
    ├── jack_timing.js
    ├── render_final.js
    ├── render_test.js
    └── render_test2.js
```

---

## Python Utilities (`tools/`)

### 1. `spine_skel_to_json.py`
- **Description:** Decodes binary Spine 3.6 skeleton files (`.skel`) into human-readable Spine `.json` files.
- **Usage:**
  ```bash
  python tools/spine_skel_to_json.py <path/to/skeleton.skel> [path/to/output.json]
  ```
- **Notes:** Handles standard Spine binary decoding, including bones, slots, IK/transform constraints, skins, attachments (region, mesh, weighted mesh), and animation keyframes.

### 2. `fix_uvs.py`
- **Description:** Converts mesh attachment UV coordinates in skeleton JSON from normalized (0–1) atlas-space coordinates to region-relative pixel coordinates using region metadata from `.atlas` files.
- **Usage:**
  ```bash
  python tools/fix_uvs.py <path/to/skeleton.json> <path/to/atlas.atlas>
  ```
- **Notes:** Useful when skeleton JSON mesh UVs are formatted for standalone textures rather than texture atlas subregions.

### 3. `simulate_bones.py`
- **Description:** Computes world transforms (position, rotation, scale, shear) across parent-child bone hierarchies without needing a browser or full Spine runtime.
- **Usage:**
  ```bash
  python tools/simulate_bones.py
  ```
- **Notes:** Reads skeleton structure (defaulting to `characters/aladdin/skeleton.json`) and prints computed world positions and rotations for debugging hierarchy transforms.

### 4. `upload_to_github.py`
- **Description:** Automated script to commit and upload files directly to the GitHub repository (`aciderix/disney-heroes-spine-viewer`) using the GitHub REST / Git Trees API.
- **Usage:**
  ```bash
  GITHUB_TOKEN="your_github_token" python tools/upload_to_github.py
  ```
- **Notes:** Pushes tracked project assets and code changes without requiring local Git CLI credentials or setup.

---

## Headless Testing Scripts (`tools/headless-tests/`)

These Node.js scripts run in a headless environment using `node-canvas` and the Spine 2D Canvas runtime (`spine-canvas.js`).

### 1. `render_final.js`
- **Description:** Renders a character's animation frame to a PNG image file using node-canvas.
- **Usage:**
  ```bash
  node tools/headless-tests/render_final.js <character_dir> [animation_name] [output_path.png]
  ```
- **Example:**
  ```bash
  node tools/headless-tests/render_final.js characters/aladdin idle /tmp/aladdin_render.png
  ```

### 2. `render_test.js` & `render_test2.js`
- **Description:** Initial and updated prototype rendering scripts for testing canvas-based character pose and animation rendering offscreen.
- **Usage:**
  ```bash
  node tools/headless-tests/render_test.js [character_dir] [animation_name] [output_path.png]
  node tools/headless-tests/render_test2.js [character_dir] [animation_name] [output_path.png]
  ```

### 3. `debug_buzz.js`
- **Description:** Focused debug script for inspecting Buzz Lightyear's skeleton, texture atlas, attachment loader, and slot configurations.
- **Usage:**
  ```bash
  node tools/headless-tests/debug_buzz.js
  ```

### 4. `debug_jack_dash.js`
- **Description:** Debug script for analyzing rendering artifacts, missing textures, and transform issues specific to Jack Skellington and Dash skeletons.
- **Usage:**
  ```bash
  node tools/headless-tests/debug_jack_dash.js
  ```

### 5. `debug_slots.js`
- **Description:** Dumps detailed slot and attachment state information (visibility, texture references, drawing order) for skeleton debugging.
- **Usage:**
  ```bash
  node tools/headless-tests/debug_slots.js
  ```

### 6. `debug_verts.js`
- **Description:** Calculates and prints computed world vertex coordinates for mesh attachments to diagnose skinning/deformation issues.
- **Usage:**
  ```bash
  node tools/headless-tests/debug_verts.js
  ```

### 7. `jack_timing.js`
- **Description:** Tests animation timeline stepping, frame timing, and track update logic for Jack Skellington animations.
- **Usage:**
  ```bash
  node tools/headless-tests/jack_timing.js
  ```
