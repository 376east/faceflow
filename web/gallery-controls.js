/* The gallery changes presentation only; signed media URLs and selection stay in app.js. */
'use strict';
(()=>{
  let zoom,guard=()=>true,returnToViewer=true;
  const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function closeZoom(){returnToViewer=false;zoom?.destroy();zoom=null;}
  function mount({gallery,onChange,canUse}){
    closeZoom();guard=canUse;
    const bar=document.createElement('div');bar.className='gallery-controls';
    bar.innerHTML='<label>Номер кадра<input type="search" inputmode="numeric" placeholder="Например, 02" aria-label="Найти кадр по номеру"></label><button type="button" class="secondary" aria-pressed="false">Только выбранные</button><button type="button" class="secondary" aria-pressed="false">Световой стол</button><span class="gallery-visible" role="status"></span>';
    const empty=document.createElement('div');empty.className='gallery-empty';empty.hidden=true;
    empty.innerHTML='<h3>Таких кадров нет</h3><p>Измените номер или покажите всю подборку. Выбранные кадры сохранены.</p><button type="button" class="secondary">Показать все кадры</button>';
    gallery.before(bar);gallery.after(empty);
    const input=bar.querySelector('input'),[selected,layout]=bar.querySelectorAll('button'),status=bar.querySelector('[role=status]');
    const clearSelection=document.createElement('button');
    clearSelection.type='button';clearSelection.className='text-button';clearSelection.dataset.clearSelection='';
    clearSelection.textContent='Снять весь выбор';bar.append(clearSelection);
    function refresh(){
      const cards=[...gallery.querySelectorAll('.photo')],query=input.value.trim().toLocaleLowerCase('ru-RU');let visible=0,chosen=0,hiddenChosen=0;
      for(const card of cards){const check=card.querySelector('[data-select]'),checked=!!check?.checked&&!check.disabled;const match=(!query||card.querySelector('.photo-name').textContent.toLocaleLowerCase('ru-RU').includes(query))&&(selected.getAttribute('aria-pressed')!=='true'||checked);card.hidden=!match;if(match)visible++;if(checked){chosen++;if(!match)hiddenChosen++;}}
      const eligible=cards.filter(card=>!card.hidden).map(card=>card.querySelector('[data-select]')).filter(check=>check&&!check.disabled);
      const selectAll=document.querySelector('#select-all');selectAll.disabled=!eligible.length;selectAll.textContent=eligible.length&&eligible.every(check=>check.checked)?'Снять видимые':'Выбрать видимые';
      clearSelection.disabled=!chosen;
      clearSelection.setAttribute('aria-label',`Снять весь выбор${chosen?` (${chosen})`:''}`);
      status.textContent=`Показано ${visible} из ${cards.length}${chosen?` · выбрано ${chosen}${hiddenChosen?`, скрыто фильтром ${hiddenChosen}`:''}`:''}`;empty.hidden=visible>0;
    }
    input.oninput=refresh;
    clearSelection.onclick=()=>{if(!canUse())return;gallery.querySelectorAll('[data-select]').forEach(check=>{if(!check.disabled)check.checked=false;});onChange();refresh();};
    selected.onclick=()=>{selected.setAttribute('aria-pressed',String(selected.getAttribute('aria-pressed')!=='true'));refresh();};
    layout.onclick=()=>{const state=!reduced()&&window.Flip?.getState([...gallery.children]);const table=gallery.dataset.layout!=='table';gallery.dataset.layout=table?'table':'album';layout.setAttribute('aria-pressed',String(table));if(state)window.Flip.from(state,{duration:.24,ease:'power2.out',absolute:false});};
    empty.querySelector('button').onclick=()=>{input.value='';selected.setAttribute('aria-pressed','false');refresh();input.focus();};
    gallery.addEventListener('change',refresh);
    gallery.addEventListener('click',()=>queueMicrotask(refresh));
    const all=document.querySelector('#select-all');
    all.onclick=()=>{if(!canUse())return;const checks=[...gallery.querySelectorAll('.photo:not([hidden]) [data-select]')].filter(check=>!check.disabled),allChecked=checks.length>0&&checks.every(check=>check.checked);checks.forEach(check=>check.checked=!allChecked);onChange();refresh();};
    refresh();return {refresh};
  }
  const viewer=document.querySelector('#viewer'),button=document.createElement('button');
  button.type='button';button.className='secondary viewer-zoom';button.textContent='Увеличить оригинал';
  button.onclick=()=>{
    const image=document.querySelector('#large-photo');if(!guard()||!window.PhotoSwipe||!image.complete||!image.naturalWidth)return;
    const instance=new window.PhotoSwipe({dataSource:[{src:image.src,width:image.naturalWidth,height:image.naturalHeight,alt:image.alt}],showHideAnimationType:reduced()?'none':'fade',showAnimationDuration:180,hideAnimationDuration:180,zoomAnimationDuration:reduced()?0:180});
    zoom=instance;returnToViewer=true;viewer.close();
    instance.on('uiRegister',()=>instance.ui.registerElement({name:'caption',order:9,appendTo:'root',isButton:false,onInit:element=>{element.textContent=`${image.alt} · Оригинал без рамки`;}}));
    instance.on('destroy',()=>{if(zoom===instance)zoom=null;if(returnToViewer&&guard()&&viewer.isConnected&&!viewer.open){viewer.showModal();button.focus();}});
    try{instance.init();}catch{zoom=null;viewer.showModal();button.focus();}
  };
  const image=document.querySelector('#large-photo');
  const imageChanged=()=>{button.disabled=!image.complete||!image.naturalWidth;};
  image.addEventListener('load',imageChanged);image.addEventListener('error',imageChanged);imageChanged();
  viewer.querySelector('.viewer-nav').after(button);
  window.addEventListener('pagehide',closeZoom);
  window.FaceFlowGallery={mount,closeZoom,imageChanged};
})();
