const html = document.documentElement;
const themeToggle = document.getElementById('themeToggle');
if(themeToggle){
  const stored = localStorage.getItem('theme')||'light';
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
    const comps = document.getElementById('competitors').value.split(',').map(s=>s.trim()).filter(Boolean);
    const res = await fetch('/api/audit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, competitors: comps})});
    const data = await res.json();

    document.getElementById('result').classList.remove('d-none');
    document.getElementById('overallScore').innerText = data.overall_score+'%';
    document.getElementById('overallBar').style.width = data.overall_score+'%';
    document.getElementById('grade').innerText = data.grade;
    document.getElementById('mTitle').innerText = data.metrics.missing_title;
    document.getElementById('mMeta').innerText = data.metrics.missing_meta_desc;
    document.getElementById('pgSize').innerText = data.metrics.total_page_size;
    document.getElementById('pdfLink').href = data.download_url;

    const labels = Object.keys(data.category_scores);
    const values = Object.values(data.category_scores);
    if(window._cat){window._cat.destroy();}
    window._cat = new Chart(document.getElementById('categoriesChart'), {type:'bar', data:{labels, datasets:[{label:'Category Score', data: values, backgroundColor:'#0ea5e9'}]}, options:{scales:{y:{min:0,max:100}}}});

    const stLabels = ['2xx','3xx','4xx','5xx'];
    const stVals = [data.metrics.http_2xx||0, data.metrics.http_3xx||0, data.metrics.http_4xx||0, data.metrics.http_5xx||0];
    if(window._st){window._st.destroy();}
    window._st = new Chart(document.getElementById('statusChart'), {type:'bar', data:{labels:stLabels, datasets:[{label:'Pages', data:stVals, backgroundColor:'#10b981'}]}, options:{scales:{y:{beginAtZero:true}}}});
  });
}