/* Installed after the existing player adapter. No server writes. */
(()=>{
 if(window.streamportPhoneCompat)return true;window.streamportPhoneCompat=true;
 document.documentElement.classList.add('modern','streamport-phone');
 const apply=()=>{const side=document.getElementById('modern-sidebar');if(side){side.hidden=true;side.setAttribute('aria-hidden','true');side.inert=true;}};
 apply();
 const previous=render;render=async function(...args){const result=await previous.apply(this,args);apply();return result;};
 return true;
})();
