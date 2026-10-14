const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom'),fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const base=path.resolve(__dirname,'../../StreamPort/static'),assets=path.resolve(__dirname,'../app/src/main/assets');
 const html=fs.readFileSync(path.join(base,'index.html'),'utf8').replace(/<script[\s\S]*?<\/script>/g,'');
 const dom=new JSDOM(html,{url:'http://server:8097/',runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window,d=w.document;
 for(const name of [path.join(base,'style.css'),path.join(assets,'mobile.css')]){const st=d.createElement('style');st.textContent=fs.readFileSync(name,'utf8');d.head.append(st);}
 d.querySelector('#app').innerHTML='<header class="app-header"><div class="search"></div></header>';
 w.eval(fs.readFileSync(path.join(assets,'mobile.js'),'utf8'));
 const p=d.querySelector('#player'),v=d.querySelector('#video');
 assert(p.classList.contains('android-player'));assert(!v.controls);assert.equal(w.getComputedStyle(p).position,'fixed');assert.equal(w.getComputedStyle(p).backgroundColor,'rgb(0, 0, 0)');assert.equal(w.getComputedStyle(p).marginTop,'0px');assert.equal(w.getComputedStyle(v).objectFit,'contain');
 const click=label=>d.querySelector(`[aria-label="${label}"]`).click();
 assert(!d.querySelector('.sp-sheet-mask').classList.contains('open'));click('Subtitles');assert(d.querySelector('.sp-sheet-mask').classList.contains('open'));assert(d.querySelector('#subtitle-track').closest('.sp-sheet-group').classList.contains('active'));assert(d.querySelector('#find-subs').closest('.sp-sheet-group').classList.contains('active'));assert(w.streamportMobileBack());assert(!d.querySelector('.sp-sheet-mask').classList.contains('open'));
 click('Audio');assert(d.querySelector('#audio-track').closest('.sp-sheet-group').classList.contains('active'));click('Close settings');click('Playback quality');assert(d.querySelector('#play-mode').closest('.sp-sheet-group').classList.contains('active'));click('Close settings');
 const range=d.querySelector('#seek');range.value=20;let seen;range.onchange=e=>seen=Number(e.target.value);click('Back 10 seconds');assert.equal(seen,10);click('Forward 10 seconds');assert.equal(seen,20);
 click('Lock controls');assert(p.classList.contains('sp-locked'));assert(p.classList.contains('sp-hidden'));assert(w.streamportMobileBack());assert(!p.classList.contains('sp-locked'));
 click('Playback speed');const speed=d.querySelector('[aria-label="Playback speed"]:is(select)');speed.value='1.5';speed.dispatchEvent(new w.Event('change'));assert.equal(v.playbackRate,1.5);click('Close settings');
 d.querySelector('#app').innerHTML='<header class="app-header"><div class="search"></div></header>';await new Promise(r=>setTimeout(r,60));assert.equal(d.querySelectorAll('.app-header #android-app-options').length,1);
 const java=fs.readFileSync(path.resolve(__dirname,'../app/src/main/java/org/streamport/mobile/MainActivity.java'),'utf8');assert(java.includes('shouldInterceptRequest'));assert(java.includes('createElement(\'link\')'));assert(!java.includes('createElement(\'style\')'));assert(java.includes('getAssets().open("mobile.css")'));assert(java.includes('ServerAddress.sameOrigin(server,url)'));
 dom.window.close();console.log('PASS: immersive style rules, video fit, settings sheets, subtitles preservation, ±10s seeking, lock/back, playback speed, menu remount and same-origin stylesheet loading.');
})().catch(e=>{console.error(e);process.exit(1)});
