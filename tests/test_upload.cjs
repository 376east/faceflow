// Client control-flow tests with mocked DOM/API; real upload integration is in test_flow.py.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const upload=source.slice(source.indexOf("const input=q('#photos')"),source.indexOf("qa('[data-filter]')"));
function setup(api){
  const nodes=new Map();
  const q=id=>{if(!nodes.has(id))nodes.set(id,{files:[],disabled:false,hidden:false,textContent:'',innerHTML:'',handlers:{},classList:{add(){},remove(){}},setAttribute(){},removeAttribute(){},addEventListener(name,fn){this.handlers[name]=fn;}});return nodes.get(id);};
  let refreshes=0;
  class DataTransfer{constructor(){this.files=[];this.items={add:f=>this.files.push(f)};}}
  class FormData{constructor(){this.fields={};}append(k,v){this.fields[k]=v;}}
  const context=vm.createContext({q,DataTransfer,FormData,id:'event',api,esc:s=>s.replaceAll('<','&lt;'),stat:(id,msg)=>q('#'+id).textContent=msg,refresh:async()=>{refreshes++;}});
  vm.runInContext(upload,context);
  return {q,refreshes:()=>refreshes,choose(files){q('#photos').files=files;q('#photos').onchange();}};
}
test('partial failure preserves only failed files; retry does not resend successful or duplicate files',async()=>{
  const seen=[];let fail=true;
  const ui=setup(async(path,opt)=>{const f=opt.body.fields.photo;seen.push(f.name);if(f.name==='bad'&&fail)throw Error('offline');return {duplicate:f.name==='duplicate'};});
  const files=['new','duplicate','bad'].map(name=>({name}));ui.choose(files);
  await ui.q('#upload').onclick();
  assert.deepEqual(ui.q('#photos').files,[files[2]]);
  assert.equal(ui.q('#upload').disabled,false);
  assert.match(ui.q('#upload-status').textContent,/Добавлено: 1\. Уже в галерее: 1\. Не загружено: 1/);
  fail=false;await ui.q('#upload').onclick();
  assert.deepEqual(seen,['new','duplicate','bad','bad']);
  assert.equal(ui.q('#photos').files.length,0);
  assert.equal(ui.q('#upload').disabled,true);
  assert.equal(ui.q('#photos').disabled,false);
  assert.equal(ui.q('#upload-errors').hidden,true);
  assert.equal(ui.refreshes(),2);
});
test('active upload ignores drops and duplicate clicks; a new selection clears old errors',async()=>{
  let release,calls=0;
  const ui=setup(async()=>{calls++;await new Promise(resolve=>release=resolve);throw Error('<broken>');});
  const original={name:'original'};ui.choose([original]);
  const pending=ui.q('#upload').onclick();
  assert.equal(ui.q('#photos').disabled,true);
  assert.equal(ui.q('#back').disabled,true);
  assert.equal(ui.q('#delete-event').disabled,true);
  ui.q('#drop').handlers.drop({preventDefault(){},dataTransfer:{files:[{name:'replacement'}]}});
  await ui.q('#upload').onclick();assert.equal(calls,1);
  release();await pending;
  assert.equal(ui.q('#back').disabled,false);
  assert.equal(ui.q('#delete-event').disabled,false);
  assert.deepEqual(ui.q('#photos').files,[original]);
  assert.match(ui.q('#upload-errors').innerHTML,/&lt;broken>/);
  ui.choose([{name:'replacement'}]);
  assert.equal(ui.q('#upload-errors').hidden,true);
  assert.equal(ui.q('#progress').hidden,true);
  assert.equal(ui.q('#upload-status').textContent,'');
  assert.equal(ui.q('#upload').textContent,'Загрузить');
});
