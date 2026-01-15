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
    const user_email = document.getElementById('email').value.trim() || null;
    const res = await fetch('/api/audit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, user_email})});
    const data = await res.json();
    document.getElementById('result').classList.remove('d-none');
    document.getElementById('overallScore').innerText = data.overall_score+'%';
    document.getElementById('overallBar').style.width = data.overall_score+'%';
    document.getElementById('grade').innerText = data.grade;

    const labels = Object.keys(data.category_scores);
    const values = Object.values(data.category_scores);
    const ctx1 = document.getElementById('categoriesChart');
    if(window._cat) window._cat.destroy();
    window._cat = new Chart(ctx1, {type:'bar', data:{labels, datasets:[{label:'Category', data: values, backgroundColor:'#0ea5e9'}]}, options:{scales:{y:{min:0,max:100}}}});

    const s = data.metrics;
    const ctx2 = document.getElementById('statusChart');
    const sLabels = ['2xx','3xx','4xx','5xx'];
    const sValues = [s.http_2xx||0,s.http_3xx||0,s.http_4xx||0,s.http_5xx||0];
    if(window._st) window._st.destroy();
    window._st = new Chart(ctx2, {type:'doughnut', data:{labels:sLabels,datasets:[{data:sValues,backgroundColor:['#22c55e','#eab308','#ef4444','#7c3aed']}]}));

    const panels = document.getElementById('panels');
    panels.innerHTML = `
      <div class="row g-2">
        <div class="col-md-4">
          <div class="border rounded p-2">
            <div class="fw-semibold">Strengths</div>
            <ul class="mb-0">${(data.summary.strengths||[]).map(x=>`<li>${x}</li>`).join('')}</ul>
          </div>
        </div>
        <div class="col-md-4">
          <div class="border rounded p-2">
            <div class="fw-semibold">Weak Areas</div>
            <ul class="mb-0">${(data.summary.weaknesses||[]).map(x=>`<li>${x}</li>`).join('')}</ul>
          </div>
        </div>
        <div class="col-md-4">
          <div class="border rounded p-2">
            <div class="fw-semibold">Priority Fixes</div>
            <ul class="mb-0">${(data.summary.priority_fixes||[]).map(x=>`<li>${x}</li>`).join('')}</ul>
          </div>
        </div>
      </div>`;
  });
}