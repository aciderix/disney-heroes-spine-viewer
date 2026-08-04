const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { createCanvas, Image } = require('canvas');

const CHAR_DIR = '/app/conversations/6a304a82c4136b7283561729/characters/jack_skellington';
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
skeleton.setSkinByName('default');
skeleton.setSlotsToSetupPose();
skeleton.updateWorldTransform();

// Check setup pose without animation
const slot = skeleton.slots[0];
const att = slot.getAttachment();
console.log('Slot:', slot.data.name, 'Attachment:', att ? att.name : 'null', att ? att.constructor.name : '');
const out = new Float32Array(att.worldVerticesLength);
att.computeWorldVertices(slot, 0, att.worldVerticesLength, out, 0, 2);
let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
for (let i=0;i<out.length;i+=2) {
  if(out[i]<minX)minX=out[i]; if(out[i]>maxX)maxX=out[i];
  if(out[i+1]<minY)minY=out[i+1]; if(out[i+1]>maxY)maxY=out[i+1];
}
console.log('Setup pose BBox:', {minX, maxX, minY, maxY});

// Try rendering setup pose
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
console.log('Setup pose non-bg pixels:', count);
