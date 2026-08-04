const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Image } = require('canvas');

const CHAR_DIR = '/app/conversations/6a304a82c4136b7283561729/characters/buzz_lightyear';
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
console.log('skeleton width/height:', skeletonData.width, skeletonData.height);
const skeleton = new spine.Skeleton(skeletonData);
skeleton.setToSetupPose();
skeleton.updateWorldTransform();

let withAtt = 0, withoutAtt = 0;
for (const slot of skeleton.slots) {
  if (slot.getAttachment()) withAtt++; else withoutAtt++;
}
console.log('slots with attachment:', withAtt, 'without:', withoutAtt);

// check body-like slot
const bodySlot = skeleton.slots.find(s => s.data.name === 'body' || s.data.name.includes('body'));
if (bodySlot) {
  console.log('found slot:', bodySlot.data.name, 'attachment:', bodySlot.getAttachment() ? bodySlot.getAttachment().name : null);
}

// dump first 10 slots and attachments with bbox
for (const slot of skeleton.slots.slice(0, 15)) {
  const att = slot.getAttachment();
  if (!att) { console.log(slot.data.name, 'NO ATTACHMENT'); continue; }
  console.log(slot.data.name, '->', att.name, att.constructor.name);
}
