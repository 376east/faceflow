// Result controls tested with the actual client function, mocked DOM and controlled time.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const code=source.slice(source.indexOf('function results('),source.indexOf("q('#close-viewer').onclick="));
const viewerCode=source.slice(source.indexOf('function setFaceMarker('),source.indexOf('function wireModal('));
function setup(apiResponse){
  let clock=100000,counter=0,closed=0,submitted=0,apiCalls=0,refreshed=0;
  const timers=new Map(),nodes=new Map();
  const node=()=>({disabled:false,hidden:false,checked:false,dataset:{},style:{removeProperty(){},setProperty(){}},handlers:{},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},before(){},addEventListener(name,fn){this.handlers[name]=fn;}});
  const q=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
  const card=node();card.dataset.photo='one';
  const check=q('[data-select]');check.dataset.select='one';
  const feedback=q('[data-feedback]');feedback.dataset.feedback='one';
  const open=q('.photo-open');
  const qa=selector=>selector==='.photo'||selector==='[data-photo]'?[card]:selector==='[data-select]:checked'?(check.checked?[check]:[]):selector==='[data-select]'?[check]:selector==='[data-feedback]'?[feedback]:selector==='.photo-open, [data-select], [data-feedback]'?[open,check,feedback]:[];
  class Clock extends Date{static now(){return clock;}}
  q('#search').requestSubmit=()=>submitted++;
  const context=vm.createContext({q,qa,Date:Clock,document:{createElement:node},photo:()=>'',wireModal(){},eventId:'event',modalPhoto:'one',ticket:'test',feedbackHandler:null,resultTimer:null,viewer:{open:true,close(){closed++;this.open=false;}},api:async()=>{apiCalls++;if(apiResponse)await apiResponse();},refreshViewer(){refreshed++;},stat:(id,msg)=>q('#'+id).textContent=msg,setTimeout:fn=>{const id=++counter;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id)});
  context.viewerItems=[card];context.viewerIndex=0;
  vm.runInContext(viewerCode+code,context);
  const refresh=context.refreshViewer;context.refreshViewer=()=>{refreshed++;refresh();};
  const show=()=>{nodes.set('#result-gallery',node());context.ticket='fresh';context.results({zip:'/zip?ticket=test',ticket:'test',expires_in:20},[{id:'one'}]);};
  return {q,show,timers,view:id=>{context.modalPhoto=id;context.viewer.open=true;},close:()=>context.viewer.open=false,refreshed:()=>refreshed,ticket:()=>context.ticket,closed:()=>closed,submitted:()=>submitted,apiCalls:()=>apiCalls,advance:ms=>clock+=ms};
}
test('expiry hides ZIP, disables old result actions and closes viewer; renewal submits existing form',()=>{
  const ui=setup();ui.show();assert.equal(ui.q('#zip').hidden,false);
  ui.advance(20001);[...ui.timers.values()][0]();
  assert.equal(ui.q('#zip').hidden,true);assert.equal(ui.q('#zip').href,undefined);
  assert.equal(ui.q('.photo-open').disabled,true);
  assert.equal(ui.q('[data-select]').disabled,true);
  assert.equal(ui.closed(),1);
  assert.match(ui.q('#result-expiry-status').textContent,/Срок ссылок истёк/);
  ui.q('#renew-results').onclick();assert.equal(ui.submitted(),1);
  assert.equal(ui.q('#search-details').open,true);
});
test('late timers after backgrounding cannot allow expired download or feedback',async()=>{
  const ui=setup();ui.show();ui.advance(30000);
  let prevented=0;ui.q('#zip').onclick({preventDefault(){prevented++;}});
  assert.equal(prevented,1);
  await ui.q('[data-feedback]').onclick();assert.equal(ui.apiCalls(),0);
});
test('new result replaces the previous expiry timer',()=>{
  const ui=setup();ui.show();const first=[...ui.timers.keys()][0];
  ui.advance(5000);ui.show();assert.equal(ui.timers.has(first),false);
  assert.equal(ui.timers.size,1);
  ui.advance(15001);[...ui.timers.values()][0]();assert.equal(ui.q('#zip').hidden,false);
});
test('old feedback completing after a new search cannot expire the new result',async()=>{
  let resolve;
  const ui=setup(()=>new Promise(r=>resolve=r));ui.show();
  const oldFeedback=ui.q('[data-feedback]').onclick();
  ui.advance(20001);ui.show();
  resolve();await oldFeedback;
  assert.equal(ui.ticket(),'fresh');
  assert.equal(ui.q('#zip').hidden,false);
  assert.doesNotMatch(ui.q('#result-expiry-status').textContent,/истёк/);
});
test('feedback failure after expiry keeps the expired result disabled',async()=>{
  let reject;
  const ui=setup(()=>new Promise((_,r)=>reject=r));ui.show();
  const pending=ui.q('[data-feedback]').onclick();
  ui.advance(20001);[...ui.timers.values()][0]();
  reject(new Error('Delayed failure'));await pending;
  assert.equal(ui.q('[data-feedback]').disabled,true);
  assert.equal(ui.q('#zip').hidden,true);
  assert.match(ui.q('#result-expiry-status').textContent,/истёк/);
  assert.notEqual(ui.q('#search-status').textContent,'Delayed failure');
});
test('feedback failure detects expiry even before its timer runs',async()=>{
  let reject;
  const ui=setup(()=>new Promise((_,r)=>reject=r));ui.show();
  const pending=ui.q('[data-feedback]').onclick();
  ui.advance(20001);
  reject(new Error('Delayed failure'));await pending;
  assert.equal(ui.q('[data-feedback]').disabled,true);
  assert.equal(ui.q('#zip').hidden,true);
  assert.match(ui.q('#result-expiry-status').textContent,/истёк/);
});
test('feedback failure before expiry allows retry and shows the error',async()=>{
  const ui=setup(async()=>{throw new Error('Try again');});ui.show();
  await ui.q('[data-feedback]').onclick();
  assert.equal(ui.q('[data-feedback]').disabled,false);
  assert.equal(ui.q('#zip').hidden,false);
  assert.equal(ui.q('#search-status').textContent,'Try again');
});
test('old feedback failure cannot change a replacement result',async()=>{
  let reject;
  const ui=setup(()=>new Promise((_,r)=>reject=r));ui.show();
  const pending=ui.q('[data-feedback]').onclick();
  ui.show();ui.q('[data-feedback]').disabled=true;
  ui.q('#search-status').textContent='New result';
  reject(new Error('Old failure'));await pending;
  assert.equal(ui.q('[data-feedback]').disabled,true);
  assert.equal(ui.q('#search-status').textContent,'New result');
  assert.equal(ui.q('#zip').hidden,false);
});

