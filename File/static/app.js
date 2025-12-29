function toggleTheme(){
  const body=document.body; const dark=body.classList.contains('theme-dark');
  body.classList.toggle('theme-dark', !dark); body.classList.toggle('theme-light', dark);
  localStorage.setItem('fftech_theme', dark?'light':'dark');
}
(function initTheme(){
  const saved=localStorage.getItem('fftech_theme')||'dark';
  document.body.classList.add(saved==='dark'?'theme-dark':'theme-light');
})();
function logout(){ localStorage.removeItem('fftech_token'); alert('Logged out'); }
if (window.Chart) {
  const color=getComputedStyle(document.body).getPropertyValue('--text').trim()||'#e2e8f0';
  Chart.defaults.color=color;
  Chart.defaults.font.family="'Inter', system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
  Chart.defaults.plugins.legend.display=false;
}
