/* TV 1.4: row-based remote navigation; stable views; explicit text editing. */
(() => {
 if(window.streamportTVInstalled)return true;
 window.streamportTVInstalled=true;document.documentElement.classList.add('streamport-tv');
 const $=s=>document.querySelector(s),player=$('#player'),video=$('#video');
 const selector='button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]';
 const signal=name=>{location.href='streamport://'+name;};
 let remembered='',libraryFocus='',timer=0,editing=null,rendering=false,lastSignature='',lastRoute='',pending=false;
 const views=new Map();
 function identity(el){if(!el)return '';if(el.id)return '#'+el.id;for(const key of ['themeChoice','page','detail','show','play','favorite','season','sort','direction','reset','view','folder','collection','identify'])if(el.dataset?.[key]!==undefined)return key+':'+el.dataset[key];return el.getAttribute('aria-label')||el.name||el.textContent.trim().slice(0,100);}
 function scope(){const ds=[...document.querySelectorAll('dialog[open]')],d=ds[ds.length-1];return d===player?(player.querySelector('.sp-sheet-mask.open')||player):(d||document);}
 function candidates(root=scope()){
  const styles=new WeakMap();
  function visible(el){
   if(!el.getClientRects().length||el.closest('[hidden],.tv-concealed'))return false;
   for(let p=el;p&&p.nodeType===1;p=p.parentElement){
    let c=styles.get(p);if(!c){c=getComputedStyle(p);styles.set(p,c);}
    if(c.visibility==='hidden'||c.display==='none')return false;
    if(p.tagName==='DETAILS'&&!p.open&&el!==p.querySelector('summary'))return false;
   }return true;
  }
  return [...root.querySelectorAll(selector)].filter(visible);
 }
 const motions=new Map();
 function position(root,axis){return root===window?(axis==='y'?scrollY:scrollX):root[axis==='y'?'scrollTop':'scrollLeft'];}
 function limit(root,axis){return root===window?Math.max(0,document.documentElement.scrollHeight-innerHeight):Math.max(0,root[axis==='y'?'scrollHeight':'scrollWidth']-root[axis==='y'?'clientHeight':'clientWidth']);}
 function stopMotion(){
  for(const [root,motion] of motions){clearTimeout(motion.timer);root.scrollTo({left:position(root,'x'),top:position(root,'y'),behavior:'instant'});}motions.clear();
 }
 function animateScroll(root,axis,value){
  const end=Math.max(0,Math.min(limit(root,axis),value)),old=motions.get(root);
  if(old&&old.axis===axis&&Math.abs(old.end-end)<1)return;
  if(old)clearTimeout(old.timer);
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  // Let WebView animate scrolling; no JS position writes on every display frame.
  root.scrollTo({[axis==='y'?'top':'left']:end,behavior:reduced?'instant':'smooth'});
  if(reduced){motions.delete(root);return;}
  const motion={root,axis,end,timer:0};motion.timer=setTimeout(()=>motions.delete(root),700);motions.set(root,motion);
 }
 function boundaryScroll(el,dir){
  const root=scope()===document?window:el.closest('.sp-sheet,dialog');if(!root)return;
  const current=[...motions.values()].find(m=>m.root===root&&m.axis==='y')?.end??position(root,'y');
  const step=(root===window?innerHeight:root.clientHeight)*.65;
  animateScroll(root,'y',current+(dir==='up'?-step:step));
 }
 function reveal(el){
  // Only deliberate remote input starts animation; refreshes never move the view.
  const rail=el.closest('.rail,.people-row,.studio-row');if(rail){const a=el.getBoundingClientRect(),b=rail.getBoundingClientRect();if(a.left<b.left+8)animateScroll(rail,'x',rail.scrollLeft+a.left-b.left-8);else if(a.right>b.right-8)animateScroll(rail,'x',rail.scrollLeft+a.right-b.right+8);}
  if(el.closest('#tv-nav'))return;
  const a=el.getBoundingClientRect(),margin=28,top=document.body.classList.contains('tv-search')?82:margin;
  if(scope()===document){
   const heading=el.closest('.shelf,.panel')?.querySelector('h2'),h=heading?.getBoundingClientRect();
   const revealTop=h&&a.bottom-h.top<innerHeight-top-margin?Math.min(a.top,h.top):a.top;
   if(revealTop<top)animateScroll(window,'y',scrollY+revealTop-top);
   else if(a.bottom>innerHeight-margin)animateScroll(window,'y',scrollY+a.bottom-innerHeight+margin);
  }else{const sheet=el.closest('.sp-sheet,dialog');if(sheet){const b=sheet.getBoundingClientRect();if(a.top<b.top+20)animateScroll(sheet,'y',sheet.scrollTop+a.top-b.top-20);else if(a.bottom>b.bottom-20)animateScroll(sheet,'y',sheet.scrollTop+a.bottom-b.bottom+20);}}
 }
 function focus(el,scroll=false){if(!el)return;el.focus({preventScroll:true});remembered=identity(el);if(scroll)reveal(el);}
 function restore(key=remembered,scroll=false){const list=candidates();if(!list.length)return;if(list.includes(document.activeElement))return;focus(list.find(x=>identity(x)===key)||list.find(x=>x.matches('.primary,.card'))||list[0],scroll);}
 function endEditing(){if(!editing)return false;editing.readOnly=true;editing.removeAttribute('data-tv-editing');editing=null;signal('keyboard-close');return true;}
 function beginEditing(el){editing=el;el.readOnly=false;el.dataset.tvEditing='true';el.focus({preventScroll:true});el.click();signal('keyboard');}
 function protectInputs(){document.querySelectorAll('input:not([type=range]):not([type=checkbox]):not([type=radio]),textarea').forEach(el=>{if(el!==editing)el.readOnly=true;});}
 function route(){try{return [page,detailId||'',filter||'',browseMode||'',folderPath||'',search.trim()?'search':''].join('|');}catch{return 'auth';}}
 function signature(){try{return JSON.stringify([route(),search,selectedSeason,typeof genreFilter==='undefined'?'':genreFilter,typeof collectionFilter==='undefined'?'':collectionFilter,localStorage.getItem('streamport-sort-'+me?.id),library]);}catch{return '';}}
 function sidebar(){
  const header=$('.app-header');if(!header)return;
  if(!$('#tv-nav')){
   const nav=document.createElement('nav');nav.id='tv-nav';nav.setAttribute('aria-label','StreamPort TV');
   nav.innerHTML='<div class="tv-wordmark"><img src="/icon.svg" alt="">StreamPort</div><div class="tv-nav-items"></div><div class="tv-profile"></div>';
   const entries=[['search','⌕','Search'],['home','⌂','Home'],['movies','▷','Movies'],['shows','▤','TV shows'],['continue','◷','Continue'],['collections','▦','Collections'],['favorites','♡','Favorites'],['requests','＋','Requests'],['account','◉','My account']];
   for(const [id,icon,label] of entries){const b=document.createElement('button');b.dataset.page=id;b.innerHTML='<span aria-hidden="true">'+icon+'</span><span>'+label+'</span>';b.onclick=()=>{endEditing();page=id;search='';filter='';detailId=null;selectedSeason=null;browseMode='library';folderPath=null;if(typeof collectionFilter!=='undefined')collectionFilter='';const input=$('#search');if(input)input.value='';render().catch(error);};nav.querySelector('.tv-nav-items').append(b);}
   const appearance=document.createElement('button');appearance.id='tv-appearance-open';appearance.innerHTML='<span>◐</span><span>Appearance</span>';appearance.onclick=()=>window.streamportTVTheme.open();nav.querySelector('.tv-nav-items').append(appearance);
   const settings=document.createElement('button');settings.id='tv-options';settings.innerHTML='<span>⚙</span><span>App settings</span>';settings.onclick=()=>signal('settings');nav.querySelector('.tv-nav-items').append(settings);header.after(nav);
  }
  const profile=$('#tv-nav .tv-profile'),name=typeof me!=='undefined'&&me?me.name:'';if(profile.textContent!==name)profile.textContent=name;
  document.querySelectorAll('#tv-nav [data-page]').forEach(b=>b.classList.toggle('selected',typeof page!=='undefined'&&b.dataset.page===page));
  document.body.classList.toggle('tv-search',typeof page!=='undefined'&&page==='search');
 }
 function decorate(){
  sidebar();protectInputs();window.streamportTVTheme?.decorate();
  document.querySelectorAll('#content img:not([decoding])').forEach(img=>{img.decoding='async';});
  // Informational rows must be reachable with a remote, even without links.
  document.querySelectorAll('.people-row .person,.studio-row > div').forEach((el,i)=>{el.tabIndex=0;el.dataset.tvInfo=String(i);});
  document.querySelectorAll('.media-tile').forEach(t=>t.classList.toggle('tv-favorite',t.querySelector('[data-favorite]')?.getAttribute('aria-pressed')==='true'));
  const detail=$('.media-detail');
  if(detail&&!detail.dataset.tvReady){
   detail.dataset.tvReady='true';
   const play=detail.querySelector('[data-play]'),copy=detail.querySelector(':scope > div:not(.poster)');
   if(copy)copy.classList.add('tv-detail-copy');
   const actions=document.createElement('div');actions.className='tv-detail-actions';actions.dataset.tvRow='detail-primary';
   if(play){const oldRow=play.closest('.row');actions.append(play);if(oldRow&&!oldRow.children.length)oldRow.remove();}
   const mediaActions=$('#media-actions');if(mediaActions){[...mediaActions.children].forEach(b=>actions.append(b));mediaActions.remove();}
   if(copy)copy.append(actions);
   // Technical/admin information is secondary and cannot split the primary action row.
   const extras=document.createElement('details');extras.className='tv-detail-more';extras.innerHTML='<summary>More information</summary><div class="tv-admin-info"></div>';
   if(copy){[...copy.children].filter(el=>el.matches('p.small,details')).forEach(el=>extras.lastElementChild.append(el));copy.append(extras);}
   const identify=$('.detail-extras [data-identify]');if(identify)extras.lastElementChild.append(identify);
   if(!extras.lastElementChild.children.length)extras.remove();
  }
  document.querySelectorAll('.sp-sheet .row').forEach(el=>el.classList.add('tv-sheet-row'));
 }
 // Consecutive visual rows, not a global distance score. A distant aligned control
 // must never beat the row directly above/below the current control.
 function rowsFor(list,rects=new Map(list.map(el=>[el,el.getBoundingClientRect()]))){
  const sorted=list.slice().sort((a,b)=>rects.get(a).top-rects.get(b).top||rects.get(a).left-rects.get(b).left),rows=[];
  for(const el of sorted){const r=rects.get(el),last=rows[rows.length-1];
   if(last&&Math.abs(last.top-r.top)<Math.min(18,r.height*.35))last.items.push(el);
   else rows.push({top:r.top,items:[el]});
  }
  return rows.map(r=>r.items.sort((a,b)=>rects.get(a).left-rects.get(b).left));
 }
 function nextInDirection(list,active,dir){
  const rects=new Map(list.map(el=>[el,el.getBoundingClientRect()])),rows=rowsFor(list,rects),ri=rows.findIndex(r=>r.includes(active));if(ri<0)return list[0]||null;
  const row=rows[ri],ci=row.indexOf(active);
  if(dir==='left'||dir==='right')return row[ci+(dir==='left'?-1:1)]||null;
  const other=rows[ri+(dir==='up'?-1:1)];if(!other)return null;
  if(active.matches('#detail-back,#show-back')&&dir==='down')return list.find(el=>el.closest('.tv-detail-actions')&&el.matches('[data-play]'))||other[0];
  const center=el=>rects.get(el).left+rects.get(el).width/2,x=center(active);
  return other.reduce((a,b)=>Math.abs(center(b)-x)<Math.abs(center(a)-x)?b:a);
 }
 function showControls(){if(!player?.open)return;player.classList.add('tv-controls');player.classList.remove('sp-hidden');clearTimeout(timer);timer=setTimeout(()=>{if(!video.paused&&!player.querySelector('.sp-sheet-mask.open'))player.classList.remove('tv-controls');},5000);}
 let seekState=null,seekTimer=0;
 function cancelSeek(){clearTimeout(seekTimer);seekState=null;}
 function commitSeek(){if(!seekState)return;const state=seekState;cancelSeek();if(!player.open)return;const r=$('#seek');r.value=state.target;r.dispatchEvent(new Event('change',{bubbles:true}));showControls();}
 function seek(delta,held=0){
  const r=$('#seek');if(!r)return;const now=performance.now(),direction=Math.sign(delta);
  if(!seekState||seekState.direction!==direction){if(seekState)commitSeek();seekState={target:Number(r.value),direction,last:0};}
  if(now-seekState.last<250)return;
  seekState.last=now;const step=held>=5000?30:held>=2000?20:10;
  seekState.target=Math.max(0,Math.min(Math.max(0,Number(r.max)-.1),seekState.target+direction*step));
  r.value=seekState.target;const status=$('.sp-status');if(status)status.textContent=(direction<0?'−':'+')+step+' s · '+time(seekState.target);showControls();
  clearTimeout(seekTimer);seekTimer=setTimeout(commitSeek,650);
 }
 window.streamportTVKeyUp=()=>{commitSeek();};
 window.streamportTVSeekCancel=cancelSeek;
 video.addEventListener('timeupdate',()=>{if(seekState)$('#seek').value=seekState.target;});
 video.addEventListener('emptied',cancelSeek);
 window.addEventListener('blur',cancelSeek);
 function toggle(){if(video.paused)video.play().catch(()=>player.querySelector('[aria-label="Playback quality"]')?.click());else video.pause();showControls();}
 // Native select popups are not consistently controllable from a TV WebView.
 function selectDialog(el){
  const d=document.createElement('dialog');d.className='tv-choice';d.setAttribute('aria-label',el.getAttribute('aria-label')||el.closest('label')?.childNodes[0]?.textContent||'Choose');
  const title=document.createElement('h2');title.textContent=d.getAttribute('aria-label');d.append(title);
  [...el.options].filter(o=>!o.disabled).forEach(o=>{const b=document.createElement('button');b.textContent=(o.selected?'✓  ':'')+o.textContent;b.dataset.value=o.value;b.onclick=()=>{el.value=o.value;el.dispatchEvent(new Event('change',{bubbles:true}));d.close();};d.append(b);});
  d.addEventListener('close',()=>{d.remove();focus(el.isConnected?el:candidates().find(e=>identity(e)===identity(el)));});document.body.append(d);d.showModal();focus([...d.querySelectorAll('button')].find(b=>b.dataset.value===el.value)||d.querySelector('button'));
 }
 window.streamportTVKey=function(key,held=0){
  if(editing){if(key==='done'){const el=editing;endEditing();el.dispatchEvent(new Event('change',{bubbles:true}));if(el.id==='search'){render().catch(error);el.blur();setTimeout(()=>focus($('#content .card')||$('#content button'),true),180);}return true;}return false;}
  const inPlayer=player?.open,sheet=inPlayer&&player.querySelector('.sp-sheet-mask.open'),modal=scope()!==document;
  if(inPlayer&&['toggle','play','pause','rewind','forward'].includes(key)){if(key==='toggle')toggle();else if(key==='play')video.play().catch(()=>{});else if(key==='pause')video.pause();else seek(key==='rewind'?-10:10,held);showControls();return true;}
  if(inPlayer&&!sheet&&!player.classList.contains('tv-controls')){showControls();focus(player.querySelector('.sp-toggle'));if(key==='left'||key==='right')seek(key==='left'?-10:10,held);else if(key==='ok')toggle();return true;}
  if(inPlayer&&!sheet&&['left','right'].includes(key)&&(seekState||document.activeElement?.matches('.sp-toggle,#seek'))){seek(key==='left'?-10:10,held);return true;}
  if(seekState)commitSeek();
  if(inPlayer)showControls();
  let active=document.activeElement,list=candidates();if(!list.includes(active)){restore();active=document.activeElement;}
  if(!active)return true;
  if(key==='ok'){
   if(active.matches('input:not([type=range]):not([type=checkbox]):not([type=radio]),textarea'))beginEditing(active);
   else if(active.matches('select'))selectDialog(active);
   else if(active.matches('summary')){active.parentElement.open=!active.parentElement.open;}
   else if(active.matches('input[type=range]')&&inPlayer)toggle();else active.click();return true;
  }
  if(!['left','right','up','down'].includes(key))return true;
  if(active.matches('input[type=range]')&&['left','right'].includes(key)){if(inPlayer)seek(key==='left'?-10:10,held);return true;}
  const inNav=!!active.closest('#tv-nav');
  if(!modal&&inNav){const navlist=candidates($('#tv-nav')),i=navlist.indexOf(active);if(key==='up'||key==='down')focus(navlist[i+(key==='up'?-1:1)],true);else if(key==='right'){const contentList=list.filter(el=>!el.closest('#tv-nav'));focus(contentList.find(el=>identity(el)===libraryFocus)||contentList.find(el=>el.matches('.primary,.card'))||contentList[0],true);}return true;}
  if(!modal)list=list.filter(el=>!el.closest('#tv-nav'));
  const target=nextInDirection(list,active,key);
  if(target)focus(target,true);else if(key==='up'||key==='down')boundaryScroll(active,key);else if(key==='left'&&!modal)focus($('#tv-nav .selected')||$('#tv-nav button'));
  return true;
 };
 window.streamportTVBack=()=>{if(endEditing())return true;const d=$('dialog.tv-choice[open]');if(d){d.close();return true;}return false;};
 let heldKey='',heldSince=0;
 document.addEventListener('keyup',()=>{heldKey='';window.streamportTVKeyUp();},true);
 document.addEventListener('keydown',e=>{if(editing){if(e.key==='Enter'){e.preventDefault();window.streamportTVKey('done');}return;}const keys={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down',Enter:'ok',MediaPlayPause:'toggle'};if(keys[e.key]){e.preventDefault();e.stopImmediatePropagation();if(heldKey!==e.key||!e.repeat){heldKey=e.key;heldSince=performance.now();}window.streamportTVKey(keys[e.key],performance.now()-heldSince);}},true);
 document.addEventListener('click',e=>{if(e.target.closest('[data-sort],[data-direction]'))lastSignature='';},true);
 document.addEventListener('focusin',e=>{remembered=identity(e.target);if(scope()===document&&!e.target.closest('#tv-nav'))libraryFocus=remembered;});
 // CookieManager is notified after authenticated fetch responses, not just page loads.
 if(window.fetch){const originalFetch=window.fetch;window.fetch=async function(input,options){const response=await originalFetch.call(this,input,options);const url=new URL(typeof input==='string'?input:input.url,location.href);if(url.origin===location.origin){if(['/api/login','/api/me','/api/setup'].includes(url.pathname)&&response.ok)signal('session-sync');if((url.pathname==='/api/logout'&&response.ok)||(url.pathname==='/api/me'&&response.status===401))signal('session-clear');}return response;};}
 if(typeof render==='function'){
  const baseRender=render;
  render=async function(){
   browseMode='library';const sig=signature(),r=route();if(sig&&sig===lastSignature&&$('#content')?.children.length)return;
   if(rendering){pending=true;return;}stopMotion();rendering=true;
   const old=lastRoute,saved={focus:identity(document.activeElement),y:window.scrollY,rails:[...document.querySelectorAll('.rail')].map(el=>el.scrollLeft)};
   if(old)views.set(old,saved);
   try{
    if(typeof page!=='undefined'&&page==='search'&&!search.trim()&&!detailId){$('#content').innerHTML='<div class="tv-search-empty"><span class="eyebrow">YOUR ENTIRE COLLECTION</span><h1>Find your next watch.</h1><p>Select the search field and press OK to type a title.</p></div>';}
    else await baseRender();
    decorate();lastSignature=signature();lastRoute=route();
    const same=old===lastRoute,state=same?saved:views.get(lastRoute),list=candidates();
    if(state){[...document.querySelectorAll('.rail')].forEach((el,i)=>el.scrollLeft=state.rails[i]||0);window.scrollTo(0,state.y);focus(list.find(el=>identity(el)===state.focus)||$('#content .primary')||$('#content .card'));}
    else {window.scrollTo(0,0);focus(document.body.classList.contains('tv-search')?$('#search'):($('#content .primary')||$('#content .card')||$('#content button')||$('#tv-nav .selected')));}
   }finally{rendering=false;if(pending){pending=false;queueMicrotask(()=>render().catch(error));}}
  };
 }
 // Observe structural events only. Never refocus or scroll on timer text, images,
 // probe results or arbitrary DOM changes while the current focus remains valid.
 let scheduled=false;
 new MutationObserver(()=>{if(scheduled||rendering)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;decorate();if(!document.activeElement?.isConnected||document.activeElement===document.body)restore();});}).observe($('#app')||document.body,{childList:true,subtree:true});
 if(player)new MutationObserver(()=>{if(player.open){showControls();focus(player.querySelector('.sp-toggle'));}else{clearTimeout(timer);restore(libraryFocus);}}).observe(player,{attributes:true,attributeFilter:['open']});
 video?.addEventListener('pause',showControls);video?.addEventListener('playing',showControls);
 window.streamportTVNavigation={identity,nextInDirection,rowsFor,restore,decorate,route,animateScroll,boundaryScroll,stopMotion};
 decorate();if(typeof me!=='undefined'&&me)signal('session-sync');restore();return true;
})();
