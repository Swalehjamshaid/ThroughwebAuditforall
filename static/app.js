
/* static/app.js */

// -------- Theme toggle (persisted) --------
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

// -------- Basic helpers --------
function showLogin(){ alert('Login via magic link/OTP will be added next.'); }
function logout(){ localStorage.removeItem('fftech_token'); alert('Logged out'); }

const overlay = {
  show(){ document.getElementById('overlay').classList.remove('hidden'); },
  hide(){ document.getElementById('overlay').classList.add('hidden'); }
};

// -------- Chart.js defaults --------
Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text').trim() || '#e2e8f0';
Chart.defaults.font.family = "'Inter', system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#0b1220';
Chart.defaults.plugins.tooltip.borderColor = getComputedStyle(document.body).getPropertyValue('--border').trim() || '#334155';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.animation.duration = 650;

// Donut helper
function donut(el, val){
  return new Chart(el, {
    type: 'doughnut',
    data: {
      labels: ['Score','Remaining'],
      datasets: [{ data:[val,100-val], backgroundColor:[
        getComputedStyle(document.body).getPropertyValue('--brand-green').trim() || '#16a34a',
        getComputedStyle(document.body).getPropertyValue('--border').trim() || '#334155'
      ], borderWidth:0 }]
    },
    options: { cutout: '70%' }
  });
}

let currentAudit = null;
let currentDescriptors = null;
let catBarChart = null;

// -------- Open Audit flow --------
async function runOpenAudit(e){
  e.preventDefault();
  overlay.show();
  const btn = document.getElementById('btnOpen'); btn.disabled = true;
  const url = document.getElementById('urlOpen').value;

  try{
    const r = await fetch('/api/audit/open',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})
    });
    const d = await r.json();
    if (!r.ok){ alert(d.detail || 'Audit failed'); return; }

    const descRes = await fetch('/api/metrics/descriptors');
    currentDescriptors = await descRes.json();

    currentAudit = d;
    renderAll(d, currentDescriptors);
  }catch(err){
    alert('Error: '+err);
  }finally{
    overlay.hide();
    btn.disabled = false;
  }
}

function renderAll(d, DESCRIPTORS){
  document.getElementById('results').classList.remove('hidden');

  // Summary
  document.getElementById('summary').textContent = d.metrics[3].value;

  // Score & Grade
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

  // Category bar chart
  const cat = d.metrics[8].value;   // { Crawlability, On-Page SEO, Performance, Security, Mobile }
  const labels = Object.keys(cat);
  const values = Object.values(cat);
  const accentGraph = getComputedStyle(document.body).getPropertyValue('--accent-graph').trim() || '#2E86C1';
  if (catBarChart) catBarChart.destroy();
  catBarChart = new Chart(document.getElementById('catBarChart'), {
    type:'bar',
    data:{ labels, datasets:[{ data: values, backgroundColor: accentGraph, borderRadius:6 }] },
    options:{ scales:{ y:{ min:0, max:100, grid:{ color:'#223047'} }, x:{ grid:{ display:false } } } }
  });

  // Category donuts
  donut(document.getElementById('donutCrawl'),  cat['Crawlability']);
  donut(document.getElementById('donutSEO'),    cat['On-Page SEO']);
  donut(document.getElementById('donutPerf'),   cat['Performance']);
  donut(document.getElementById('donutSec'),    cat['Security']);
  donut(document.getElementById('donutMobile'), cat['Mobile']);

  // Render metrics table
  buildMetricsTable(d, DESCRIPTORS);
  initSortableHeaders(); // attach click handlers once
}

// -------- Metrics table: build, filter, sort --------
let sortState = { col: 'id', dir: 'asc' }; // default sort by ID asc

