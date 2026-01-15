
const form = document.getElementById('auditForm');
if(form){
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const url = document.getElementById('url').value.trim();
    const email = (document.getElementById('email')||{}).value || null;
    const res = await fetch('/api/audit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, email})});
    const data = await res.json();
    document.getElementById('result').classList.remove('d-none');
    document.getElementById('overallScore').innerText = data.overall_score+'%';
    document.getElementById('overallBar').style.width = data.overall_score+'%';
    document.getElementById('grade').innerText = data.grade;
  });
}
