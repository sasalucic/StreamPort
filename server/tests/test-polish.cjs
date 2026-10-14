const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom');
(async()=>{
 const base=path.resolve(__dirname,'../static');
 const dom=new JSDOM(fs.readFileSync(base+'/index.html','utf8').replace(/<script[\s\S]*?<\/script>/g,''),{url:'http://server/',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,d=w.document,ctx=dom.getInternalVMContext(),run=s=>vm.runInContext(s,ctx);let poll;
 w.setInterval=fn=>{poll=fn;return 1;};w.scrollTo=()=>{};
 const fixture=[{id:1,title:'Test',series:'',kind:'movie',duration:3600,added:1}];
 w.fetch=async()=>({ok:true,json:async()=>JSON.parse(JSON.stringify(fixture))});
 for(const file of ['app.js','enhancements.js','search.js','features.js','polish.js'])run(fs.readFileSync(base+'/'+file,'utf8').replace(/boot\(\);\s*$/,''));
 run(`me={id:1,name:'Admin',admin:1};library=${JSON.stringify(fixture)};shell();page='movies';`);await run('render()');
 const original=d.querySelector('#content').firstElementChild;await poll();assert.equal(d.querySelector('#content').firstElementChild,original,'identical data must not redraw');
 fixture[0].title='Changed';d.dispatchEvent(new w.Event('scroll'));await poll();assert.equal(d.querySelector('#content').firstElementChild,original,'refresh waits for scroll to settle');
 await new Promise(r=>setTimeout(r,550));assert(d.querySelector('#content').textContent.includes('Changed'));
 d.querySelector('#content').innerHTML+='<img src="poster.jpg">';await run('render()');
 assert(w.streamportPolishInstalled);
 const css=fs.readFileSync(base+'/polish.css','utf8');assert(css.includes('html:not(.streamport-tv)'));assert(css.includes('scroll-snap-type:none'));assert(css.includes('prefers-reduced-motion'));
 dom.window.close();console.log('PASS: unchanged polling preserves DOM, changed polling waits for scrolling, shared polish stays outside TV layout.');
})().catch(e=>{console.error(e);process.exit(1)});
