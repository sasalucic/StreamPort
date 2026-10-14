// Real server UI scripts + TV adapter, with explicit geometry fixtures for D-pad tests.
const {JSDOM,VirtualConsole}=require(process.env.JSDOM_PATH||'jsdom');
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
(async()=>{
 const root=path.resolve(__dirname,'../../StreamPort/static'),assets=path.resolve(__dirname,'../app/src/main/assets');
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8').replace(/<script[\s\S]*?<\/script>/g,'');
 const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('navigation'))throw e;});
 const dom=new JSDOM(html,{url:'http://tv-server:8097/',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});const w=dom.window,d=w.document,ctx=dom.getInternalVMContext();
 w.matchMedia=()=>({matches:true});
 const observers=[],BaseObserver=w.MutationObserver;w.MutationObserver=class extends BaseObserver{constructor(fn){super(fn);observers.push(this);}};
 const run=s=>vm.runInContext(s,ctx),tick=()=>new Promise(r=>setTimeout(r,60));let scrolls=0,y=0;
 let lastScroll;w.scrollTo=(x,next)=>{lastScroll=x;y=typeof x==='object'?(x.top??y):next;scrolls++;};w.scrollBy=(x,next)=>{y+=next;scrolls++;};Object.defineProperty(w,'scrollY',{get:()=>y});
 w.HTMLElement.prototype.scrollIntoView=function(){throw Error('Uncontrolled scrollIntoView');};
 w.HTMLElement.prototype.getBoundingClientRect=function(){const [left,top,width,height]=(this.dataset.rect||'0,0,100,40').split(',').map(Number);return {left,top,width,height,right:left+width,bottom:top+height};};
 w.HTMLElement.prototype.getClientRects=function(){if(!this.dataset.rect)return [];for(let p=this;p;p=p.parentElement)if(p.hidden||p.tagName==='DIALOG'&&!p.open)return [];return [this.getBoundingClientRect()];};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 w.fetch=async()=>({ok:true,status:200,json:async()=>({streams:[]})});w.setInterval=()=>0;
 const fixtures=[{id:1,title:'Film One',kind:'movie',year:'2024',overview:'An overview',duration:7200,size:100,poster:'',backdrop:'',source:'tmdb',favorite:false},{id:2,title:'Film Two',kind:'movie',year:'2025',overview:'Overview',duration:7000,size:100,poster:''}];
 for(const file of ['app.js','enhancements.js','search.js','features.js'])run(fs.readFileSync(path.join(root,file),'utf8').replace(/boot\(\);\s*$/,''));
 run(`me={id:1,name:'TV user',admin:1};library=${JSON.stringify(fixtures)};shell();`);await run('render()');
 for(const file of ['mobile.js','tv.js'])run(fs.readFileSync(path.join(assets,file),'utf8'));
 await run('render()');await tick();assert(d.querySelector('#tv-nav'));
 // Back must prefer Play in the next row even when Favorite is horizontally closer.
 run('detailId=1');await run('render()');await tick();
 const back=d.querySelector('#detail-back'),play=d.querySelector('.tv-detail-actions [data-play]'),fav=d.querySelector('.tv-detail-actions [data-favorite]');
 assert(play&&fav,'primary actions consolidated');back.dataset.rect='100,40,140,40';play.dataset.rect='360,180,150,44';fav.dataset.rect='100,180,150,44';
 back.focus();w.streamportTVKey('down');assert.equal(d.activeElement,play,'Back Down selects Play');
 // Vertical nearest row beats a more aligned but distant search box.
 const a=d.createElement('button'),b=d.createElement('button'),search=d.createElement('button');
 a.dataset.rect='500,600,150,100';b.dataset.rect='200,400,150,100';search.dataset.rect='500,0,150,40';
 assert.equal(w.streamportTVNavigation.nextInDirection([search,b,a],a,'up'),b,'Up cannot skip a row');
 // Identical 15-second refresh: not one element replaced, not one scroll.
 play.focus();w.scrollTo(0,170);const originalContent=d.querySelector('#content').innerHTML,beforeScroll=scrolls;
 for(let i=0;i<4;i++)await run('render()');await tick();
 assert.equal(d.querySelector('#content').innerHTML,originalContent);assert.equal(d.activeElement,play);assert.equal(scrolls,beforeScroll,'idle refresh must never scroll');
 // Metadata probes/status text mutations must not move valid focus either.
 d.querySelector('.tv-detail-copy').append(d.createElement('span'));await tick();assert.equal(d.activeElement,play);assert.equal(scrolls,beforeScroll);
 // A real changed library re-render restores both focus and scroll once.
 run("library[0].favorite=true");await run('render()');await tick();assert.equal(d.activeElement.dataset.play,'1');assert.equal(y,170);
 // Page edges remain reachable past the last interactive control.
 Object.defineProperty(d.documentElement,'scrollHeight',{configurable:true,value:2400});
 const nav=w.streamportTVNavigation;
 w.scrollTo(0,300);for(let i=0;i<8;i++)nav.boundaryScroll(d.activeElement,'up');assert.equal(y,0,'reach absolute top');
 for(let i=0;i<10;i++)nav.boundaryScroll(d.activeElement,'down');assert.equal(y,2400-w.innerHeight,'reach absolute bottom');
 // Cast has its own focus stops, including horizontal navigation.
 const cast=d.createElement('section');cast.innerHTML='<h2>Cast & characters</h2><div class="people-row"><div class="person">Actor One</div><div class="person">Actor Two</div></div>';d.querySelector('#content').append(cast);nav.decorate();
 const people=[...cast.querySelectorAll('.person')];people.forEach((p,i)=>{assert.equal(p.tabIndex,0);p.dataset.rect=`${200+i*150},650,125,210`;});
 assert.equal(nav.nextInDirection(people,people[0],'right'),people[1]);
 // Native smooth scrolling receives one command, not per-frame JS writes.
 w.matchMedia=()=>({matches:false});w.scrollTo(0,0);nav.animateScroll(w,'y',800);assert.equal(lastScroll.behavior,'smooth');assert.equal(y,800);
 const commandCount=scrolls;nav.animateScroll(w,'y',800);await tick();assert.equal(scrolls,commandCount,'same target does not restart animation');
 nav.animateScroll(w,'y',0);assert.equal(y,0);assert.equal(lastScroll.behavior,'smooth');nav.stopMotion();w.matchMedia=()=>({matches:true});cast.remove();
 // Navigation reads each rectangle once, even in a large library.
 const many=Array.from({length:400},(_,i)=>{const el=d.createElement('button');el.dataset.rect=`${i%8*150},${Math.floor(i/8)*200},125,170`;return el;});
 let reads=0;many.forEach(el=>{const original=el.getBoundingClientRect.bind(el);el.getBoundingClientRect=()=>{reads++;return original();};});
 assert.equal(nav.nextInDirection(many,many[120],'down'),many[128]);assert.equal(reads,400);
 // Search is readonly on navigation; keyboard starts only on OK.
 const input=d.querySelector('#search');input.dataset.rect='200,30,500,42';input.focus();assert(input.readOnly);
 w.streamportTVKey('ok');assert(!input.readOnly);assert(w.streamportTVBack());assert(input.readOnly);
 // A select uses a trapped, readable list instead of cycling on OK.
 const select=d.querySelector('#subtitle-track');select.dataset.rect='700,100,150,44';select.innerHTML='<option value="">Off</option><option value="sr">Srpski</option>';
 d.querySelector('#player').open=true;d.querySelector('[aria-label=Subtitles]').click();select.focus();
 w.streamportTVKey('ok');const choice=d.querySelector('.tv-choice');assert(choice?.open);assert.equal(choice.querySelectorAll('button').length,2);
 run('setSubtitle=async()=>{}');choice.querySelector('[data-value="sr"]').click();assert.equal(select.value,'sr');assert(!d.querySelector('.tv-choice'));
 // No stale mobile focus geometry: fixed poster/card dimensions and centered player controls.
 assert(!fs.readFileSync(path.join(assets,'tv.css'),'utf8').match(/:focus\s*\{[^}]*position\s*:/));
 await tick();observers.forEach(o=>o.disconnect());dom.window.close();console.log('PASS: Back→Play, row navigation, no idle jumps, refresh restoration, explicit keyboard editing, subtitle choice dialog, page edges, cast focus, native smooth scroll, one geometry read per card.');
})().catch(e=>{console.error(e);process.exit(1)});
