'use strict';
(() => {
 let active=null, panel=null, writing=false;
 const storageKey=c=>'streamport.subtitle-sync.v1:'+JSON.stringify([c.user,c.media,c.key,c.version]);
 function read(c){try{const n=Number(localStorage.getItem(storageKey(c)));return Number.isFinite(n)?Math.max(-600,Math.min(600,n)):0;}catch{return 0;}}
 function persist(c,n){try{localStorage.setItem(storageKey(c),String(n));return true;}catch{return false;}}
 function context(){const option=$('#subtitle-track')?.selectedOptions[0];return current&&option?.value!==''?{user:me?.id??me?.name,media:current.id,key:option.dataset.key,version:option.dataset.version||'',admin:!!me?.admin}:null;}
 function mount(){
  if(panel?.isConnected)return;
  panel=document.createElement('section');panel.id='subtitle-sync';panel.setAttribute('aria-label','Subtitle synchronization');
  panel.innerHTML='<h4>Subtitle sync</h4><p class="sync-help">Earlier − / Later + · changes apply immediately</p><div class="sync-controls"><button type="button" data-shift="-0.5" aria-label="Subtitles half a second earlier">−0.5 s</button><button type="button" data-shift="-0.1" aria-label="Subtitles one tenth of a second earlier">−0.1 s</button><output id="sync-value" aria-live="polite">0.0 s</output><button type="button" data-shift="0.1" aria-label="Subtitles one tenth of a second later">+0.1 s</button><button type="button" data-shift="0.5" aria-label="Subtitles half a second later">+0.5 s</button></div><div class="sync-input-row"><label>Offset (seconds)<input id="sync-seconds" type="number" min="-600" max="600" step="0.1" inputmode="decimal" value="0"></label><button type="button" id="sync-apply">Apply</button><button type="button" id="sync-reset">Reset</button></div><p id="sync-feedback" role="status"></p><details id="sync-save-area"><summary>Save to subtitle file · Admin</summary><p>This changes the subtitle for everyone. A backup is created first.</p><button type="button" id="sync-save">Save current offset to file</button></details>';
  const label=$('#subtitle-track').closest('label');label.after(panel);
  panel.addEventListener('click',e=>{if(e.target.closest('button,input,summary'))e.stopPropagation();});
  panel.querySelectorAll('[data-shift]').forEach(b=>b.onclick=()=>change((active?.delay||0)+Number(b.dataset.shift)));
  panel.querySelector('#sync-reset').onclick=()=>change(0);
  panel.querySelector('#sync-apply').onclick=()=>{const value=panel.querySelector('#sync-seconds').value; if(value.trim()==='')return;change(Number(value));};
  panel.querySelector('#sync-save').onclick=save;
 }
 function paint(){
  mount();const n=active?.delay||0;
  panel.querySelector('#sync-value').textContent=(n>0?'+':'')+n.toFixed(1)+' s';
  panel.querySelector('#sync-seconds').value=n.toFixed(1);
  panel.querySelectorAll('button,input').forEach(x=>x.disabled=!active||writing);
  panel.querySelector('#sync-save-area').hidden=!active?.context.admin;
  panel.querySelector('#sync-save').disabled=!active||writing||n===0;
 }
 function apply(){
  if(!active)return;
  const {track,cues,delay,base}=active;
  // Always derive from original timings, including cues before the transcode start.
  // Keeping removed cues allows a subsequent positive adjustment to restore them.
  for(const cue of Array.from(track.cues||[]))track.removeCue(cue);
  for(const row of cues){const end=row.end+delay-base;if(end<=0)continue;
   row.cue.startTime=Math.max(0,row.start+delay-base);row.cue.endTime=end;track.addCue(row.cue);
  }
  track.mode='showing';
 }
 function change(n){
  if(!active||writing)return;
  if(!Number.isFinite(n)||n < -600||n > 600){panel.querySelector('#sync-feedback').textContent='Enter an offset between −600 and +600 seconds.';return;}
  active.delay=Math.round(n*10)/10;apply();
  const saved=persist(active.context,active.delay);paint();
  panel.querySelector('#sync-feedback').textContent=saved?'Remembered for this account and subtitle on this device.':'Applied for this session; device storage is unavailable.';
 }
 function load(track,c,base){
  if(!c){clear();return;}
  active={track,context:c,base,cues:Array.from(track.cues||[]).map(cue=>({cue,start:cue.startTime,end:cue.endTime})),delay:read(c)};
  apply();paint();panel.querySelector('#sync-feedback').textContent='Remembered per account, title and subtitle on this device.';
 }
 function clear(){active=null;paint();panel.querySelector('#sync-feedback').textContent='Select a subtitle to adjust its timing.';}
 async function save(){
  if(!active||writing||!active.context.admin)return;
  const snapshot=active,delta=snapshot.delay;writing=true;paint();
  try{
   const result=await api('/api/subtitles/shift',{id:snapshot.context.media,key:snapshot.context.key,version:snapshot.context.version,seconds:delta});
   // Preserve timings for other sessions still reading the old version; new file
   // versions have a fresh storage key and start at zero (no double adjustment).
   if(active===snapshot&&current?.id===snapshot.context.media){
    await loadSubs(snapshot.context.key);
    panel.querySelector('#sync-feedback').textContent='Saved to file. Backup created. Live offset reset to 0.';
   }
  }catch(e){panel.querySelector('#sync-feedback').textContent=e.message||String(e);}
  finally{writing=false;paint();}
 }
 window.StreamPortSubtitleSync={context,load,clear};
 // Clearing on selector changes prevents editing the previous track while loading.
 $('#subtitle-track').addEventListener('change',clear);
 mount();clear();
 new MutationObserver(()=>{if(!window.document)return;const label=$('#subtitle-track')?.closest('label');if(label?.isConnected&&label.nextElementSibling!==panel)label.after(panel);}).observe($('#player'),{childList:true,subtree:true});
})();
