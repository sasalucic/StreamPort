const {JSDOM}=require('jsdom'),fs=require('fs'),vm=require('vm'),assert=require('assert');
const dom=new JSDOM('<dialog id="player"><div><label>Subtitles<select id="subtitle-track"><option value="0" data-key="movie.en.srt" data-version="v1">English</option></select></label></div></dialog>',{url:'http://localhost',runScripts:'outside-only'});
const w=dom.window,ctx=dom.getInternalVMContext();
vm.runInContext('const $=s=>document.querySelector(s);let me={id:1,admin:false},current={id:8};',ctx);
vm.runInContext(fs.readFileSync(require('path').join(__dirname,'../static/subtitle-sync.js'),'utf8'),ctx);
const sync=w.StreamPortSubtitleSync;
function track(){return {cues:[{startTime:1,endTime:2},{startTime:5,endTime:6}],removeCue(c){this.cues.splice(this.cues.indexOf(c),1)},addCue(c){this.cues.push(c)}};}
function click(s){w.document.querySelector(s).click()}
let t=track();sync.load(t,sync.context(),2.2);assert.equal(t.cues.length,1);
click('[data-shift="0.5"]');assert.equal(t.cues.length,2);assert(Math.abs(t.cues[0].endTime-.3)<1e-9);
for(let i=0;i<10;i++)click('[data-shift="0.1"]');assert(Math.abs(t.cues[1].startTime-4.3)<1e-9);
click('#sync-reset');assert.equal(t.cues.length,1);assert(Math.abs(t.cues[0].startTime-2.8)<1e-9);
click('[data-shift="-0.5"]');let newTrack=track();sync.load(newTrack,sync.context(),0);assert.equal(newTrack.cues[0].startTime,.5);
vm.runInContext('me={id:2,admin:false}',ctx);sync.load(track(),sync.context(),0);assert.equal(w.document.querySelector('#sync-value').textContent,'0.0 s');
vm.runInContext('me={id:1,admin:true}',ctx);w.document.querySelector('option').dataset.version='v2';sync.load(track(),sync.context(),0);assert.equal(w.document.querySelector('#sync-value').textContent,'0.0 s');assert.equal(w.document.querySelector('#sync-save-area').hidden,false);
sync.clear();assert(w.document.querySelector('#sync-reset').disabled);
console.log('PASS: original timing, negative/positive delay, restoring clipped cues, reset, persistence, user isolation and changed-file reset');setTimeout(()=>dom.window.close(),0);
