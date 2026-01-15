
(function(){
  const toggle = document.getElementById('themeToggle');
  const html = document.documentElement;
  function setTheme(mode){
    html.setAttribute('data-bs-theme', mode);
    localStorage.setItem('theme', mode);
  }
  const saved = localStorage.getItem('theme') || 'light';
  setTheme(saved);
  toggle.addEventListener('click', ()=>{
    const next = html.getAttribute('data-bs-theme') === 'light' ? 'dark' : 'light';
    setTheme(next);
  });
})();
