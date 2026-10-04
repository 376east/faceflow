// Guest readiness control flow with mocked responses and timers.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const accessCode=source.slice(source.indexOf('function guestAccessHint('),source.indexOf('function clear('));
const code=source.slice(source.indexOf("const find=q('#find'),refreshReady="),source.indexOf("q('#selfie').onchange"));
function setup(event,api){
  const nodes=new Map();let scheduled=null;
  const q=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,hidden:false,textContent:'',after(){}});return nodes.get(id);};
  const context=vm.createContext({q,event,eventId:'event',api,document:{createElement(){const el={};nodes.set('#refresh-ready',el);return el;}},clear(){scheduled=null;},stat:(id,msg)=>q('#'+id).textContent=msg,setTimeout:fn=>{scheduled=fn;return 1;},poll:null});
  vm.runInContext(accessCode+code,context);
  return {q,pending:()=>scheduled};
}
test('paused gallery can become ready without reloading the form',async()=>{
  const ui=setup({status:'paused',title:'Old'},async()=>({status:'published',ready:2,pending:0,title:'New'}));
  ui.q('#selfie').selected='preserved';ui.q('#consent').checked=true;
  assert.equal(ui.q('#find').disabled,true);
  await ui.q('#refresh-ready').onclick();
  assert.equal(ui.q('#find').disabled,false);
  assert.equal(ui.q('#refresh-ready').hidden,true);
  assert.equal(ui.q('.guest-head h1').textContent,'New');
  assert.equal(ui.q('#selfie').selected,'preserved');
  assert.equal(ui.q('#consent').checked,true);
});
test('failed pending poll gives a visible retry and stops timers; manual retry recovers',async()=>{
  let fail=true;
  const ui=setup({status:'published',ready:0,pending:1,total:1},async()=>{if(fail)throw Error('offline');return {status:'published',ready:1,pending:0};});
  await ui.pending()();
  assert.match(ui.q('#search-status').textContent,/offline.*Проверить готовность/);
  assert.equal(ui.q('#find').disabled,true);
  assert.equal(ui.q('#refresh-ready').disabled,false);
  assert.equal(ui.pending(),null);
  fail=false;await ui.q('#refresh-ready').onclick();
  assert.equal(ui.q('#find').disabled,false);
});
test('manual readiness checks cannot overlap',async()=>{
  let release,calls=0;
  const ui=setup({status:'draft'},async()=>{calls++;await new Promise(r=>release=r);return {status:'published',pending:0,ready:1};});
  const first=ui.q('#refresh-ready').onclick();
  await ui.q('#refresh-ready').onclick();assert.equal(calls,1);
  release();await first;assert.equal(ui.q('#find').disabled,false);
});
test('revoked or missing gallery stops readiness retries and gives the next step',async()=>{
  for(const status of [403,404]){
    const ui=setup({status:'published',pending:1},async()=>{throw Object.assign(Error('failure'),{status});});
    await ui.pending()();
    assert.equal(ui.q('#find').disabled,true);
    assert.equal(ui.q('#refresh-ready').hidden,true);
    assert.equal(ui.pending(),null);
    assert.match(ui.q('#search-status').textContent,/фотограф/);
  }
});

function openingUI(api){
  const nodes=new Map();
  const q=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false});return nodes.get(id);};
  const context=vm.createContext({q,api,root:{innerHTML:''},esc:String,clearTimeout(){},poll:null,eventId:'event'});
  const failCode=source.slice(source.indexOf('function guestAccessHint('),source.indexOf('function badge('));
  const guestStart=source.indexOf('async function guest(){');
  const opening=source.slice(guestStart,source.indexOf('root.innerHTML=',guestStart));
  vm.runInContext(failCode+opening+"root.innerHTML='opened';}",context);
  return {q,context,open:()=>context.guest()};
}
test('initial temporary failure can retry once without overlapping requests',async()=>{
  let calls=0,release;
  const ui=openingUI(async()=>{if(++calls===1)throw Error('offline');return await new Promise(resolve=>release=resolve);});
  await ui.open();
  assert.match(ui.context.root.innerHTML,/retry-page/);
  const retry=ui.q('#retry-page').onclick();
  assert.equal(ui.q('#retry-page').disabled,true);
  await ui.q('#retry-page').onclick();
  assert.equal(calls,2);
  release({status:'published'});await retry;
  assert.equal(ui.context.root.innerHTML,'opened');
});
test('initial access failure explains missing or revoked link without useless retry',async()=>{
  for(const status of [403,404]){
    const ui=openingUI(async()=>{throw Object.assign(Error('failure'),{status});});
    await ui.open();
    assert.doesNotMatch(ui.context.root.innerHTML,/retry-page/);
    assert.match(ui.context.root.innerHTML,/фотограф/);
  }
  let calls=0;
  const ui=openingUI(async()=>{calls++;throw Error('offline');});
  await ui.open();await ui.q('#retry-page').onclick();
  assert.match(ui.context.root.innerHTML,/retry-page/);
  assert.equal(ui.q('#retry-page').disabled,false);
  assert.equal(calls,2);
});
test('opening a different guest key in the same tab reloads credentials only when key changes',()=>{
  const code=source.slice(source.indexOf("if(eventId)window.addEventListener('hashchange'"),source.indexOf('\nlet poll,'));
  let handler,reloads=0;
  const location={hash:'#g=old',reload:()=>reloads++};
  const ctx=vm.createContext({eventId:'event',guestKey:'old',location,URLSearchParams,window:{addEventListener(type,fn){assert.equal(type,'hashchange');handler=fn;}}});
  vm.runInContext(code,ctx);
  location.hash='#g=old&other=value';handler();assert.equal(reloads,0);
  location.hash='#g=new';handler();assert.equal(reloads,1);
  location.hash='';handler();assert.equal(reloads,2);
  handler=null;ctx.eventId=null;vm.runInContext(code,ctx);assert.equal(handler,null);
});
