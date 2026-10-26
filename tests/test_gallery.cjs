const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/gallery-controls.js'),'utf8');

function setup(){
  const element=()=>({value:'',hidden:false,attrs:{},dataset:{},append(child){this.child=child;},setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k]??null;},addEventListener(){},before(){},after(){},focus(){}});
  const input=element(),selected=element(),layout=element(),status=element(),reset=element();
  selected.setAttribute('aria-pressed','false');layout.setAttribute('aria-pressed','false');
  const viewer=element();viewer.querySelector=()=>element();
  let divs=0,clearSelection;
  const document={querySelector:selector=>selector==='#viewer'?viewer:all,createElement:tag=>{
    const e=element();if(tag==='button')clearSelection=e;if(tag==='div'){divs++;e.querySelector=selector=>selector==='input'?input:selector==='[role=status]'?status:reset;e.querySelectorAll=()=>[selected,layout];}return e;
  }};
  const all=element(),checks=[{checked:true,disabled:false},{checked:false,disabled:false}],cards=checks.map((check,i)=>({hidden:false,querySelector:selector=>selector==='[data-select]'?check:{textContent:`Кадр 0${i+1}`}}));
  const gallery={children:cards,dataset:{},querySelectorAll:selector=>selector==='.photo'?cards:cards.filter(c=>selector==='[data-select]'||!c.hidden).map((c,i)=>c.querySelector('[data-select]')),before(){},after(){},addEventListener(){}};
  let live=true,updates=0;
  const window={matchMedia:()=>({matches:true}),addEventListener(){}};
  vm.runInNewContext(source,{window,document,queueMicrotask:fn=>fn()});
  const controller=window.FaceFlowGallery.mount({gallery,onChange:()=>updates++,canUse:()=>live});
  return{input,selected,layout,status,reset,all,cards,checks,gallery,controller,clearSelection,updates:()=>updates,expire:()=>live=false};
}
test('clear selection includes hidden frames and synchronizes download; expired results cannot change it',()=>{
  const ui=setup();ui.checks[1].checked=true;ui.input.value='02';ui.input.oninput();
  assert.equal(ui.cards[0].hidden,true);assert.equal(ui.clearSelection.disabled,false);
  ui.clearSelection.onclick();assert(ui.checks.every(check=>!check.checked));assert.equal(ui.updates(),1);assert.equal(ui.clearSelection.disabled,true);
  ui.checks[0].checked=true;ui.expire();ui.clearSelection.onclick();assert.equal(ui.checks[0].checked,true);assert.equal(ui.updates(),1);
});
test('filter hides a selected frame without clearing its choice; reset restores all frames',()=>{
  const ui=setup();ui.input.value='02';ui.input.oninput();
  assert.equal(ui.cards[0].hidden,true);assert.equal(ui.checks[0].checked,true);
  assert.match(ui.status.textContent,/скрыто фильтром 1/);
  ui.reset.onclick();assert(ui.cards.every(card=>!card.hidden));assert.equal(ui.checks[0].checked,true);
});
test('select-all changes only visible eligible frames; expiry cannot mutate selection',()=>{
  const ui=setup();ui.input.value='02';ui.input.oninput();ui.all.onclick();
  assert(ui.checks.every(check=>check.checked));assert.equal(ui.updates(),1);
  ui.expire();ui.all.onclick();assert(ui.checks.every(check=>check.checked));assert.equal(ui.updates(),1);
});
test('selected-only empty state can reset without fabricating a selection',()=>{
  const ui=setup();ui.checks[0].checked=false;ui.selected.onclick();
  assert(ui.cards.every(card=>card.hidden));assert.equal(ui.all.disabled,true);assert.match(ui.status.textContent,/Показано 0/);
  ui.reset.onclick();assert(ui.cards.every(card=>!card.hidden));assert(ui.checks.every(check=>!check.checked));
});
test('light-table layout remains functional without animation under reduced motion',()=>{
  const ui=setup();ui.layout.onclick();assert.equal(ui.gallery.dataset.layout,'table');assert.equal(ui.layout.getAttribute('aria-pressed'),'true');
  ui.layout.onclick();assert.equal(ui.gallery.dataset.layout,'album');
});
