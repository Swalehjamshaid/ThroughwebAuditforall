
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

const form = document.getElementById('auditForm');
if(form){
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const url = document.getElementById('url').value.trim();
    const comps = document.getElementById('competitors') ? document.getElementById('competitors').value.split(',').map(x=>x.trim()).filter(Boolean) : [];
    const res = await fetch('/api/audit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, competitors: comps})});
    const data = await res.json();
    document.getElementById('result').classList.remove('d-none');
    document.getElementById('overallScore').innerText = data.overall_score+'%';
    document.getElementById('overallBar').style.width = data.overall_score+'%';
    document.getElementById('grade').innerText = data.grade;

    const ctx = document.getElementById('categoriesChart');
    const labels = Object.keys(data.category_scores);
    const values = Object.values(data.category_scores);
    if(window._catChart){ window._catChart.destroy(); }
    window._catChart = new Chart(ctx, {type:'bar', data:{labels, datasets:[{label:'Category Score', data: values, backgroundColor:'#0ea5e9'}]}, options:{scales:{y:{min:0,max:100}}}});

    renderCompetitorChart(data.competitors || []);
  });
}

function renderCompetitorChart(list){
  const el = document.getElementById('competitorChart');
  if(!el || !Array.isArray(list) || list.length===0){ return; }
  const labels = list.map(c => c.url);
  const values = list.map(c => c.competitor_health_score || 0);
  if(window._compChart){ window._compChart.destroy(); }
  window._compChart = new Chart(el, {type:'bar', data:{labels, datasets:[{label:'Health', data: values, backgroundColor:'#f59e0b'}]}, options:{scales:{y:{min:0,max:100}}}});
}
