
function showLogin(){alert('Login form coming soon');}
function logout(){localStorage.removeItem('fftech_token');alert('Logged out');}
const overlay={show(){document.getElementById('overlay').classList.remove('hidden');},hide(){document.getElementById('overlay').classList.add('hidden');}};
async function runOpenAudit(e){
  e.preventDefault();
  overlay.show();
  const url=document.getElementById('urlOpen').value;
  try{
    const r=await fetch('/api/audit/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const d=await r.json();
    if(r.ok){renderResults(d);}else{alert(d.detail||'Audit failed');}
  }catch(err){alert('Error:'+err);}finally{overlay.hide();}
}
function renderResults(d){
  document.getElementById('results').classList.remove('hidden');
  document.getElementById('summary').textContent=d.metrics[3].value;
  document.getElementById('scoreGrade').innerHTML=`<span>Score:${d.score}%</span><span>Grade:${d.grade}</span>`;
  document.getElementById('scoreBar').style.width=d.score+'%';
}
