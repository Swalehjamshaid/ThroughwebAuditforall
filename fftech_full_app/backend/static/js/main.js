(function(){
  const $ = (q)=>document.querySelector(q);
  const html = document.documentElement;
  const themeToggle = $('#themeToggle');
  if(themeToggle){
    const stored = localStorage.getItem('theme')||'light'; html.setAttribute('data-bs-theme', stored);
    themeToggle.addEventListener('click',()=>{const next=html.getAttribute('data-bs-theme')==='light'?'dark':'light';html.setAttribute('data-bs-theme',next);localStorage.setItem('theme',next);});
  }
  async function runAudit(url){
    const res = await fetch('/api/audit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    if(!res.ok){throw new Error((await res.json()).detail||'Audit failed');}
    return res.json();
  }
  if($('#homeAuditForm')){
    $('#homeAuditForm').addEventListener('submit', async (e)=>{
      e.preventDefault(); const url='https://'+$('#homeUrl').value.trim(); const data=await runAudit(url);
      $('#homeResult').classList.remove('d-none'); $('#homeScore').textContent=data.overall_score+'%'; $('#homeBar').style.width=data.overall_score+'%';
      if(window._homeChart) window._homeChart.destroy();
      window._homeChart=new Chart(document.getElementById('homeChart'),{type:'bar',data:{labels:Object.keys(data.category_scores),datasets:[{label:'Category',data:Object.values(data.category_scores),backgroundColor:'#0ea5e9'}]},options:{scales:{y:{min:0,max:100}}}});
    });
  }
  if($('#openAuditForm')){
    $('#openAuditForm').addEventListener('submit', async (e)=>{
      e.preventDefault(); const url=$('#openUrl').value.trim(); const data=await runAudit(url);
      $('#openResult').classList.remove('d-none'); $('#openScore').textContent=data.overall_score+'%'; $('#openBar').style.width=data.overall_score+'%'; $('#openGrade').textContent=data.grade;
      if(window._openChart) window._openChart.destroy();
      window._openChart=new Chart(document.getElementById('openChart'),{type:'bar',data:{labels:Object.keys(data.category_scores),datasets:[{label:'Category',data:Object.values(data.category_scores),backgroundColor:'#22d3ee'}]},options:{scales:{y:{min:0,max:100}}}});
      if(window._openStatus) window._openStatus.destroy();
      window._openStatus=new Chart(document.getElementById('openStatusChart'),{type:'bar',data:{labels:['2xx','3xx','4xx','5xx'],datasets:[{label:'HTTP',data:[data.metrics.http_2xx||0,data.metrics.http_3xx||0,data.metrics.http_4xx||0,data.metrics.http_5xx||0],backgroundColor:'#a78bfa'}]}});
      const ul=document.getElementById('openFindings'); ul.innerHTML='';
      ['Missing titles: '+(data.metrics.missing_title||0),'Missing meta descriptions: '+(data.metrics.missing_meta_desc||0),'Avg HTML size: '+(data.metrics.total_page_size||0)+' bytes'].forEach(t=>{const li=document.createElement('li'); li.textContent=t; ul.appendChild(li);});
    });
  }
  if($('#registerForm')){
    $('#registerForm').addEventListener('submit', async (e)=>{e.preventDefault(); const email=$('#registerEmail').value.trim(); await fetch('/api/auth/request-link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})}); alert('Sign-in link sent to '+email);});
  }
  if($('#loginForm')){
    $('#loginForm').addEventListener('submit', async (e)=>{e.preventDefault(); const email=$('#loginEmail').value.trim(); await fetch('/api/auth/request-link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})}); alert('Sign-in link sent to '+email);});
  }
  if($('#newAuditForm')){
    $('#newAuditForm').addEventListener('submit', async (e)=>{e.preventDefault(); const url=$('#regUrl').value.trim(); const data=await runAudit(url); document.getElementById('newAuditResult').classList.remove('d-none'); document.getElementById('viewAuditLink').href='/audit_detail?id='+(data.audit_id||0);});
  }
})();