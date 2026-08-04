const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { Image } = require('canvas');

const spineSrc = fs.readFileSync('/app/conversations/6a304a82c4136b7283561729/spine-canvas.js', 'utf8');
const sandbox = { console, Image, document: { createElement: () => ({}) }, window: {} };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(spineSrc, sandbox, { filename: 'spine-canvas.js' });
const spine = sandbox.spine;

function debugChar(charDir, charName) {
  console.log(`\n=== ${charName} ===`);
  const atlasText = fs.readFileSync(path.join(charDir, 'atlas.atlas'), 'utf8');
  const jsonText = fs.readFileSync(path.join(charDir, 'skeleton.json'), 'utf8');
  const img = new Image();
  img.src = fs.readFileSync(path.join(charDir, 'texture.png'));
  
  const texture = new spine.canvas.CanvasTexture(img);
  const atlas = new spine.TextureAtlas(atlasText, function(p) { return texture; });
  const attachmentLoader = new spine.AtlasAttachmentLoader(atlas);
  const json = new spine.SkeletonJson(attachmentLoader);
  const skeletonData = json.readSkeletonData(JSON.parse(jsonText));
  const skeleton = new spine.Skeleton(skeletonData);
  
  const skinNames = skeletonData.skins.map(s => s.name);
  const defaultSkin = skinNames.includes('default') ? 'default' : skinNames[0];
  skeleton.setSkinByName(defaultSkin);
  skeleton.setSlotsToSetupPose();
  skeleton.updateWorldTransform();
  
  let withAtt = 0, withoutAtt = 0;
  let meshCount = 0, regionCount = 0;
  for (const slot of skeleton.slots) {
    const att = slot.getAttachment();
    if (att) {
      withAtt++;
      if (att.constructor.name === 'MeshAttachment') meshCount++;
      else if (att.constructor.name === 'RegionAttachment') regionCount++;
    } else {
      withoutAtt++;
    }
  }
  console.log(`  skin: ${defaultSkin}, slots with att: ${withAtt}, without: ${withoutAtt}`);
  console.log(`  meshes: ${meshCount}, regions: ${regionCount}`);
  
  // Try different skins for dash
  if (charName === 'dash') {
    for (const skinName of skinNames) {
      skeleton.setSkinByName(skinName);
      skeleton.setSlotsToSetupPose();
      skeleton.updateWorldTransform();
      let c = 0;
      for (const slot of skeleton.slots) {
        if (slot.getAttachment()) c++;
      }
      console.log(`  skin="${skinName}": ${c} slots with attachment`);
    }
    // Reset to hero
    skeleton.setSkinByName('hero');
    skeleton.setSlotsToSetupPose();
    skeleton.updateWorldTransform();
  }
  
  // Advance animation
  const animNames = skeletonData.animations.map(a => a.name);
  const animName = animNames.includes('idle') ? 'idle' : animNames[0];
  const stateData = new spine.AnimationStateData(skeletonData);
  const state = new spine.AnimationState(stateData);
  state.setAnimation(0, animName, true);
  state.update(0.5);
  state.apply(skeleton);
  skeleton.updateWorldTransform();
  
  let withAttAfter = 0;
  for (const slot of skeleton.slots) {
    if (slot.getAttachment()) withAttAfter++;
  }
  console.log(`  after anim "${animName}" (0.5s): ${withAttAfter} slots with attachment`);
}

debugChar('/app/conversations/6a304a82c4136b7283561729/characters/jack_skellington', 'jack_skellington');
debugChar('/app/conversations/6a304a82c4136b7283561729/characters/dash', 'dash');
