// Real client handlers with mocked DOM/API: PATCH must own only fields of its action.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
function setup(code,published){
  const nodes=new Map();
  const q=id=>{if(!nodes.has(id))nodes.set(id,{value:id==='#edit-title'?' New title ':' New description ',checked:false,disabled:false});return nodes.get(id);};
  const patches=[];
  const context=vm.createContext({q,id:'event',published,event:{title:'Old',description:'Old description',status:published?'published':'draft',detailed:true},api:async(path,opt)=>patches.push(JSON.parse(JSON.stringify(opt.body))),stat(){},refresh:async()=>{}});
  vm.runInContext(code,context);
  return {q,patches};
}
test('settings save does not overwrite publication state',async()=>{
  const start=source.indexOf("q('#save').onclick=");
  const ui=setup(source.slice(start,source.indexOf("const input=q('#photos')",start)),true);
  await ui.q('#save').onclick();
  assert.deepEqual(ui.patches,[{title:'New title',description:'New description',detailed:false}]);
  assert.equal(ui.q('#save').disabled,false);
});
test('publish and pause do not overwrite title, description or detailed mode',async()=>{
  const start=source.indexOf("q('#toggle',box).onclick=");
  for(const published of [false,true]){
    const ui=setup('const box={};'+source.slice(start,source.indexOf("q('#copy',box)",start)),published);
    await ui.q('#toggle').onclick();
    assert.deepEqual(ui.patches,[{status:published?'paused':'published'}]);
  }
});
