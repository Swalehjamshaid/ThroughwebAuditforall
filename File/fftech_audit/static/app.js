
function toggleTheme(){
  const isLight = document.body.classList.toggle('light');
  document.cookie = 'theme='+(isLight?'light':'dark')+'; Max-Age='+(60*60*24*180)+'; Path=/; SameSite=Lax';
}
