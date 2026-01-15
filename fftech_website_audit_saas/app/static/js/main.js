
const html = document.documentElement;
const themeToggle = document.getElementById('themeToggle');
if(themeToggle){
  const stored = localStorage.getItem('theme') || 'light';
  html.setAttribute('data-bs-theme', stored);
  themeToggle.addEventListener('click', ()=>{
    const curr = html.getAttribute('data-bs-theme')==='light'?'dark':'light';
    html.setAttribute('data-bs-theme', curr);
    localStorage.setItem('theme', curr);
  });
}

async function postJSON(url, body){
  const res = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!res.ok){ throw new Error((await res.json()).detail || 'Request failed'); }
  return await res.json();
}

const form=document.getElementById('auditForm');
if(form){
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const url = document.getElementById('url').value.trim();
    const comps = document.getElementById('competitors').value.split(',').map(s=>s.trim()).filter(Boolean);
    try{
      const data = await postJSON('/api/audit',{url, competitors: comps.length?comps:undefined});
      document.getElementById('result').classList.remove('d-none');
      document.getElementById('overallScore').innerText = data.overall_score+'%';
      document.getElementById('overallBar').style.width = data.overall_score+'%';
      document.getElementById('grade').innerText = data.grade;
      // category chart
      const labels = Object.keys(data.category_scores);
      const values = Object.values(data.category_scores);
      if(window._catChart){window._catChart.destroy();}
      window._catChart = new Chart(document.getElementById('categoriesChart'),{
        type:'bar',data:{labels,datasets:[{label:'Score',data:values,backgroundColor:'#0ea5e9'}]},options:{scales:{y:{min:0,max:100}}}
      });
      // status chart
      const status = {
        '2xx': data.metrics.http_2xx||0,
        '3xx': data.metrics.http_3xx||0,
        '4xx': data.metrics.http_4xx||0,
        '5xx': data.metrics.http_5xx||0,
      };
      if(window._statusChart){window._statusChart.destroy();}
      window._statusChart = new Chart(document.getElementById('statusChart'),{
        type:'doughnut', data:{labels:Object.keys(status), datasets:[{data:Object.values(status), backgroundColor:['#22c55e','#06b6d4','#f59e0b','#ef4444']}]} , options:{plugins:{legend:{position:'bottom'}}}
      });
      // issues list
      const issues = [
        `Missing Titles: ${data.metrics.missing_title||0}`,
        `Missing Meta Descriptions: ${data.metrics.missing_meta_desc||0}`,
        `Missing H1: ${data.metrics.missing_h1||0}`,
      ];
      const ul=document.getElementById('issuesList');
      ul.innerHTML='';
      issues.forEach(t=>{const li=document.createElement('li'); li.textContent=t; ul.appendChild(li);});
    }catch(err){
      alert(err.message);
    }
  });
}

const signinBtn=document.getElementById('signinBtn');
if(signinBtn){
  signinBtn.addEventListener('click', async ()=>{
    const email = prompt('Enter your email to receive a sign-in link:');
    if(!email) return;
    try{ await postJSON('/api/auth/request-link',{email}); alert('Link sent. Check your inbox.'); }
    catch(err){ alert(err.message); }
  });
}
