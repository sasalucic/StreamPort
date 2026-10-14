// CSS cascade regression for the device-reported focus/overlay defects.
const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom'),fs=require('fs'),path=require('path'),assert=require('assert');
const assets=path.resolve(__dirname,'../app/src/main/assets'),server=path.resolve(__dirname,'../../StreamPort/static');
const dom=new JSDOM('<html class="streamport-tv"><head></head><body><main class="main"><div class="rail"><div class="grid"><div class="media-tile"><button class="card"><div class="poster"></div><h3>Long movie title</h3></button><button class="favorite-overlay">♡</button></div></div></div></main><dialog id="player" class="android-player"><button class="sp-icon" aria-label="Lock controls"></button><button class="sp-icon" aria-label="Rotate screen"></button><button class="sp-icon" aria-label="Subtitles"></button></dialog></body></html>',{pretendToBeVisual:true});
const d=dom.window.document;
for(const file of [path.join(server,'style.css'),path.join(server,'features.css'),path.join(assets,'mobile.css'),path.join(assets,'tv.css')]){const style=d.createElement('style');style.textContent=fs.readFileSync(file,'utf8');d.head.append(style);}
const css=el=>dom.window.getComputedStyle(el),heart=d.querySelector('.favorite-overlay');assert.equal(css(heart).display,'none');const before=css(heart).position;heart.focus();assert.equal(css(heart).position,before,'focus must not change absolute positioning');assert.equal(css(heart).display,'none');
for(const label of ['Lock controls','Rotate screen'])assert.equal(css(d.querySelector(`[aria-label="${label}"]`)).display,'none');assert.notEqual(css(d.querySelector('[aria-label=Subtitles]')).display,'none');
const card=d.querySelector('.card');card.focus();assert.equal(css(card).transform,'none');assert(css(d.querySelector('.poster')).outline.includes('#ccff00'));
assert(!fs.readFileSync(path.join(assets,'tv.css'),'utf8').match(/:focus\s*\{[^}]*position\s*:/));
dom.window.close();console.log('PASS: real CSS cascade keeps favorite action hidden and fixed, removes TV lock/rotate icons, prevents focus scaling and highlights the poster.');
