// Guest readiness control flow with mocked responses and timers.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const code=source.slice(source.indexOf("const find=q('#find'),refreshReady="),source.indexOf("q('#selfie').onchange"));
function setup(event,api){
  const nodes=new Map();let scheduled=null;
  const q=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,hidden:false,textContent:'',after(){}});return nodes.get(id);};
  const context=vm.createContext({q,event,eventId:'event',api,document:{createElement(){const el={};nodes.set('#refresh-ready',el);return el;}},clear(){scheduled=null;},stat:(id,msg)=>q('#'+id).textContent=msg,setTimeout:fn=>{scheduled=fn;return 1;},poll:null});
  vm.runInContext(code,context);
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
