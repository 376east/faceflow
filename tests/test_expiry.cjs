// Result controls tested with the actual client function, mocked DOM and controlled time.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const code=source.slice(source.indexOf('function results('),source.indexOf("q('#close-viewer').onclick="));
function setup(apiResponse){
  let clock=100000,counter=0,closed=0,submitted=0,apiCalls=0;
  const timers=new Map(),nodes=new Map();
  const node=()=>({disabled:false,hidden:false,checked:false,dataset:{},handlers:{},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},before(){},addEventListener(name,fn){this.handlers[name]=fn;}});
  const q=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
  const card=node();card.dataset.photo='one';
  const check=q('[data-select]');check.dataset.select='one';
  const feedback=q('[data-feedback]');feedback.dataset.feedback='one';
  const open=q('.photo-open');
  const qa=selector=>selector==='.photo'||selector==='[data-photo]'?[card]:selector==='[data-select]:checked'?(check.checked?[check]:[]):selector==='[data-select]'?[check]:selector==='[data-feedback]'?[feedback]:selector==='.photo-open, [data-select], [data-feedback]'?[open,check,feedback]:[];
  class Clock extends Date{static now(){return clock;}}
  q('#search').requestSubmit=()=>submitted++;
  const context=vm.createContext({q,qa,Date:Clock,document:{createElement:node},photo:()=>'',wireModal(){},eventId:'event',modalPhoto:'one',ticket:'test',feedbackHandler:null,resultTimer:null,viewer:{open:true,close(){closed++;}},api:async()=>{apiCalls++;if(apiResponse)await apiResponse();},refreshViewer(){},stat:(id,msg)=>q('#'+id).textContent=msg,setTimeout:fn=>{const id=++counter;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(code,context);
  const show=()=>{nodes.set('#result-gallery',node());context.ticket='fresh';context.results({zip:'/zip?ticket=test',ticket:'test',expires_in:20},[{id:'one'}]);};
  return {q,show,timers,ticket:()=>context.ticket,closed:()=>closed,submitted:()=>submitted,apiCalls:()=>apiCalls,advance:ms=>clock+=ms};
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
