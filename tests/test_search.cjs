// Real guest handler with delayed/mock API: protects the identity of the active query.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const accessCode=source.slice(source.indexOf('function guestAccessHint('),source.indexOf('function clear('));
const start=source.indexOf("q('#search').onsubmit=async");
const handler=source.slice(start,source.indexOf('\nfunction results(',start)).trim().slice(0,-1);
function setup(api){
  const nodes=new Map();
  const q=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,hidden:true,files:[{name:'selfie'}],setAttribute(){},removeAttribute(){},focus(){}});return nodes.get(id);};
  const shown=[];
  const context=vm.createContext({q,api,find:q('#find'),refreshReady:q('#refresh-ready'),searching:false,checkingReadiness:false,event:{status:'published',pending:0,ready:1},eventId:'event',ticket:null,feedbackHandler:null,resultTimer:null,clearTimeout(){},FormData:class{append(){}},stat:(id,msg)=>q('#'+id).textContent=msg,results:(result,photos)=>shown.push(photos)});
  vm.runInContext(accessCode+handler,context);
  return {q,shown,submit:()=>q('#search').onsubmit({preventDefault(){}})};
}
test('delayed query locks selfie/consent and rejects another submit until results arrive',async()=>{
  let release,calls=0;
  const ui=setup(async()=>{calls++;return await new Promise(r=>release=r);});
  const pending=ui.submit();
  assert.equal(ui.q('#selfie').disabled,true);
  assert.equal(ui.q('#search input[type="checkbox"]').disabled,true);
  assert.equal(ui.q('#find').disabled,true);
  await ui.submit();assert.equal(calls,1);
  release({ticket:'test',photos:[{id:'first'}]});await pending;
  assert.equal(ui.shown.length,1);
  assert.equal(ui.q('#selfie').disabled,false);
  assert.equal(ui.q('#search input[type="checkbox"]').disabled,false);
  assert.equal(ui.q('#find').disabled,false);
});
test('invalid selfie restores inputs; gallery unavailable exposes readiness and blocks search',async()=>{
  for(const status of [400,409,403,404]){
    const ui=setup(async()=>{throw Object.assign(Error('failure'),{status});});
    await ui.submit();assert.equal(ui.q('#selfie').disabled,false);
    assert.equal(ui.q('#find').disabled,status!==400);
    if(status!==400)assert.equal(ui.q('#refresh-ready').hidden,status!==409);
    if(status===403||status===404)assert.match(ui.q('#search-status').textContent,/фотограф/);
  }
});
test('API errors preserve HTTP status for client recovery',async()=>{
  const api=source.slice(source.indexOf('async function api('),source.indexOf('\nfunction clear('));
  const ctx=vm.createContext({adminKey:'test',guestKey:'test',FormData:class{},fetch:async()=>({ok:false,status:409,json:async()=>({error:'paused'})})});
  vm.runInContext(api,ctx);
  await assert.rejects(vm.runInContext("api('/test')",ctx),e=>e.status===409&&e.message==='paused');
});
