
(function initThemeFromCookie(){ const theme=document.cookie.split('; ').find(r=>r.startsWith('theme='))?.split('=')[1]; applyTheme(theme||'dark'); })();
function applyTheme(theme){ document.body.classList.remove('theme-light','theme-dark'); document.body.classList.add(theme==='light'?'theme-light':'theme-dark'); }
async function toggleTheme(){ try{ const res=await fetch('/theme/toggle',{method:'POST'}); const data=await res.json(); if(data?.theme) applyTheme(data.theme);}catch(e){console.error('Theme toggle failed',e);} }
async function logout(){ try{ const res=await fetch('/logout',{method:'POST'}); if(res.ok){ localStorage.removeItem('fftech_token'); window.location.href='/'; } }catch(e){ console.error('Logout failed',e);} }
