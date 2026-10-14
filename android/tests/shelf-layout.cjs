const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom'),fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'../..');
for(const modern of [false,true]){
const card='<button class="card"><div class="poster"><img></div><h3>A long movie title</h3><p>2025 · 120 min</p></button>';
const markup=modern?`<div class="media-tile">${card}<button class="favorite-overlay">♡</button></div>`:card;
const dom=new JSDOM(`<body><main class="main"><div class="rail"><div class="grid">${markup.repeat(24)}</div></div></main></body>`),d=dom.window.document;
for(const f of ['StreamPort/static/style.css','StreamPort/static/features.css','StreamPort-Android/app/src/main/assets/mobile.css']){const el=d.createElement('style');el.textContent=fs.readFileSync(path.join(root,f),'utf8');d.head.append(el);}
const css=el=>dom.window.getComputedStyle(el),grid=d.querySelector('.rail>.grid'),item=grid.firstElementChild;
assert.equal(css(grid).display,'flex');assert.equal(css(grid).flexWrap,'nowrap');assert.equal(css(item).flexShrink,'0');assert.equal(css(item).minWidth,'78vw');assert.equal(css(d.querySelector('.rail')).overflowX,'auto');
if(modern)assert.equal(css(item.querySelector('.card')).width,'100%');
dom.window.close();}
console.log('PASS: 24-card shelves remain non-shrinking horizontal rows with both old and wrapped server markup.');
