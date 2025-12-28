
/* static/app.js */

// ---------- Helpers ----------
function token(){ return localStorage.getItem('fftech_token') || ''; }
function showLogin(){ document.getElementById('loginCard').classList.remove('hidden'); }
function logout(){ localStorage.removeItem('fftech_token'); toast('Logged out', 'success'); }

function toast(msg, type='success'){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.remove('hidden','toast-success','toast-error');
  t.classList.add(type === 'success' ? 'toast-success' : 'toast-error');
  setTimeout(()=> t.classList.add('hidden'), 3500);
}

function toggleTheme(){
  // Optional: dark/light toggle via data attribute
  toast('Theme toggled');
}

// ---------- Chart.js defaults ----------
Chart.defaults.color = '#e2e8f0';
Chart.defaults.font.family = "'Inter', system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#0b1220';
Chart.defaults.plugins.tooltip.borderColor = '#334155';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.animation.duration = 600;

// Rounded bars plugin
const roundedBars = {
  id: 'roundedBars',
  afterDatasetsDraw(chart) {
    const {ctx, chartArea:{top, bottom}} = chart;
    chart.getDatasetMeta(0).data.forEach(bar => {
      ctx.save();
      ctx.lineJoin = 'round';
      ctx.lineWidth = 8;
      ctx.strokeStyle = '#2E86C1';
      ctx.beginPath();
      ctx.moveTo(bar.x, bottom);
      ctx.lineTo(bar.x, bar.y);
      ctx.stroke();
      ctx.restore();
    });
  }
};

// Doughnut chart factory
function chartDonut(el, val){
  return new Chart(el, {
    type: 'doughnut',
    data: {
      labels: ['Score','Remaining'],
      datasets: [{ data: [val, 100-val], backgroundColor: ['#16a34a','#334155'], borderWidth: 0 }]
    },
    options: { cutout: '70%', plugins: { legend: { display: false } } }
  });
}

// ---------- Render functions ----------
let catChart;

function render(d){
  // Summary
  document.getElementById('summary').textContent = d.metrics[3].value;

  // Score & Grade badges
  document.getElementById('scoreGrade').innerHTML =
    `<span class="badge">Score: ${d.score}%</span><span class="badge">Grade: ${d.grade}</span>`;

  // Progress
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
  const ctx = document.getElementById('catChart').getContext('2d');
  if (catChart) catChart.destroy();
  catChart = new Chart(ctx, {
    type:'bar',
    data:{ labels, datasets:[{ data: values, backgroundColor:'#2E86C1', borderRadius: 6 }] },
    options:{ scales:{ y:{ min:0,max:100, grid:{ color:'#223047'} }, x:{ grid:{ display:false } } }, plugins:{legend:{display:false}} },
    plugins: [roundedBars]
  });

  // Small donuts
  chartDonut(document.getElementById('chartCrawl'), cat['Crawlability']);
  chartDonut(document.getElementById('chartSEO'),   cat['On-Page SEO']);
  chartDonut(document.getElementById('chartPerf'),  cat['Performance']);
  chartDonut(document.getElementById('chartSec'),   cat['Security']);
  chartDonut(document.getElementById('chartMobile'),cat['Mobile']);

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

// ---------- CSV export ----------
function exportMetricsCSV(){
  const rows = Array.from(document.querySelectorAll('#metricsTable tr'))
    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.textContent));
  if (!rows.length){ toast('No metrics to export', 'error'); return; }
  const header = ['ID','Name','Category','Value','Detail'];
  const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `fftech_metrics_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast('Exported metrics CSV');
}

// ---------- API calls (with loaders & toasts) ----------
async function requestLink(e){
  e.preventDefault();
  try{
    const email = document.getElementById('emailInput').value;
    const r = await fetch('/auth/request-link',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})
    });
    const d = await r.json();
    toast(d.message || 'Magic link sent / logged.');
  }catch(err){ toast('Error sending link: '+err, 'error'); }
}

async function requestCode(e){
  e.preventDefault();
  try{
    const email = document.getElementById('emailCode').value;
    const r = await fetch('/auth/request-code',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})
    });
    const d = await r.json();
    toast(d.message || 'Code sent / logged.');
  }catch(err){ toast('Error sending code: '+err, 'error'); }
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
      toast('Logged in via code!', 'success');
    } else {
      toast(d.detail || 'Verification failed', 'error');
    }
  }catch(err){ toast('Error verifying code: '+err, 'error'); }
}

async function runOpenAudit(e){
  e.preventDefault();
  const loader = document.getElementById('loadingOpen'); loader.classList.remove('hidden');
  try{
    const url = document.getElementById('urlOpen').value;
    const r = await fetch('/api/audit/open',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})
    });
    const d = await r.json();
    if (r.ok){ render(d); toast('Open audit complete'); } else { toast(d.detail || 'Audit failed', 'error'); }
  }catch(err){ toast('Error: '+err, 'error'); }
  finally{ loader.classList.add('hidden'); }
}

async function runUserAudit(e){
  e.preventDefault();
  const t = token();
  if (!t){ toast('Please login first.', 'error'); return; }
  const loader = document.getElementById('loadingUser'); loader.classList.remove('hidden');
  try{
    const url = document.getElementById('urlUser').value;
    const r = await fetch('/api/audit/user',{
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+t}, body:JSON.stringify({url})
    });
    const d = await r.json();
    if (r.ok){ render(d); toast('Audit saved. ID: '+d.audit_id); } else { toast(d.detail || 'Audit failed', 'error'); }
  }catch(err){ toast('Error: '+err, 'error'); }
  finally{ loader.classList.add('hidden'); }
}

async function loadHistory(){
  const t = token(); if (!t){ toast('Login required', 'error'); return; }
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
         <td><a href="/api/report/${a.id}.></td>`;
      tbody.appendChild(tr);
    }
    toast('History refreshed');
  }catch(err){ toast('Error loading history: '+err, 'error'); }
}

