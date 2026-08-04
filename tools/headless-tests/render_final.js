const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { createCanvas, Image } = require('canvas');

const CHAR_DIR = process.argv[2];
const ANIM = process.argv[3] || null;
const OUT = process.argv[4] || '/tmp/headless-test/out.png';

const spineSrc = fs.readFileSync('/app/conversations/6a304a82c4136b7283561729/spine-canvas.js', 'utf8');
const sandbox = { console, Image, document: { createElement: () => ({}) }, window: {} };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(spineSrc, sandbox, { filename: 'spine-canvas.js' });
const spine = sandbox.spine;

const atlasText = fs.readFileSync(path.join(CHAR_DIR, 'atlas.atlas'), 'utf8');
const jsonText = fs.readFileSync(path.join(CHAR_DIR, 'skeleton.json'), 'utf8');
const img = new Image();
img.src = fs.readFileSync(path.join(CHAR_DIR, 'texture.png'));
const texture = new spine.canvas.CanvasTexture(img);
const atlas = new spine.TextureAtlas(atlasText, function(p) { return texture; });
const attachmentLoader = new spine.AtlasAttachmentLoader(atlas);
const json = new spine.SkeletonJson(attachmentLoader);
const skeletonData = json.readSkeletonData(JSON.parse(jsonText));
const skeleton = new spine.Skeleton(skeletonData);

// Smart skin selection
const skinNames = skeletonData.skins.map(s => s.name);
let bestSkin = skinNames[0], bestCount = 0;
for (const sn of skinNames) {
  const skin = skeletonData.findSkin(sn);
  let count = 0;
  if (skin) {
    for (let i = 0; i < skeletonData.slots.length; i++) {
      if (skin.getAttachment(i, skeletonData.slots[i].attachmentName) != null) count++;
    }
  }
  if (count > bestCount) { bestCount = count; bestSkin = sn; }
}
skeleton.setSkinByName(bestSkin);
skeleton.setSlotsToSetupPose();

const stateData = new spine.AnimationStateData(skeletonData);
const state = new spine.AnimationState(stateData);
const animNames = skeletonData.animations.map(a => a.name);
const animName = ANIM || (animNames.includes('idle') ? 'idle' : animNames[0]);
state.setAnimation(0, animName, true);
state.update(0.5);
state.apply(skeleton);
skeleton.updateWorldTransform();

const canvas = createCanvas(800, 800);
const ctx = canvas.getContext('2d');
ctx.fillStyle = '#1a1a2e';
ctx.fillRect(0, 0, 800, 800);
const renderer = new spine.canvas.SkeletonRenderer(ctx);
renderer.triangleRendering = true;
ctx.save();
const w = skeletonData.width || 500, h = skeletonData.height || 800;
const fitScale = Math.min(800/w*0.8, 800/h*0.9);
ctx.translate(400, 736);
ctx.scale(fitScale, -fitScale);
renderer.draw(skeleton);
ctx.restore();

const imgData = ctx.getImageData(0,0,800,800);
let count=0;
for(let i=0;i<imgData.data.length;i+=4){
  if(!(imgData.data[i]===26&&imgData.data[i+1]===26&&imgData.data[i+2]===46)) count++;
}
const charName = path.basename(CHAR_DIR);
console.log(`${charName}: skin=${bestSkin} anim=${animName} pixels=${count}`);

const out = fs.createWriteStream(OUT);
canvas.createPNGStream().pipe(out);
