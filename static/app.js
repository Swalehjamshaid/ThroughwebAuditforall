
// Theme toggle
function toggleTheme() {
  const body = document.body;
  if (body.classList.contains('theme-dark')) {
    body.classList.remove('theme-dark'); body.classList.add('theme-light');
    localStorage.setItem('fftech_theme', 'light');
  } else {
    body.classList.remove('theme-light'); body.classList.add('theme-dark');
    localStorage.setItem('fftech_theme', 'dark');
  }
}
(function initTheme(){
  const saved = localStorage.getItem('fftech_theme');
  const theme = saved || 'dark';
  document.body.classList.add(theme === 'dark' ? 'theme-dark' : 'theme-light');
})();

// Auth
function logout() {
  localStorage.removeItem('fftech_token');
  alert('Logged out');
}

// Overlay helpers
function overlayShow(){ document.getElementById('overlay')?.classList.remove('hidden'); }
function overlayHide(){ document.getElementById('overlay')?.classList.add('hidden'); }

// Chart defaults tuned for theme
if (window.Chart) {
  const color = getComputedStyle
