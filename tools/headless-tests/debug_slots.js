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

for (const slot of skeleton.slots) {
  const att = slot.getAttachment();
  const name = slot.data.name;
  if (att) {
    const type = att.constructor.name;
    console.log(`${name}: attachment=${att.name} type=${type}`);
  } else {
    console.log(`${name}: attachment=NULL (expected: ${slot.data.attachmentName})`);
  }
}
