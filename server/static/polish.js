/* Shared web and touch polish; never intercepts touch/wheel or TV keys. */
(()=>{
 if(window.streamportPolishInstalled)return true;window.streamportPolishInstalled=true;
 const decodeImages=()=>document.querySelectorAll('#content img:not([decoding])').forEach(img=>{img.decoding='async';});
 const original=render;render=async function(...args){const result=await original.apply(this,args);decodeImages();return result;};
 decodeImages();return true;
})();
