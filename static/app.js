
(function initTheme(){
  const saved = localStorage.getItem('fftech_theme');
  const theme = saved || 'dark';
  document.body.setAttribute('data-theme', theme);
})();
function toggleTheme(){
  const cur = document.body.getAttribute('data-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.body.setAttribute('data-theme', next);
  localStorage.setItem('fftech_theme', next);
}
function logout(){ localStorage.removeItem('fftech_token'); alert('Logged out'); }
