const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { createCanvas, Image } = require('canvas');

const CHAR_DIR = process.argv[2] || '/app/conversations/6a304a82c4136b7283561729/characters/aladdin';
const ANIM = process.argv[3] || null;
const OUT = process.argv[4] || '/tmp/headless-test/out.png';

const spineSrc = fs.readFileSync('/app/conversations/6a304a82c4136b7283561729/spine-canvas.js', 'utf8');
const sandbox = { console, Image, document: { createElement: () => ({}) }, window: {} };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(spineSrc, sandbox, { filename: 'spine-canvas.js' });
const spine = sandbox.spine;

async function main() {
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
  
  // Auto-select skin if no "default"
  const skinNames = skeletonData.skins.map(s => s.name);
  const defaultSkin = skinNames.includes('default') ? 'default' : skinNames[0];
  if (defaultSkin) {
    skeleton.setSkinByName(defaultSkin);
    skeleton.setSlotsToSetupPose();
  }
  console.log('Skins:', skinNames, '→ using:', defaultSkin);
  
  const stateData = new spine.AnimationStateData(skeletonData);
  const state = new spine.AnimationState(stateData);
  const animNames = skeletonData.animations.map(a => a.name);
  const animName = ANIM || (animNames.includes('idle') ? 'idle' : animNames[0]);
  console.log('Animation:', animName, 'of', animNames.length);
  state.setAnimation(0, animName, true);
  state.update(0.3);
  state.apply(skeleton);
  skeleton.updateWorldTransform();
  
  const canvas = createCanvas(800, 800);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, 800, 800);
  
  const renderer = new spine.canvas.SkeletonRenderer(ctx);
  renderer.triangleRendering = true;
  
  ctx.save();
  const w = (skeletonData.width || 500);
  const h = (skeletonData.height || 800);
  const sx = canvas.width / w * 0.8;
  const sy = canvas.height / h * 0.9;
  const fitScale = Math.min(sx, sy);
  ctx.translate(canvas.width / 2, canvas.height * 0.92);
  ctx.scale(fitScale, -fitScale);
  
  try {
    renderer.draw(skeleton);
  } catch (e) {
    console.error('DRAW ERROR:', e.message);
  }
  ctx.restore();
  
  // Count non-background pixels
  const imgData = ctx.getImageData(0, 0, 800, 800);
  let count = 0;
  for (let i = 0; i < imgData.data.length; i += 4) {
    const r = imgData.data[i], g = imgData.data[i+1], b = imgData.data[i+2];
    if (!(r === 26 && g === 26 && b === 46)) count++;
  }
  console.log(`Non-bg pixels: ${count}`);
  
  const out = fs.createWriteStream(OUT);
  canvas.createPNGStream().pipe(out);
  out.on('finish', () => console.log('Saved', OUT));
}

main().catch(e => { console.error(e); process.exit(1); });