async function createSchedule(e){
  e.preventDefault();
  const t = token(); if (!t){ toast('Login required', 'error'); return; }
  try{
    const url = document.getElementById('scheduleUrl').value;
    const frequency = document.getElementById('scheduleFreq').value;
    const r = await fetch('/schedule',{
      method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+t}, body:JSON.stringify({url,frequency})
    });
    const d = await r.json();
    if (r.ok){ toast('Scheduled: '+d.schedule_id, 'success'); } else { toast(d.detail || 'Failed', 'error'); }
  }catch(err){ toast('Error scheduling: '+err, 'error'); }
}

async function listSchedules(){
  const t = token(); if (!t){ toast('Login required', 'error'); return; }
  try{
    const r = await fetch('/schedule',{ headers:{'Authorization':'Bearer '+t} });
    const d = await r.json();
    const ul = document.getElementById('schedules'); ul.innerHTML='';
    document.getElementById('schedulesCount').textContent = `${d.length} scheduled`;
    for (const s of d){
      const li = document.createElement('li');
      li.className = 'flex items-center justify-between bg-slate-800 rounded-md px-3 py-2 border border-slate-700';
      li.innerHTML = `<span>#${s.id} ${s.url} (${s.frequency})</span><span class="muted">next: ${s.next_run_at}</span>`;
      ul.appendChild(li);
    }
    toast('Schedules loaded');
  }catch(err){ toast('Error loading schedules: '+err, 'error'); }
}

// ---------- Magic-link auto verify ----------
(function(){
  const params = new URLSearchParams(location.search);
  const tok = params.get('token');
  if (tok){
    fetch('/auth/verify-link',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token: tok})
    })
      .then(r=>r.json())
      .then(d=>{
        if (d.token){
          localStorage.setItem('fftech_token', d.token);
          toast('Logged in via magic link!');
          history.replaceState({},'',location.pathname);
        } else {
          toast('Magic link failed', 'error');
        }
      })
      .catch(err => toast('Magic link error: '+err, 'error'));
  }
})();
