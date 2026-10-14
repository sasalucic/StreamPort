// Integration of the real HTML, all web scripts, and DOM events (no browser rendering).
const vm=require('vm');
const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom'),fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const base=path.resolve(__dirname,'../static');
 const html=fs.readFileSync(path.join(base,'index.html'),'utf8').replace(/<script[\s\S]*?<\/script>/g,'');
 const dom=new JSDOM(html,{url:'http://server:8097/',runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window,d=w.document;
 const evaluate=code=>vm.runInContext(code,dom.getInternalVMContext());
 w.scrollTo=()=>{};w.setInterval=()=>0;w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 const calls=[];w.fetch=async(url,init)=>{calls.push([url,init]);return {ok:true,json:async()=>url.endsWith('/probe')?{streams:[]}:[]};};
 for(const f of ['app.js','enhancements.js','search.js','features.js'])evaluate(fs.readFileSync(path.join(base,f),'utf8').replace(/boot\(\);\s*$/,''));
 evaluate(`me={id:1,name:'Admin',admin:1};library=[{id:1,title:'Zulu',kind:'movie',series:'',year:'2020',duration:3600,rating:'8',favorite:0,added:1},{id:2,title:'Alpha',kind:'movie',series:'',year:'2023',duration:7200,rating:'',favorite:1,added:2},{id:3,title:'Episode',series:'A show',kind:'episode',show_key:'show',season:1,episode:1,added:3}];shell();page='movies';`);
 await evaluate('render()');assert(d.querySelector('[data-page=favorites]'));assert(d.querySelector('[data-page=account]'));assert(d.querySelector('#sort-control'));assert.equal(d.querySelector('.card').dataset.detail,'2');assert.equal(d.querySelectorAll('.favorite-overlay').length,2);assert.equal(d.querySelectorAll('button button').length,0);
 d.querySelector('#sort-control').click();assert.equal(d.querySelectorAll('[data-sort]').length,10);d.querySelector('[data-sort=rating]').click();await new Promise(r=>setTimeout(r,0));assert.equal(d.querySelector('.card').dataset.detail,'1');
 d.querySelector('#sort-control').click();d.querySelector('[data-direction=down]').click();await new Promise(r=>setTimeout(r,0));assert.equal(d.querySelector('.card').dataset.detail,'1','missing ratings stay last descending');
 const order=items=>Array.from(items,m=>m.id);w.streamportLibrarySort.set('random');let a=order(w.streamportLibrarySort.sorted([{id:1},{id:2},{id:3}]));assert.deepEqual(a,order(w.streamportLibrarySort.sorted([{id:3},{id:2},{id:1}])),'random stable between renders');
 evaluate("page='favorites'");await evaluate('render()');assert.equal(d.querySelectorAll('.card').length,1);assert.equal(d.querySelector('.card').dataset.detail,'2');
 evaluate("search='Zulu';page='home'");await evaluate('render()');assert.equal(d.querySelectorAll('.card').length,1);assert(!d.querySelector('.cinema-hero'));assert(!d.querySelector('.shelf'));
 evaluate("search='';page='movies';detailId=1");await evaluate('render()');assert(d.querySelector('#delete-media'));assert(d.querySelector('#media-actions [data-favorite]'));
 evaluate("me.admin=0");await evaluate('render()');assert(!d.querySelector('#delete-media'));assert(!d.querySelector('.folder-location'));
 evaluate("page='account';detailId=null");await evaluate('render()');assert(d.querySelector('#password-form'));assert(!d.querySelector('#password-users'));
 evaluate("me.admin=1;api=async(url,body)=>url==='/api/users'?[{id:1,name:'Admin',admin:1},{id:2,name:'User',admin:0}]:{ok:true};");await evaluate('render()');assert.equal(d.querySelectorAll('[data-reset]').length,2);d.querySelector('[data-reset="2"]').click();assert(d.querySelector('#feature-dialog [name=current_password]'));
 const form=d.querySelector('#feature-dialog form');form.querySelector('[name=current_password]').value='admin-password';form.querySelector('[name=new_password]').value='new-password-123';form.querySelector('[name=repeat]').value='mismatch-pass';form.dispatchEvent(new w.Event('submit',{cancelable:true}));assert(form.querySelector('[role=status]').textContent.includes('do not match'));
 d.querySelector('[data-dismiss]').click();evaluate("page='shows';filter='show';");await evaluate('render()');assert.equal(d.querySelector('#delete-media').textContent,'Delete entire series');
 evaluate(`api=async(url,body)=>url.endsWith('delete-preview')?{token:'token',title:'A show',count:1,bytes:1024,files:['/media/tv/a.mp4']}:url==='/api/library'?[]:{ok:true,deleted:[3],failed:[]};`);d.querySelector('#delete-media').click();await new Promise(r=>setTimeout(r,0));assert(d.querySelector('.delete-files').textContent.includes('/media/tv/a.mp4'));assert(d.querySelector('[name=password]'));assert.equal(d.querySelectorAll('#feature-dialog [type=submit]').length,1);
 dom.window.close();console.log('PASS: real DOM navigation, favorites, accessible sibling buttons, 10 sort modes, missing-last, stable random, deduplicated search, role visibility, password forms, series delete preview.');
})().catch(e=>{console.error(e);process.exit(1)});
