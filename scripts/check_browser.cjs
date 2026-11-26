'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const net=require('node:net');
const {spawn,execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const ROOT=path.resolve(__dirname,'..');

async function waitFor(check,timeout=30000){
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){try{const value=await check();if(value)return value;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
  throw Error('Timed out waiting for the local browser check');
}
async function freePort(){const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;await new Promise(resolve=>server.close(resolve));return port;}
async function imagesReady(page,selector){
  await page.locator(selector).first().waitFor();
  await page.waitForFunction(selector=>[...document.querySelectorAll(selector)].every(i=>i.complete&&i.naturalWidth>0),selector);
  await page.evaluate(()=>document.fonts.ready);
}
async function actionVisible(page,selector){
  const node=page.locator(selector);await node.scrollIntoViewIfNeeded();
  const state=await node.evaluate(el=>{const r=el.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);return {width:r.width,height:r.height,inViewport:x>=0&&y>=0&&x<innerWidth&&y<innerHeight,hit:hit===el||el.contains(hit)};});
  assert(state.width>0&&state.height>0&&state.inViewport&&state.hit,`Action obscured: ${selector}: ${JSON.stringify(state)}`);
  return state;
}
async function layout(page){
  const state=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,dpr:devicePixelRatio,visualScale:visualViewport.scale,cssZoom:getComputedStyle(document.documentElement).zoom,reduced:matchMedia('(prefers-reduced-motion: reduce)').matches}));
  assert(state.scrollWidth<=state.width+1,`Horizontal overflow: ${JSON.stringify(state)}`);return state;
}
async function main(){
  const outputFlag=process.argv.indexOf('--output');
  const output=path.resolve(outputFlag<0?path.join(ROOT,'work/browser-check'):process.argv[outputFlag+1]);
  await fs.mkdir(output,{recursive:true});
  const workRoot=path.join(ROOT,'work');await fs.mkdir(workRoot,{recursive:true});
  const temporary=await fs.mkdtemp(path.join(workRoot,'browser-run-'));
  const data=path.join(temporary,'data'),profile=path.join(temporary,'profile');
  const executable=process.env.FACEFLOW_BROWSER_EXECUTABLE||path.join(workRoot,'test-browser/153.0.8010.36/chrome-win64/chrome.exe');
  await fs.access(executable).catch(()=>{throw Error('Run npm run browser:install before the browser check');});
  const python=process.env.FACEFLOW_PYTHON||(await fs.access(path.join(ROOT,'.venv/Scripts/python.exe')).then(()=>path.join(ROOT,'.venv/Scripts/python.exe')).catch(()=> 'python'));
  const port=await freePort(),base=`http://127.0.0.1:${port}`;
  const log=await fs.open(path.join(temporary,'server.log'),'w');
  const server=spawn(python,['app.py','--port',String(port)],{cwd:ROOT,env:{...process.env,FACEFLOW_DATA:data},stdio:['ignore',log.fd,log.fd],windowsHide:true});
  let context;const secrets=[];
  const report={gitHead:execFileSync('git',['rev-parse','HEAD'],{cwd:ROOT,encoding:'utf8'}).trim(),browser:null,synthetic:true,computerUse:false,modes:[],screenshots:[],errors:[]};
  try{
    const config=await waitFor(async()=>JSON.parse(await fs.readFile(path.join(data,'config.json'),'utf8')));secrets.push(config.admin);
    await waitFor(async()=>{const r=await fetch(base+'/api/events',{headers:{'X-Admin-Key':config.admin}});return r.ok;});
    const extension=path.join(ROOT,'tests/browser/zoom-extension');
    context=await chromium.launchPersistentContext(profile,{channel:'chromium',executablePath:executable,headless:true,viewport:{width:1280,height:800},args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
    report.browser=context.browser().version();assert.equal(report.browser,'153.0.8010.36','Pinned test browser version');
    report.sources={};for(const file of ['web/app.js','web/style.css','web/motion.js','web/gallery-controls.js','scripts/check_browser.cjs','tests/browser/zoom-extension/manifest.json','tests/browser/zoom-extension/worker.js'])report.sources[file]=crypto.createHash('sha256').update(await fs.readFile(path.join(ROOT,file))).digest('hex');
    const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker');
    const admin=await context.newPage();
    admin.on('pageerror',e=>report.errors.push(e.message));
    await admin.goto(base+'/#admin='+config.admin);
    await admin.getByRole('textbox',{name:'Название',exact:true}).fill('Синтетическая проверка интерфейса');
    await admin.getByRole('checkbox').check();await admin.getByRole('button',{name:'Создать съёмку',exact:true}).click();
    await admin.locator('#photos').setInputFiles([path.join(ROOT,'tests/fixtures/person-a.png'),path.join(ROOT,'tests/fixtures/person-b.png')]);
    await admin.getByRole('button',{name:'Загрузить',exact:true}).click();
    await admin.getByRole('button',{name:'Опубликовать',exact:true}).waitFor();
    await waitFor(()=>admin.getByRole('button',{name:'Опубликовать',exact:true}).isEnabled());
    await imagesReady(admin,'#gallery img');
    report.admin=await layout(admin);
    report.admin.images=await admin.locator('#gallery img').evaluateAll(imgs=>imgs.map(i=>{const r=i.getBoundingClientRect();return {complete:i.complete,naturalWidth:i.naturalWidth,width:r.width,height:r.height};}));
    assert(report.admin.images.every(i=>Math.abs(i.width/i.height-4/3)<.02),'Admin thumbnail proportions');
    const shot=async(page,name)=>{
      const target=path.join(output,name+'.png'),session=await page.context().newCDPSession(page);
      try{
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const metrics=await session.send('Page.getLayoutMetrics');
        (report.captureMetrics??=[]).push({name,visual:metrics.visualViewport,cssVisual:metrics.cssVisualViewport});
        // Native tab zoom changes CSS coordinates; avoid Playwright's clipped capture rectangle.
        const {data}=await session.send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false});
        await fs.writeFile(target,Buffer.from(data,'base64'));
      }finally{await session.detach();}
      report.screenshots.push(target);
    };
    await shot(admin,'browser-admin');
    await admin.getByRole('button',{name:'Опубликовать',exact:true}).click();
    const guestUrl=await admin.getByRole('link',{name:'Открыть',exact:true}).getAttribute('href');secrets.push(new URLSearchParams(new URL(guestUrl).hash.slice(1)).get('g'));
    const phone=admin.locator('[data-phone-panel]');
    await phone.getByText('Доступ с телефона',{exact:true}).click();
    assert.match(await phone.innerText(),/HTTP без шифрования/);
    await waitFor(async()=>Boolean(await phone.locator('[data-phone-content]').innerText()));
    assert.equal(await phone.locator('[data-phone-stop]').count(),0,'LAN must be closed by default');
    const addresses=phone.locator('[data-phone-address] option:not([disabled])');
    if(await addresses.count()){
      await phone.locator('[data-phone-address]').selectOption(await addresses.first().innerText());
      await phone.getByRole('button',{name:'Открыть доступ на 30 минут'}).click();
      const link=phone.locator('.share-link');
      await link.waitFor();
      const remoteUrl=await link.innerText();
      const remote=new URL(remoteUrl);
      secrets.push(new URLSearchParams(remote.hash.slice(1)).get('g'));
      assert.notEqual(remote.hostname,'127.0.0.1');
      assert.notEqual(remote.hash,new URL(guestUrl).hash);
      await phone.getByRole('button',{name:'Закрыть доступ'}).click();
      await phone.getByRole('button',{name:'Открыть доступ на 30 минут'}).waitFor();
      report.phoneShare='Published shoot starts and closes through the host browser UI';
    }else{
      report.phoneShare='No eligible private Windows IPv4; opt-in panel rendered';
    }
    for(const mode of [{name:'desktop',width:1280,height:800,reduce:false,zoom:1},{name:'zoom-200',width:1280,height:800,reduce:false,zoom:2},{name:'reduced',width:1280,height:800,reduce:true,zoom:1},{name:'mobile-390',width:390,height:844,reduce:true,zoom:1},{name:'mobile-320',width:320,height:700,reduce:true,zoom:1}]){
      const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
      await page.setViewportSize({width:mode.width,height:mode.height});await page.emulateMedia({reducedMotion:mode.reduce?'reduce':'no-preference'});
      await page.goto(guestUrl);await page.locator('#find').waitFor();
      const before=await layout(page);
      const browserZoom=await worker.evaluate(async({url,factor})=>{const tab=(await chrome.tabs.query({})).find(tab=>tab.url===url);if(!tab)throw Error('Test tab missing');await chrome.tabs.setZoomSettings(tab.id,{mode:'automatic',scope:'per-tab'});await chrome.tabs.setZoom(tab.id,factor);return chrome.tabs.getZoom(tab.id);},{url:guestUrl,factor:mode.zoom});
      await page.waitForFunction(({zoom,width})=>Math.abs(innerWidth-width/zoom)<3,{zoom:mode.zoom,width:mode.width});
      const state=await layout(page);assert.equal(browserZoom,mode.zoom);assert.equal(state.reduced,mode.reduce);
      assert(['1','normal'].includes(state.cssZoom),'CSS zoom must remain untouched');
      if(mode.zoom===2){assert(Math.abs(state.dpr/before.dpr-2)<.05);assert.equal(state.visualScale,1);}
      // Observe real style changes only. No product function, media result or CSS is replaced.
      await page.evaluate(()=>{window.__qaMotion=[];const observer=new MutationObserver(records=>{for(const record of records){const el=record.target;if(el.id==='result-gallery'||el.id==='viewer'){const s=getComputedStyle(el);window.__qaMotion.push({opacity:s.opacity,transform:s.transform});}}});observer.observe(document.body,{subtree:true,attributes:true,attributeFilter:['style']});});
      await page.locator('#selfie').setInputFiles(path.join(ROOT,'tests/fixtures/person-a.png'));
      await page.getByRole('checkbox').check();await actionVisible(page,'#find');await page.getByRole('button',{name:'Найти мои фото',exact:true}).click();
      await imagesReady(page,'#result-gallery img');
      assert.equal(await page.locator('#result-gallery .photo').count(),1);
      await page.locator('[data-select]').focus();await page.keyboard.press('Space');
      assert.equal(await page.locator('[data-select]:checked').count(),1);
      await page.getByRole('button',{name:'Световой стол',exact:true}).click();
      assert.equal(await page.locator('#result-gallery').getAttribute('data-layout'),'table');
      await page.locator('.photo-open').focus();await page.keyboard.press('Enter');
      await page.locator('#viewer').waitFor({state:'visible'});await imagesReady(page,'#large-photo');
      for(const direction of ['Tab','Shift+Tab'])for(let i=0;i<7;i++){await page.keyboard.press(direction);const focus=await page.locator('#viewer').evaluate(el=>({inside:el.contains(document.activeElement),tag:document.activeElement.tagName,id:document.activeElement.id}));(report.keyboardTrace??=[]).push({mode:mode.name,direction,tab:i,...focus});assert(focus.inside,'Dialog focus escaped: '+JSON.stringify(focus));}
      await actionVisible(page,'#close-viewer');await actionVisible(page,'#large-download');
      const motion=await page.evaluate(()=>({samples:window.__qaMotion,final:[document.querySelector('#viewer'),document.querySelector('#result-gallery')].map(el=>({opacity:getComputedStyle(el).opacity,transform:getComputedStyle(el).transform})),active:gsap.getTweensOf([document.querySelector('#viewer'),document.querySelector('#result-gallery')]).filter(t=>t.isActive()).length}));
      if(mode.reduce){assert.equal(motion.active,0);assert(motion.final.every(s=>s.opacity==='1'&&s.transform==='none'),'Reduced motion final styles');assert(motion.samples.every(s=>s.opacity==='1'&&s.transform==='none'),'Reduced motion must not animate result/viewer');}
      else assert(motion.samples.some(s=>Number(s.opacity)<1||s.transform!=='none'),'Normal state transition must be observed');
      const viewerGeometry=await page.locator('#viewer').evaluate(el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height,scrollTop:el.scrollTop,innerHeight,scrollY};});assert(viewerGeometry.top>=-1&&viewerGeometry.bottom<=viewerGeometry.innerHeight+1,'Viewer outside viewport: '+JSON.stringify(viewerGeometry));await shot(page,mode.name+'-viewer');await page.keyboard.press('Escape');
      await waitFor(()=>page.locator('.photo-open').evaluate(el=>document.activeElement===el));
      const focus=await page.locator('.photo-open').evaluate(el=>({keyboard:el.matches(':focus-visible'),visible:getComputedStyle(el).outlineStyle!=='none',width:getComputedStyle(el).outlineWidth}));assert(focus.keyboard&&focus.visible&&parseFloat(focus.width)>0,'Keyboard focus must be visible');
      await layout(page);await actionVisible(page,'#zip');
      const downloadPromise=page.waitForEvent('download');await page.locator('#zip').click();const download=await downloadPromise;assert((await fs.stat(await download.path())).size>0);
      await shot(page,mode.name+'-results');
      report.modes.push({name:mode.name,browserZoom,state,motion,viewerGeometry,focus,downloaded:true,overlapChecks:'find, close, single download, ZIP centers hit their own controls'});
      await page.close();
    }
    assert.equal(report.errors.length,0);report.status='PASS';
  }catch(error){report.status='FAIL';report.failure=error.stack;throw error;}
  finally{
    if(context)await context.close();
    if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}
    await log.close();
    let serialized=JSON.stringify(report,null,2);for(const secret of secrets.filter(Boolean))serialized=serialized.replaceAll(secret,'[redacted]');await fs.writeFile(path.join(output,'browser-report.json'),serialized);
    // Only remove the uniquely created child of this repository's work directory.
    const resolved=await fs.realpath(temporary),allowed=await fs.realpath(workRoot);
    assert(resolved.startsWith(allowed+path.sep)&&path.basename(resolved).startsWith('browser-run-'));
    if(report.status==='PASS')await fs.rm(resolved,{recursive:true,force:true});
  }
  console.log(`Browser checks PASS: ${report.modes.length} modes; report: ${path.join(output,'browser-report.json')}`);
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
