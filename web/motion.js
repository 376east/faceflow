/* Short state transitions; no scroll interception or page-load choreography. */
'use strict';
(()=>{
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)'),active=new Set();
  function reveal(element,distance){
    if(!element||!window.gsap||reduce.matches)return;
    window.gsap.killTweensOf(element);active.add(element);
    window.gsap.fromTo(element,{opacity:.7,y:distance},{opacity:1,y:0,duration:.18,ease:'power2.out',clearProps:'opacity,transform',onComplete:()=>active.delete(element)});
  }
  reduce.addEventListener('change',()=>{if(reduce.matches&&window.gsap){for(const element of active){window.gsap.killTweensOf(element);window.gsap.set(element,{clearProps:'opacity,transform'});}active.clear();}});
  window.FaceFlowMotion={open:element=>reveal(element,6),results:element=>reveal(element,8)};
})();
