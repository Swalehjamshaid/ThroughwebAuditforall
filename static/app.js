
/* static/app.js */

// ---- Helpers ----
function token(){ return localStorage.getItem('fftech_token') || ''; }
function showLogin(){ window.scrollTo({top:0, behavior:'smooth'}); }
function logout(){ localStorage.removeItem('fftech_token'); console.log('Logged out'); }

const overlay = {
  show(){ document.getElementById('overlay').classList.remove('hidden'); },
  hide(){ document.getElementById('overlay').classList.add('hidden'); }
};

// ---- Chart.js theme ----
Chart.defaults.color = '#e2e8f0';
Chart.defaults.font.family = "'Inter', system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#0b1220';
Chart.defaults.plugins.tooltip.borderColor = '#334155';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.animation.duration = 650;

function donut(el, val){
  return new Chart(el, {
    type: 'doughnut',
    data: { labels: ['Score','Remaining'], datasets: [{ data:[val,100-val], backgroundColor:['#16a34a','#334155'], borderWidth:0 }] },
    options: { cutout: '70%' }
  });
}

let catChart;
function renderResults(d){
  // Reveal results section
  document.getElementById('results').classList.remove('hidden');

  // Summary
  document.getElementById('summary').textContent = d.metrics[3].value;

  // Score & grade
  document.getElementById('scoreGrade').innerHTML =
    `<span class="badge">Score: ${d.score}%</span>
     <span class="badge">Grade: ${d.grade}</span>`;
  document.getElementById('scoreBar').style.width = d.score + '%';

  // Severity
  const sev = d.metrics[7].value;
  document.getElementById('severity').innerHTML =
    `<span class="badge">Errors: ${sev.errors}</span>
     <span class="badge">Warnings: ${sev.warnings}</span>
     <span class="badge">Notices: ${sev.notices}</span>`;

  // Category bar
  const cat = d.metrics[8].value;
  const labels = Object.keys(cat);
  const values = Object.values(cat);
  if (catChart) catChart.destroy();
  catChart = new Chart(document.getElementById('catChart'), {
    type:'bar',
    data:{ labels, datasets:[{ data: values, backgroundColor:'#2E86C1', borderRadius:6 }] },
    options:{ scales:{ y:{ min:0, max:100, grid:{ color:'#223047'} }, x:{ grid:{ display:false } } } }
  });

  // Small donuts
  donut(document.getElementById('chartCrawl'), cat['Crawlability']);
  donut(document.getElementById('chartSEO'),   cat['On-Page SEO']);
  donut(document.getElementById('chartPerf'),  cat['Performance']);
  donut(document.getElementById('chartSec'),   cat['Security']);
  donut(document.getElementById('chartMobile'),cat['Mobile']);

  // Metrics table
  const tbody = document.getElementById('metricsTable');
  tbody.innerHTML = '';
  const entries = Object.entries(d.metrics).sort((a,b)=>parseInt(a[0])-parseInt(b[0]));
  fetch('/api/metrics/descriptors')
    .then(r=>r.json())
    .then(DESCRIPTORS=>{
      for (const [id,obj] of entries){
        const desc = DESCRIPTORS[id] || {name:'(Unknown)', category:'-'};
        const tr = document.createElement('tr');
        tr.innerHTML =
          `<td>${id}</td>
           <td>${desc.name}</td>
           <td>${desc.category}</td>
           <td>${(typeof obj.value==='object')? JSON.stringify(obj.value): obj.value}</td>
           <td>${obj.detail || ''}</td>`;
        tbody.appendChild(tr);
      }
    });
}

// ---- CSV Export ----
function exportMetricsCSV(){
  const rows = Array.from(document.querySelectorAll('#metricsTable tr'))
    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.textContent));
  if (!rows.length){ console.log('No metrics to export'); return; }
  const header = ['ID','Name','Category','Value','Detail'];
  const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `fftech_metrics_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---- Open audit (with full-screen waiting indicator) ----
async function runOpenAudit(e){
  e.preventDefault();
  const btn = document.getElementById('btnOpen');
  const url = document.getElementById('urlOpen').value;

  overlay.show();
  btn.disabled = true;

  try{
    const r = await fetch('/api/audit/open',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url})
    });
    const d = await r.json();
    if (r.ok){
      renderResults(d);
      console.log('Open audit complete');
    } else {
      alert(d.detail || 'Audit failed');
    }
  }catch(err){
    alert('Error: '+err);
  } finally {
    overlay.hide();
    btn.disabled = false;
  }
}

// ---- Login flows ----
async function requestLink(e){
  e.preventDefault();
  try{
    const email = document.getElementById('emailInput').value;
    const r = await fetch('/auth/request-link',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})
    });
    const d = await r.json();
    alert(d.message || 'Magic link sent / logged.');
  }catch(err){ alert('Error sending link: '+err); }
}

async function requestCode(e){
  e.preventDefault();
  try{
    const email = document.getElementById('emailCode').value;
    const r = await fetch('/auth/request-code',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})
    });
    const d = await r.json();
    alert(d.message || 'Code sent / logged.');
  }catch(err){ alert('Error sending code: '+err); }
}

async function verifyCode(e){
  e.preventDefault();
  try{
    const email = document.getElementById('emailCode').value;
    const code  = document.getElementById('codeInput').value;
    const r = await fetch('/auth/verify-code',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email,code})
    });
    const d = await r.json();
    if (r.ok){
      localStorage.setItem('fftech_token', d.token);
      alert('Logged in via code');
    } else {
      alert(d.detail || 'Verification failed');
    }
  }catch(err){ alert('Error verifying code: '+err); }
}

// ---- History (for logged-in users) ----
async function loadHistory(){
  const t = token(); if (!t){ alert('Login required'); return; }
  try{
    const r = await fetch('/api/audits',{ headers:{'Authorization':'Bearer '+t} });
    const d = await r.json();
    const tbody = document.getElementById('historyTable');
    tbody.innerHTML = '';
    for (const a of d){
      const tr = document.createElement('tr');
      tr.innerHTML =
        `<td>${a.id}</td>
         <td>${a.url}</td>
         <td>${a.score}</td>
         <td>${a.grade}</td>
         <td>${a.created_at}</td>
         <td>/api/report/${a.id}.pdfPDF</a></td>`;
      tbody.appendChild(tr);
    }
    document.getElementById('results').classList.remove('hidden');
  }catch(err){ alert('Error loading history: '+err); }
}

// ---- Magic-link auto verify on redirect ----
(function(){
  const params = new URLSearchParams(location.search);
  const tok = params.get('token');
  if (tok){
    fetch('/auth/verify-link',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token: tok})
    })
      .then(r=>r.json()).then(d=>{
        if(d.token){
          localStorage.setItem('fftech_token', d.token);
          alert('Logged in via magic link');
          history.replaceState({},'',location.pathname);
        } else {
          alert('Magic link failed');
        }
      })
      .catch(err => alert('Magic link error: '+err));
  }
})();
