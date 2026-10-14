// UI state/HTML tests with DOM stubs; not a browser rendering test.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const nodes=new Map();let tracks=[];
function node(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',value:'',style:{},dataset:{},selectedOptions:[{textContent:'sr subtitles',dataset:{key:'2.sr.77.vtt'}}],textTracks:[],classList:{toggle(){}},append(el){if(el.kind==='subtitles'){tracks.push(el);el.onload()}},prepend(){},after(){},querySelectorAll(){return []},showModal(){this.open=true},close(){this.open=false},pause(){},load(){}});return nodes.get(key)}
const ctx={window:{},document:{body:node('body'),querySelector:node,querySelectorAll:()=>[],addEventListener(){},createElement(tag){if(tag==='track')return {track:{mode:'disabled',cues:[{startTime:5,endTime:10}],removeCue(){}},remove(){}};return node('created-'+tag)}},setInterval(){},setTimeout(){return 1},clearTimeout(){},console,URLSearchParams,fetch(){throw Error('Unexpected network')}};
vm.createContext(ctx);
for(const f of ['app.js','enhancements.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',f),'utf8').replace(/boot\(\);\s*$/,''),ctx);
(async()=>{
vm.runInContext(`library=[{id:2,title:'Film',kind:'movie',year:'2020',poster:'',backdrop:'https://image.tmdb.org/t/p/w1280/x.jpg',overview:'Description',duration:90,size:99,position:0,genres:'Drama',collection_id:'5',collection_name:'Saga',added:1}];me={admin:1,name:'Admin'};page='home';`,ctx);
await vm.runInContext('render()',ctx);assert(node('#content').innerHTML.includes('cinema-hero'));assert(node('#content').innerHTML.includes('Movies for tonight'));
vm.runInContext("page='collections'",ctx);await vm.runInContext('render()',ctx);assert(node('#content').innerHTML.includes('Saga'));
vm.runInContext("api=async()=>[{index:0,key:'2.en.11.vtt',label:'English'},{index:1,key:'2.sr.77.vtt',label:'Srpski'}];current=library[0];offset=2;",ctx);
await vm.runInContext("loadSubs('2.sr.77.vtt')",ctx);assert.equal(node('#subtitle-track').value,'1');assert.equal(tracks[0].track.mode,'showing');assert.equal(tracks[0].track.cues[0].startTime,3);assert(node('#subtitle-status').textContent.includes('enabled'));
node('#player').open=true;vm.runInContext("toast('Download failed: quota')",ctx);assert.equal(node('#subtitle-status').textContent,'Download failed: quota');
console.log('v0.3 UI state tests passed: cinema home, collections, exact subtitle selection, track mode, cue offset and in-player errors.');
})().catch(e=>{console.error(e);process.exit(1)});