test('viewer feedback failure does not appear on another photo',async()=>{
  let reject;
  const ui=setup(()=>new Promise((_,r)=>reject=r));ui.show();
  const pending=ui.q('#not-me').onclick();
  ui.view('two');ui.q('#viewer-status').textContent='Second photo';
  reject(new Error('First photo failure'));await pending;
  assert.equal(ui.q('#viewer-status').textContent,'Second photo');
});

test('viewer feedback failure does not change a closed viewer',async()=>{
  let reject;
  const ui=setup(()=>new Promise((_,r)=>reject=r));ui.show();
  const pending=ui.q('#not-me').onclick();ui.close();
  ui.q('#viewer-status').textContent='Closed';
  reject(new Error('Delayed failure'));await pending;
  assert.equal(ui.q('#viewer-status').textContent,'Closed');
});

test('viewer feedback failure checks expiry without waiting for the timer',async()=>{
  let reject;
  const ui=setup(()=>new Promise((_,r)=>reject=r));ui.show();
  const pending=ui.q('#not-me').onclick();ui.advance(20001);
  reject(new Error('Expired failure'));await pending;
  assert.equal(ui.q('#zip').hidden,true);
  assert.equal(ui.closed(),1);
  assert.notEqual(ui.q('#viewer-status').textContent,'Expired failure');
});

test('viewer feedback failure on the active photo still shows a retryable error',async()=>{
  const ui=setup(async()=>{throw new Error('Try again');});ui.show();
  await ui.q('#not-me').onclick();
  assert.equal(ui.q('#viewer-status').textContent,'Try again');
  assert.equal(ui.q('#not-me').disabled,false);
  assert.equal(ui.q('#zip').hidden,false);
});

test('viewer feedback success updates its card without refreshing another photo',async()=>{
  let resolve;
  const ui=setup(()=>new Promise(r=>resolve=r));ui.show();
  const pending=ui.q('#not-me').onclick(),before=ui.refreshed();ui.view('two');
  resolve();await pending;
  assert.equal(ui.q('[data-feedback]').textContent,'Отмечено');
  assert.equal(ui.q('[data-select]').disabled,true);
  assert.equal(ui.refreshed(),before);
});

test('viewer feedback success refreshes the active original photo',async()=>{
  const ui=setup();ui.show();await ui.q('#not-me').onclick();
  assert.ok(ui.refreshed()>0);
  assert.equal(ui.q('[data-feedback]').textContent,'Отмечено');
});

test('card and viewer share one pending feedback request and recover after failure',async()=>{
  let reject;
  const ui=setup(()=>new Promise((_,r)=>reject=r));ui.show();
  const pending=ui.q('[data-feedback]').onclick();
  assert.equal(ui.q('[data-feedback]').disabled,true);
  assert.equal(ui.q('#not-me').disabled,true);
  assert.equal(ui.q('#not-me').textContent,'Отмечаем…');
  await ui.q('#not-me').onclick();
  await ui.q('[data-feedback]').onclick();
  assert.equal(ui.apiCalls(),1);
  reject(new Error('Try again'));await pending;
  assert.equal(ui.q('[data-feedback]').disabled,false);
  assert.equal(ui.q('#not-me').disabled,false);
  assert.equal(ui.q('#not-me').textContent,'Это не я');
});

test('viewer pending feedback blocks the card too; success leaves both marked',async()=>{
  let resolve;
  const ui=setup(()=>new Promise(r=>resolve=r));ui.show();
  const pending=ui.q('#not-me').onclick();
  assert.equal(ui.q('[data-feedback]').disabled,true);
  assert.equal(ui.q('#not-me').disabled,true);
  await ui.q('[data-feedback]').onclick();assert.equal(ui.apiCalls(),1);
  resolve();await pending;
  assert.equal(ui.q('[data-feedback]').textContent,'Отмечено');
  assert.equal(ui.q('#not-me').textContent,'Отмечено');
  assert.equal(ui.q('#not-me').disabled,true);
});


test('viewer highlight uses CSS properties and clears the preceding face on an unmarked photo',()=>{
  const context=vm.createContext({});vm.runInContext(source.slice(source.indexOf('function setFaceMarker('),source.indexOf('function refreshViewer(')),context);
  const values={};const marker={style:{setProperty:(k,v)=>values[k]=v,removeProperty:k=>delete values[k]}};
  context.setFaceMarker(marker,'left:10%;top:20%;width:30%;height:40%;');
  assert.equal(marker.hidden,false);assert.deepEqual(values,{left:'10%',top:'20%',width:'30%',height:'40%'});
  context.setFaceMarker(marker,'');assert.equal(marker.hidden,true);assert.deepEqual(values,{});
});
