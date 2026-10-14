'use strict';
// Shared by the web server and Android client. Safe to install only once.
if (!globalThis.streamportSearchInstalled) {
 globalThis.streamportSearchInstalled = true;
 const searchBaseRender=render,searchBaseShell=shell;
 let searchTimer;
 function searchNormalize(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/đ/g,'dj').replace(/[^\p{L}\p{N}]+/gu,' ').trim();}
 function searchScore(title,extra,query){
  const name=searchNormalize(title),all=name+' '+searchNormalize(extra),q=searchNormalize(query);
  if(!q)return 0;
  const terms=q.split(/\s+/);if(!terms.every(t=>all.includes(t)))return 0;
  return name===q?100:name.startsWith(q)?80:name.includes(q)?60:terms.every(t=>name.includes(t))?40:20;
 }
 function movieSearchKey(m){return m.tmdb_id?'tmdb:'+m.tmdb_id:m.imdb?'imdb:'+m.imdb:m.year?'title:'+searchNormalize(m.title)+':'+m.year:'file:'+m.id;}
 function searchResults(items,query){
  const movies=new Map();for(const m of items.filter(x=>x.kind==='movie')){
   const score=searchScore(m.title,m.year,query);if(!score)continue;
   const key=movieSearchKey(m),old=movies.get(key);
   if(!old||score>old.score||score===old.score&&!old.item.poster&&m.poster)movies.set(key,{item:m,score});
  }
  const series=new Map();for(const m of items.filter(x=>x.kind==='episode')){
   const key=showKey(m),score=searchScore(m.series,(m.episode_title||'')+' '+(m.year||''),query);
   if(score>0)series.set(key,Math.max(series.get(key)||0,score));
  }
  const shows=showGroups(items).filter(m=>series.has(showKey(m))).map(m=>({item:m,score:series.get(showKey(m))}));
  const order=(a,b)=>b.score-a.score||(a.item.title||a.item.series).localeCompare(b.item.title||b.item.series)||a.item.id-b.item.id;
  return {movies:[...movies.values()].sort(order).map(x=>x.item),shows:shows.sort(order).map(x=>x.item)};
 }
 // Exposed for shared standalone tests without network or server access.
 globalThis.streamportSearch={normalize:searchNormalize,results:searchResults};
 function resetSearch(){clearTimeout(searchTimer);search='';filter='';detailId=null;page='home';const input=$('#search');if(input)input.value='';render().catch(error);}
 globalThis.streamportSearchBack=()=>{if(search.trim()&&!detailId&&!filter){resetSearch();return true;}return false;};
 function bindSearchInput(){
  const input=$('#search');if(!input)return;input.setAttribute('type','search');input.setAttribute('placeholder','Search movies, series or episodes…');
  input.oninput=e=>{search=e.target.value;detailId=null;filter='';page=search.trim()?'search':'home';clearTimeout(searchTimer);searchTimer=setTimeout(()=>render().catch(error),150);};
  input.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();resetSearch();}else if(e.key==='Enter'){e.preventDefault();clearTimeout(searchTimer);render().catch(error);input.blur();}};
  document.querySelectorAll('[data-page]').forEach(b=>{const fn=b.onclick;b.onclick=e=>{clearTimeout(searchTimer);search='';input.value='';if(fn)fn.call(b,e);};});
 }
 shell=function(){searchBaseShell();bindSearchInput();};
 render=async function(){
  if(!search.trim()){search='';return searchBaseRender();}
  if(detailId||page==='shows'&&filter)return searchBaseRender();
  const result=searchResults(library,search),count=result.movies.length+result.shows.length;
  document.querySelectorAll('[data-page]').forEach(b=>b.classList.remove('selected'));
  $('#content').innerHTML=`<section class="search-results"><div class="section-head"><div><span class="eyebrow">YOUR LIBRARY</span><h1>Search results</h1></div><button id="clear-search" aria-label="Clear search">Clear ✕</button></div><p class="muted" role="status">${count} ${count===1?'result':'results'} for “${esc(search.trim())}”</p>${result.movies.length?`<div class="section-head"><h2>Movies</h2><span class="muted small">${result.movies.length}</span></div>${cards(result.movies)}`:''}${result.shows.length?`<div class="section-head"><h2>TV shows</h2><span class="muted small">${result.shows.length}</span></div>${cards(result.shows,true)}`:''}${!count?'<div class="empty"><h2>No matches found</h2><p>Try part of the title, a different spelling or the release year.</p></div>':''}</section>`;
  $('#clear-search').onclick=resetSearch;bindCards();
  document.querySelectorAll('[data-show]').forEach(b=>b.onclick=()=>{search='';const input=$('#search');if(input)input.value='';filter=b.dataset.show;selectedSeason=null;detailId=null;page='shows';render().catch(error);});
 };
 bindSearchInput();
}
