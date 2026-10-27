const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
function setup(api){
  const nodes=new Map(),timers=[];
  const element=()=>({disabled:false,textContent:'',innerHTML:'',after(){},addEventListener(type,fn){this.onclick=fn;}});
  const q=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
  const context=vm.createContext({q,document:{createElement:element},api,input:{files:[]},id:'event',event:{},last:'',poll:null,clear(){},setTimeout:fn=>timers.push(fn),share:e=>q('#toggle').disabled=!!e.pending||!e.ready,render(){},stat:(id,msg)=>q('#'+id).textContent=msg});
  const start=source.indexOf('const galleryNode=');
  vm.runInContext(source.slice(source.indexOf('function galleryProgress('),source.indexOf('function badge('))+source.slice(start,source.indexOf('}await refresh();}',start)+1),context);
  return {q,timers,context,refresh:()=>vm.runInContext('refresh()',context),leave:()=>nodes.delete('#gallery')};
}
test('admin sees errors alongside pending work and can recover from a failed poll',async()=>{
  let fail=false;
  const ui=setup(async()=>{if(fail)throw Error('offline');return {total:4,ready:1,pending:2,errors:1,photos:[]};});
  await ui.refresh();
  assert.match(ui.q('#gallery-status').innerHTML,/Готово: 1 из 4.*Обрабатывается: 2.*Ошибок: 1/);
  assert.equal(ui.q('#toggle').disabled,true);
  fail=true;await ui.refresh();
  assert.match(ui.q('#gallery-status').textContent,/устаревшими/);
  assert.match(ui.q('#upload-status').textContent,/Обновить состояние/);
  fail=false;await ui.refresh();assert.equal(ui.context.event.ready,1);
});
test('admin ignores overlapping and late status requests after navigation',async()=>{
  let release,calls=0;
  const ui=setup(async()=>{calls++;await new Promise(resolve=>release=resolve);return {title:'Old screen',photos:[]};});
  const pending=ui.refresh();await ui.refresh();assert.equal(calls,1);
  ui.leave();release();await pending;
  assert.equal(ui.q('#event-title').textContent,'');assert.equal(ui.q('#stats').innerHTML,'');
});
test('closing viewer focuses the visible frame, falls back for a hidden frame, and leaves zoom alone',()=>{
  let handler,zoom=false,focused;
  const button={disabled:false,focus(){focused='photo';}},card={dataset:{photo:'p'},hidden:false};
  const results={focus(){focused='results';}};
  const context={viewer:{addEventListener:(type,fn)=>handler=fn},window:{FaceFlowGallery:{isZoomOpen:()=>zoom}},root:{},modalPhoto:'p',qa:()=>[card],q:(s,n)=>n===card?button:results};
  const start=source.indexOf("viewer.addEventListener('close'");
  vm.runInNewContext(source.slice(start,source.indexOf("q('#viewer-prev').onclick",start)),context);
  handler();assert.equal(focused,'photo');card.hidden=true;handler();assert.equal(focused,'results');
  focused='zoom';zoom=true;handler();assert.equal(focused,'zoom');
});
