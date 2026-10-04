// Real client handlers with mocked DOM/API: PATCH must own only fields of its action.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
function setup(code,published){
  const nodes=new Map();
  const q=id=>{if(!nodes.has(id))nodes.set(id,{value:id==='#edit-title'?' New title ':' New description ',checked:false,disabled:false});return nodes.get(id);};
  const patches=[];
  const context=vm.createContext({q,id:'event',published,event:{title:'Old',description:'Old description',status:published?'published':'draft',detailed:true},changeSharing:action=>action(),api:async(path,opt)=>patches.push(JSON.parse(JSON.stringify(opt.body))),stat(){},refresh:async()=>{}});
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

function sharingUI({fail=false,confirm=true}={}){
  const nodes=new Map();
  const q=id=>{
    if(id==='.page-head .badge')return null;
    if(!nodes.has(id))nodes.set(id,{disabled:false,setAttribute(){},removeAttribute(){},addEventListener(type,handler){this.onclick=handler;}});
    return nodes.get(id);
  };
  const requests=[],messages=[];
  Object.defineProperty(q('#sharing'),'innerHTML',{set(){['#toggle','#rotate','#copy'].forEach(id=>q(id).disabled=false);}});
  let release;
  const waiting=new Promise(resolve=>release=resolve);
  const context=vm.createContext({q,qa:()=>['#toggle','#rotate','#copy'].map(q),id:'event',event:{status:'published',guest:'old',ready:1},esc:String,badge:()=>'',guestLink:()=>'',confirmAction:async()=>confirm,stat:(...args)=>messages.push(args),api:async(path)=>{requests.push(path);await waiting;if(fail)throw Error('Connection lost');return {guest:'new'};},refresh:async()=>{}});
  const start=source.indexOf('let sharingBusy=');
  const shareStart=start<0?source.indexOf('function share(e)'):start;
  vm.runInContext(source.slice(shareStart,source.indexOf('async function refresh()',shareStart))+';share(event);',context);
  return {q,requests,messages,release,context,leave:()=>nodes.delete('#sharing')};
}
test('sharing mutation blocks duplicate clicks and competing actions until response',async()=>{
  for(const action of ['#toggle','#rotate']){
    const ui=sharingUI();
    const first=ui.q(action).onclick();
    await Promise.resolve();await Promise.resolve();
    const second=ui.q(action).onclick();
    const competing=ui.q(action==='#toggle'?'#rotate':'#toggle').onclick();
    await Promise.resolve();await Promise.resolve();
    try{
      assert.equal(ui.requests.length,1);
      vm.runInContext('share(event)',ui.context);
      assert.equal(ui.q('#toggle').disabled,true);
      assert.equal(ui.q('#rotate').disabled,true);
      assert.equal(ui.q('#copy').disabled,true);
    }finally{ui.release();await Promise.all([first,second,competing]);}
    assert.equal(ui.q('#toggle').disabled,false);
    assert.equal(ui.q('#rotate').disabled,false);
  }
});
test('sharing controls recover after failure and cancelled confirmation',async()=>{
  for(const action of ['#toggle','#rotate']){
    const ui=sharingUI({fail:true});
    const pending=ui.q(action).onclick();ui.release();await pending;
    assert.equal(ui.q('#toggle').disabled,false);
    assert.equal(ui.q('#rotate').disabled,false);
    assert.equal(ui.context.event.guest,'old');
    assert.equal(ui.context.event.status,'published');
    assert.deepEqual(ui.messages.at(-1),['share-status','Connection lost','error']);
  }
  const ui=sharingUI({confirm:false});
  await ui.q('#rotate').onclick();
  assert.equal(ui.requests.length,0);
  assert.equal(ui.q('#rotate').disabled,false);
  assert.equal(ui.messages.length,0);
});
test('late sharing response does not render into a replacement screen',async()=>{
  const ui=sharingUI();
  const pending=ui.q('#toggle').onclick();
  ui.leave();
  const replacement=ui.q('#sharing');
  let refreshes=0;
  ui.context.refresh=async()=>refreshes++;
  ui.release();await pending;
  assert.equal(refreshes,0);
  assert.equal(replacement.innerHTML,undefined);
  assert.equal(ui.messages.length,0);
});
test('publish and pause do not overwrite title, description or detailed mode',async()=>{
  const start=source.indexOf("q('#toggle',box).onclick=");
  for(const published of [false,true]){
    const ui=setup('const box={};'+source.slice(start,source.indexOf("q('#copy',box)",start)),published);
    await ui.q('#toggle').onclick();
    assert.deepEqual(ui.patches,[{status:published?'paused':'published'}]);
  }
});
