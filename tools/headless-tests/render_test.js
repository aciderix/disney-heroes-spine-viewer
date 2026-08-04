const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { createCanvas, Image } = require('canvas');

const CHAR_DIR = process.argv[2] || path.join('/app/conversations/6a304a82c4136b7283561729/characters/aladdin');
const ANIM = process.argv[3] || null;
const OUT = process.argv[4] || '/tmp/headless-test/out.png';

const spineSrc = fs.readFileSync('/app/conversations/6a304a82c4136b7283561729/spine-canvas.js', 'utf8');

const sandbox = {
  console,
  Image,
  document: { createElement: () => ({}) },
  window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(spineSrc, sandbox, { filename: 'spine-canvas.js' });
const spine = sandbox.spine;

async function main() {
  const atlasText = fs.readFileSync(path.join(CHAR_DIR, 'atlas.atlas'), 'utf8');
  const jsonText = fs.readFileSync(path.join(CHAR_DIR, 'skeleton.json'), 'utf8');
  const texPath = path.join(CHAR_DIR, 'texture.png');

  const img = new Image();
  img.src = fs.readFileSync(texPath);

  const texture = new spine.canvas.CanvasTexture(img);
  const atlas = new spine.TextureAtlas(atlasText, function(p) { return texture; });
  const attachmentLoader = new spine.AtlasAttachmentLoader(atlas);
  const json = new spine.SkeletonJson(attachmentLoader);
  const skeletonData = json.readSkeletonData(JSON.parse(jsonText));

  const skeleton = new spine.Skeleton(skeletonData);
  const stateData = new spine.AnimationStateData(skeletonData);
  const state = new spine.AnimationState(stateData);

  const animNames = skeletonData.animations.map(a => a.name);
  const animName = ANIM || (animNames.includes('idle') ? 'idle' : animNames[0]);
  console.log('Using animation:', animName, 'из', animNames.length, 'total');
  state.setAnimation(0, animName, true);

  // Advance a bit into the animation
  state.update(0.3);
  state.apply(skeleton);
  skeleton.updateWorldTransform();

  const canvas = createCanvas(800, 800);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#1a1f3a';
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
    console.log('Draw completed without error');
  } catch (e) {
    console.error('DRAW ERROR:', e.message);
    console.error(e.stack);
  }
  ctx.restore();

  const out = fs.createWriteStream(OUT);
  const stream = canvas.createPNGStream();
  stream.pipe(out);
  out.on('finish', () => console.log('Saved', OUT));

  // Compute bounding box of non-background pixels for sanity check
  const imgData = ctx.getImageData(0, 0, 800, 800);
  let minX=800,minY=800,maxX=0,maxY=0,count=0;
  for (let y=0;y<800;y++){
    for (let x=0;x<800;x++){
      const idx=(y*800+x)*4;
      const r=imgData.data[idx],g=imgData.data[idx+1],b=imgData.data[idx+2],a=imgData.data[idx+3];
      // background is #1a1f3a => (26,31,58)
      if (!(r===26 && g===31 && b===58) && a>10) {
        count++;
        if(x<minX)minX=x; if(x>maxX)maxX=x;
        if(y<minY)minY=y; if(y>maxY)maxY=y;
      }
    }
  }
  console.log(`Non-background pixels: ${count}`);
  console.log(`BBox: x[${minX},${maxX}] y[${minY},${maxY}]`);
}

main().catch(e => { console.error(e); process.exit(1); });
