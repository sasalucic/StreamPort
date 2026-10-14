(()=>{
 const root=document.documentElement;
 const themes={kiwi:['Electric Kiwi','#ccff00','204,255,0','#153126'],ocean:['Ocean Blue','#71b7ff','113,183,255','#152f52'],violet:['Royal Violet','#bb9aff','187,154,255','#352050'],coral:['Sunset Coral','#ff998a','255,153,138','#49242e'],teal:['Arctic Teal','#67e2ce','103,226,206','#153e40'],amber:['Amber Gold','#ffd078','255,208,120','#423321']};
 let owner='',returnFocus;
 const key=()=> 'streamport-theme-'+(typeof me!=='undefined'&&me?me.id:'guest');
 function apply(id,save=false){if(!themes[id])id='kiwi';const t=themes[id];root.dataset.theme=id;root.style.setProperty('--accent',t[1]);root.style.setProperty('--kiwi',t[1]);root.style.setProperty('--accent-rgb',t[2]);root.style.setProperty('--theme-deep',t[3]);
 if(save)try{localStorage.setItem(key(),id)}catch{}
 const svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="18" fill="'+t[1]+'"/><path d="M25 18 47 32 25 46Z" fill="#081015"/><path d="M16 18v28" stroke="#081015" stroke-width="5" stroke-linecap="round"/></svg>';
 const src='data:image/svg+xml,'+encodeURIComponent(svg);document.querySelectorAll('.tv-wordmark img,.brand img').forEach(img=>{if(img.getAttribute('src')!==src)img.src=src});
 document.querySelectorAll('[data-theme-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.themeChoice===id)));
 }
 function decorate(){if(owner!==key()){owner=key();let id;try{id=localStorage.getItem(owner)}catch{}apply(id||'kiwi')}else apply(root.dataset.theme||'kiwi');document.querySelectorAll('.library-head [data-view]').forEach(b=>b.remove());}
 function open(){let d=document.querySelector('#tv-appearance');if(!d){d=document.createElement('dialog');d.id='tv-appearance';d.setAttribute('aria-labelledby','tv-appearance-title');d.innerHTML='<div class="theme-heading"><h2 id="tv-appearance-title">Appearance</h2><button id="theme-close" aria-label="Close appearance">✕</button></div><p>Choose your cinema colour. Saved for this account on this TV.</p><div class="tv-theme-grid"></div>';for(const [id,t] of Object.entries(themes)){const b=document.createElement('button');b.dataset.themeChoice=id;b.style.setProperty('--swatch',t[1]);b.style.setProperty('--swatch-deep',t[3]);b.innerHTML='<span class="tv-theme-sample"></span><strong>'+t[0]+'</strong>';b.onclick=()=>apply(id,true);d.querySelector('.tv-theme-grid').append(b)}d.querySelector('#theme-close').onclick=()=>d.close();d.addEventListener('close',()=>{if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true})});document.body.append(d)}returnFocus=document.activeElement;apply(root.dataset.theme||'kiwi');d.showModal();d.querySelector('[data-theme-choice='+root.dataset.theme+']').focus({preventScroll:true});}
 window.streamportTVTheme={apply,decorate,open,themes};
})();
