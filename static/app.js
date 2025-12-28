
/* static/app.js */

// Theme
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

// Simple logout (client-side token)
function logout(){
  localStorage.removeItem('fftech_token');
  alert('Logged out (client-side).');
}

// Overlay
const overlay = {
  show(){ document.getElementById('overlay').classList.remove('hidden'); },
  hide(){ document.getElementById('overlay').classList.add('hidden'); }
};

// Chart.js defaults
Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text').trim() || '#e2e8f0';
Chart.defaults.font.family = "'Inter', system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#0b1220';
Chart.defaults.plugins.tooltip.borderColor = getComputedStyle(document.body).getPropertyValue('--border').trim() || '#334155';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.animation.duration = 650;

let currentAudit = null;
let currentDescriptors = null;
let catBarChart = null;
let sortState = { col: 'id', dir: 'asc' };

// Build metrics table
function buildMetricsTable(d, DESCRIPTORS){
  const tbody = document.getElementById('metricsTable');
  if (!tbody) return;
  tbody.innerHTML = '';

  const rows = Object.entries(d.metrics).map(([id, obj]) => {
    const desc = DESCRIPTORS[id] || { name:'(Unknown)', category:'-' };
    const value = (typeof obj.value === 'object') ? JSON.stringify(obj.value) : obj.value;
    return { id: Number(id), name: desc.name, category: desc.category, value, detail: obj.detail || '' };
  });

  rows.sort((a,b)=>compareRows(a,b,sortState.col,sortState.dir));
  for (const r of rows){
    const tr = document.createElement('tr');
    tr.dataset.name = String(r.name).toLowerCase();
    tr.dataset.cat  = String(r.category).toLowerCase();
    tr.dataset.val  = String(r.value).toLowerCase();
    tr.innerHTML =
      `<td>${r.id}</td><td>${r.name}</td><td>${r.category}</td><td>${r.value}</td><td>${r.detail}</td>`;
    tbody.appendChild(tr);
  }
  const mc = document.getElementById('metricsCount');
  if (mc) mc.textContent = `Showing ${rows.length} metrics • Sorted by ${sortState.col} (${sortState.dir})`;
  updateSortIndicators();
}

function compareRows(a,b,col,dir){
  let va = a[col], vb = b[col];
  if (col === 'id') return dir === 'asc' ? va - vb : vb - va;
  const na = parseFloat(va); const nb = parseFloat(vb);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return dir === 'asc' ? na - nb : nb - na;
  va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
  return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
}

function initSortableHeaders(){
  const ths = document.querySelectorAll('.table thead th.sortable');
  ths.forEach(th=>{
    th.onclick = ()=>{
      const col = th.dataset.col;
      if (sortState.col === col){
        sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
      } else {
        sortState.col = col;
        sortState.dir = 'asc';
      }
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
  const mc = document.getElementById('metricsCount');
  if (mc) mc.textContent = `Showing ${shown} metrics • Sorted by ${sortState.col} (${sortState.dir})`;
}

// Export CSV
function exportMetricsCSV(){
  const rows = Array.from(document.querySelectorAll('#metricsTable tr'))
    .filter(tr => tr.style.display !== 'none')
    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.textContent));
  if (!rows.length){ alert('No metrics to export'); return; }
  const header = ['ID','Name','Category','Value','Detail'];
  const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  const href = URL.createObjectURL(blob);
  a.href = href; a.download = `fftech_metrics_${Date.now()}.csv`; a.click();
  URL.revokeObjectURL(href);
}

// Registered-only PDF
async function downloadPDF(){
  const url = document.querySelector('#urlOpen')?.value || '';
  if (!url){ alert('Run an audit first'); return; }
  const token = localStorage.getItem('fftech_token');
  if (!token){ alert('Sign in & verify email to download the PDF'); return; }
  try{
    const r = await fetch('/api/report/pdf', {
      method:'POST',
      headers:{ 'Content-Type':'application/json', 'Authorization': 'Bearer '+token },
      body: JSON.stringify({ url })
    });
    if (!r.ok){
      const d = await r.json().catch(()=>({detail:'PDF error'}));
      alert(d.detail || 'Failed to generate PDF'); return;
    }
    const blob = await r.blob();
    const a = document.createElement('a');
    const href = URL.createObjectURL(blob);
    a.href = href; a.download = 'FFTech_Audit.pdf'; a.click();
    URL.revokeObjectURL(href);
  }catch(err){ alert('Download error: '+err); }
}

// Request magic/verify link
async function requestLink(e){
  e.preventDefault();
  try{
    const email = document.getElementById('emailInput').value;
    const r = await fetch('/auth/request-link', { method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({email}) });
    const d = await r.json();
    alert(d.message || 'Link sent / logged.');
  }catch(err){ alert('Error sending link: '+err); }
}