function buildMetricsTable(d, DESCRIPTORS){
  const tbody = document.getElementById('metricsTable');
  tbody.innerHTML = '';

  // Convert metrics dict to array with descriptor enrichment
  const rows = Object.entries(d.metrics).map(([id, obj]) => {
    const desc = DESCRIPTORS[id] || { name:'(Unknown)', category:'-' };
    const value = (typeof obj.value === 'object') ? JSON.stringify(obj.value) : obj.value;
    return {
      id: Number(id),
      name: desc.name || '(Unknown)',
      category: desc.category || '-',
      value,
      detail: obj.detail || ''
    };
  });

  // Apply sort
  rows.sort((a,b)=>compareRows(a,b,sortState.col,sortState.dir));

  // Append
  for (const r of rows){
    const tr = document.createElement('tr');
    tr.dataset.name = r.name.toLowerCase();
    tr.dataset.cat  = r.category.toLowerCase();
    tr.dataset.val  = String(r.value).toLowerCase();
    tr.innerHTML =
      `<td>${r.id}</td>
       <td>${r.name}</td>
       <td>${r.category}</td>
       <td>${r.value}</td>
       <td>${r.detail}</td>`;
    tbody.appendChild(tr);
  }
  document.getElementById('metricsCount').textContent = `Showing ${rows.length} metrics • Sorted by ${sortState.col} (${sortState.dir})`;
  updateSortIndicators();
}

function compareRows(a,b,col,dir){
  let va = a[col], vb = b[col];
  // numeric compare for id
  if (col === 'id'){
    return dir === 'asc' ? va - vb : vb - va;
  }
  // try numeric if both parse to number
  const na = parseFloat(va); const nb = parseFloat(vb);
  if (!Number.isNaN(na) && !Number.isNaN(nb)){
    return dir === 'asc' ? na - nb : nb - na;
  }
  // fallback string compare
  va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
  return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
}

function initSortableHeaders(){
  const ths = document.querySelectorAll('.table thead th.sortable');
  ths.forEach(th=>{
    th.onclick = ()=>{
      const col = th.dataset.col;
      // toggle or change
      if (sortState.col === col){
        sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
      } else {
        sortState.col = col;
        sortState.dir = 'asc';
      }
      // rebuild using current audit
      if (currentAudit && currentDescriptors){
        buildMetricsTable(currentAudit, currentDescriptors);
      }
    };
  });
}

function updateSortIndicators(){
  const ths = document.querySelectorAll('.table thead th.sortable');
  ths.forEach(th=>{
    const col = th.dataset.col;
    const span = th.querySelector('.sort-indicator');
    if (col === sortState.col){
      span.textContent = sortState.dir === 'asc' ? '▲' : '▼';
    } else {
      span.textContent = '';
    }
  });
}

function filterMetrics(){
  const q = (document.getElementById('filterText').value || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#metricsTable tr');
  let shown = 0;
  rows.forEach(tr=>{
    const match = !q ||
      tr.dataset.name.includes(q) ||
      tr.dataset.cat.includes(q)  ||
      tr.dataset.val.includes(q);
    tr.style.display = match ? '' : 'none';
    if (match) shown++;
  });
  document.getElementById('metricsCount').textContent =
    `Showing ${shown} metrics • Sorted by ${sortState.col} (${sortState.dir})`;
}

function exportMetricsCSV(){
  const rows = Array.from(document.querySelectorAll('#metricsTable tr'))
    .filter(tr => tr.style.display !== 'none')
    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.textContent));
  if (!rows.length){ alert('No metrics to export'); return; }
  const header = ['ID','Name','Category','Value','Detail'];
  const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `fftech_metrics_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// -------- PDF download (POST -> blob -> save) --------
async function downloadPDF(){
  const url = document.getElementById('urlOpen').value;
  if (!url){ alert('Run an audit first'); return; }

  try{
    const r = await fetch('/api/report/open.pdf', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ url })
    });
    if (!r.ok){
      const d = await r.json().catch(()=>({detail:'PDF error'}));
      alert(d.detail || 'Failed to generate PDF'); return;
    }
    const blob = await r.blob();
    const a = document.createElement('a');
    const href = URL.createObjectURL(blob);
    a.href = href; a.download = 'FFTech_Audit_Open.pdf'; a.click();
    URL.revokeObjectURL(href);
  }catch(err){
    alert('Download error: '+err);
  }
}

// -------- Registration placeholder --------
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
