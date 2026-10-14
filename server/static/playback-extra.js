/* Common playback actions for the browser and Android WebViews. */
(()=>{
 const p=document.querySelector('#player'),v=document.querySelector('#video');if(!p||!v)return;
 let switching=false;
 function nextEpisode(item,items){if(!item||item.kind!=='episode')return null;return items.filter(x=>x.kind==='episode'&&showKey(x)===showKey(item)&&((Number(x.season)===Number(item.season)&&Number(x.episode)>Number(item.episode))||(Number(x.season)>Number(item.season)&&Number(x.season)>0))).sort((a,b)=>a.season-b.season||a.episode-b.episode||a.id-b.id)[0]||null;}
 const bar=document.createElement('div');bar.className='playback-extra';
 const restart=document.createElement('button');restart.id='play-from-start';restart.textContent='↺ Start over';restart.setAttribute('aria-label','Play from beginning');
 const next=document.createElement('button');next.id='next-episode';next.textContent='⏭ Next episode';bar.append(restart,next);p.append(bar);
 function mount(){const host=p.querySelector('.sp-bottom')||p; if(bar.parentNode!==host)host.append(bar);}
 function update(){mount();const target=nextEpisode(current,library);next.hidden=current?.kind!=='episode';next.disabled=switching||!target;next.title=target?`S${target.season} E${target.episode} · ${target.episode_title||''}`:'No next episode in your library';restart.disabled=switching||!current;}
 restart.onclick=()=>{window.streamportTVSeekCancel?.();if(!current)return;startPlayback(0);current.position=0;api('/api/progress',{id:current.id,position:0,duration:total||0}).catch(error);};
 next.onclick=async()=>{const target=nextEpisode(current,library);if(!target||switching)return;switching=true;update();window.streamportTVSeekCancel?.();const quality=document.querySelector('#play-mode').value;try{await saveProgress();v.pause();await play(target.id,{fromStart:true,quality});}catch(e){error(e)}finally{switching=false;update()}};
 const original=play;play=async function(...args){try{return await original.apply(this,args)}finally{update()}};
 new MutationObserver(mount).observe(p,{childList:true});
 v.addEventListener('ended',update);p.addEventListener('close',()=>window.streamportTVSeekCancel?.());
 window.streamportPlayback={nextEpisode,update};update();
})();
