
function setLocalTZ(){
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const tzInput = document.getElementById('timezone');
  if(tzInput){ tzInput.value = tz; }
}

document.addEventListener('DOMContentLoaded', ()=>{
  setLocalTZ();
});
