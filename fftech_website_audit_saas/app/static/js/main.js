
const html = document.documentElement;
const toggle = document.getElementById('themeToggle');
if(toggle){
  const stored = localStorage.getItem('theme')||'light';
  html.setAttribute('data-bs-theme', stored);
  toggle.addEventListener('click',()=>{ const v=html.getAttribute('data-bs-theme')==='light'?'dark':'light'; html.setAttribute('data-bs-theme',v); localStorage.setItem('theme',v);});
}

const form = document.getElementById('auditForm');
if(form){
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const url = document.getElementById('url').value.trim();
    const res = await fetch('/api/audit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url})});
    const data = await res.json();
    document.getElementById('result').classList.remove('d-none');
    document.getElementById('overallScore').innerText = data.overall_score+'%';
    document.getElementById('overallBar').style.width = data.overall_score+'%';
    document.getElementById('grade').innerText = data.grade;
    const ctx = document.getElementById('categoriesChart');
    const labels = Object.keys(data.category_scores);
    const values = Object.values(data.category_scores);
    if(window._catChart){window._catChart.destroy();}
    window._catChart = new Chart(ctx, {type:'bar', data:{labels, datasets:[{label:'Category Score', data: values, backgroundColor:'#0ea5e9'}]}, options:{scales:{y:{min:0,max:100}}}});
  });
}

const mlForm = document.getElementById('mlForm');
if(mlForm){
  mlForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const email = document.getElementById('email').value.trim();
    if(!email) return;
    await fetch('/api/auth/request-link',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email})});
    alert('Magic link sent (check console log if SMTP not configured).');
  });
}

// Admin page JS
const adminForm = document.getElementById('adminLogin');
if(adminForm){
  adminForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const email = document.getElementById('adminEmail').value.trim();
    const password = document.getElementById('adminPassword').value;
    const res = await fetch('/api/auth/login',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email,password})});
    if(res.ok){
      const stats = await fetch('/api/admin/stats');
      if(stats.ok){
        const data = await stats.json();
        document.getElementById('usersCount').innerText = data.users;
        document.getElementById('auditsCount').innerText = data.audits;
        document.getElementById('statsRow').style.display = '';
      }
    } else {
      alert('Login failed');
    }
  });
}
