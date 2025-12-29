
// Theme toggle
function toggleTheme() {
  const body = document.body;
  const isDark = body.classList.contains('theme-dark');
  body.classList.toggle('theme-dark', !isDark);
  body.classList.toggle('theme-light', isDark);
  localStorage.setItem('fftech_theme', isDark ? 'light' : 'dark');
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
  const color = getComputedStyle(document.body).getPropertyValue('--text').trim() || '#e2e8f0';
  Chart.defaults.color = color;
  Chart.defaults.font.family = "'Inter', system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
  Chart.defaults.plugins.legend.display = false;
}
