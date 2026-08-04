const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Image } = require('canvas');

const CHAR_DIR = '/app/conversations/6a304a82c4136b7283561729/characters/aladdin';
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
skeleton.setToSetupPose();
skeleton.updateWorldTransform();

// Find "body" slot
const slot = skeleton.slots.find(s => s.data.name === 'body');
const att = slot.getAttachment();
console.log('Attachment:', att.name, att.constructor.name);
console.log('worldVerticesLength:', att.worldVerticesLength);
console.log('bones (weighted indices):', att.bones ? att.bones.slice(0,10) : 'none (unweighted)');
console.log('vertices.length:', att.vertices.length);

const out = new Float32Array(att.worldVerticesLength);
att.computeWorldVertices(slot, 0, att.worldVerticesLength, out, 0, 2);
console.log('World vertices (first 10):', Array.from(out.slice(0, 10)));
let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity, nanCount=0;
for (let i=0;i<out.length;i+=2) {
  const x = out[i], y = out[i+1];
  if (isNaN(x) || isNaN(y)) { nanCount++; continue; }
  if (x<minX) minX=x; if (x>maxX) maxX=x;
  if (y<minY) minY=y; if (y>maxY) maxY=y;
}
console.log(`BBox: x[${minX},${maxX}] y[${minY},${maxY}] nanCount=${nanCount}`);
