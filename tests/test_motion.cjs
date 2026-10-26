const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const motion=fs.readFileSync(path.join(__dirname,'../web/motion.js'),'utf8');
function setup(reduced=false,engine=true){
  const calls=[];let changed;const query={matches:reduced,addEventListener:(name,fn)=>changed=fn};
  const window={matchMedia:()=>query};
  if(engine)window.gsap={killTweensOf:element=>calls.push(['kill',element]),fromTo:(el,from,to)=>calls.push(['animate',el,from,to]),set:(el,props)=>calls.push(['set',el,props])};
  vm.runInNewContext(motion,{window,Set});return {window,calls,reduce:()=>{query.matches=true;changed();}};
}
test('motion is optional and disabled for reduced-motion users',()=>{
  for(const options of [[true,true],[false,false]]){const ui=setup(...options);ui.window.FaceFlowMotion.open({});ui.window.FaceFlowMotion.results({});assert.equal(ui.calls.length,0);}
});
test('short result reveal clears transforms and an active reveal stops when preference changes',()=>{
  const ui=setup(),element={};ui.window.FaceFlowMotion.results(element);const animation=ui.calls.find(c=>c[0]==='animate');
  assert.equal(animation[3].duration,.18);assert.equal(animation[3].clearProps,'opacity,transform');
  ui.reduce();assert.equal(ui.calls.at(-1)[0],'set');assert.equal(ui.calls.at(-1)[2].clearProps,'opacity,transform');
  const count=ui.calls.length;ui.window.FaceFlowMotion.open(element);assert.equal(ui.calls.length,count);
});
test('skip link focuses content without replacing the guest access fragment',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),start=source.indexOf('const skipLink='),end=source.indexOf("if(eventId)document.querySelector('.brand')",start);
  const link={},calls=[];const context={document:{querySelector:()=>link},root:{focus:()=>calls.push('focus')}};
  vm.runInNewContext(source.slice(start,end),context);link.onclick({preventDefault:()=>calls.push('prevent')});assert.deepEqual(calls,['prevent','focus']);
});
