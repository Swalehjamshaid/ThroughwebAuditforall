
// Open access audit
const openForm = document.getElementById('openAuditForm');
if(openForm){ openForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const url = document.getElementById('url_open').value.trim();
  const res = await fetch('/api/audit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url})});
  const data = await res.json();
  document.getElementById('openResult').classList.remove('d-none');
  document.getElementById('openOverall').innerText = data.overall_score+'%';
  document.getElementById('openBar').style.width = data.overall_score+'%';
  const ctx = document.getElementById('openChart');
  const labels = Object.keys(data.category_scores), values = Object.values(data.category_scores);
  if(window._openChart) window._openChart.destroy();
  window._openChart = new Chart(ctx, {type:'bar', data:{labels, datasets:[{label:'Category', data: values, backgroundColor:'#0ea5e9'}]}, options:{scales:{y:{min:0,max:100}}}});
}); }

// Registered audit
const regForm = document.getElementById('regAuditForm');
if(regForm){ regForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const url = document.getElementById('url_reg').value.trim();
  const res = await fetch('/api/audit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url})});
  const data = await res.json();
  document.getElementById('regResult').classList.remove('d-none');
  document.getElementById('regOverall').innerText = data.overall_score+'%';
  document.getElementById('regBar').style.width = data.overall_score+'%';
  const ctx = document.getElementById('regChart');
  const labels = Object.keys(data.category_scores), values = Object.values(data.category_scores);
  if(window._regChart) window._regChart.destroy();
  window._regChart = new Chart(ctx, {type:'bar', data:{labels, datasets:[{label:'Category', data: values, backgroundColor:'#22c55e'}]}, options:{scales:{y:{min:0,max:100}}}});
}); }

// Magic link request (login/register)
const loginForm = document.getElementById('loginForm') || document.getElementById('registerForm');
if(loginForm){ loginForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const email = (document.getElementById('email_login')||document.getElementById('email_register')).value.trim();
  const res = await fetch('/auth/request-link', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email})});
  if(res.ok){ window.location='/verify'; }
}); }
