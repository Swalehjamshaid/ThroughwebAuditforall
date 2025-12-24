<!DOCTYPE html>
<html lang="en" class="h-full scroll-smooth">
<head>
<meta charset="UTF-8">
<title>FF TECH ELITE v3 | Enterprise Web Audit</title>
<meta name="viewport" content="width=device-width, initial-scale=1">

<!-- Tailwind -->
<script src="https://cdn.tailwindcss.com"></script>

<!-- Fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">

<style>
body{font-family:Inter,sans-serif}
.card{background:#0b1220;border:1px solid #1f2a3b}
.glow{box-shadow:0 0 35px rgba(16,185,129,.35)}
.loader{border-top-color:#10b981;animation:spin 1s linear infinite}
.step{opacity:.4;transition:.4s}
.step.active{opacity:1;color:#34d399}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>

<body class="bg-slate-950 text-slate-100 min-h-full">

<!-- HEADER -->
<header class="border-b border-slate-800">
  <div class="max-w-7xl mx-auto px-6 py-5 flex justify-between items-center">
    <h1 class="text-2xl font-bold text-emerald-400">
      FF TECH ELITE <span class="text-slate-400">v3</span>
    </h1>
    <span class="text-sm text-slate-400">Enterprise Website Audit Engine</span>
  </div>
</header>

<!-- HERO -->
<section class="max-w-7xl mx-auto px-6 py-14 text-center">
  <h2 class="text-4xl font-bold mb-4">World-Class Website Audit</h2>
  <p class="text-slate-400 max-w-3xl mx-auto">
    Real Lighthouse, SEO, UX, Security & Performance analysis with
    300+ weighted metrics. Every site gets a real score.
  </p>
</section>

<!-- INPUT -->
<section class="max-w-4xl mx-auto px-6">
  <div class="card rounded-xl p-8 glow">
    <div class="grid md:grid-cols-4 gap-4">
      <input id="urlInput" placeholder="https://example.com"
        class="md:col-span-2 px-4 py-3 rounded bg-slate-800 border border-slate-700 focus:ring-2 focus:ring-emerald-500 outline-none">

      <select id="modeInput"
        class="px-4 py-3 rounded bg-slate-800 border border-slate-700">
        <option value="desktop">Desktop Audit</option>
        <option value="mobile">Mobile Audit</option>
      </select>

      <button onclick="runAudit()"
        class="bg-emerald-500 hover:bg-emerald-600 text-black font-semibold rounded px-6 py-3">
        Run Audit
      </button>
    </div>
  </div>
</section>

<!-- LOADER -->
<div id="loader" class="hidden flex flex-col items-center py-16">
  <div class="w-16 h-16 border-4 border-slate-700 rounded-full loader"></div>
  <p class="mt-4 text-slate-400">Running real audit…</p>
</div>

<!-- PROGRESS -->
<div id="progressSteps" class="hidden max-w-3xl mx-auto px-6 py-10">
  <ul class="space-y-3 text-sm">
    <li class="step">🔍 Initializing audit engine</li>
    <li class="step">⚡ Lighthouse performance</li>
    <li class="step">📊 Core Web Vitals</li>
    <li class="step">🔐 Security & headers</li>
    <li class="step">🧠 SEO & DOM intelligence</li>
    <li class="step">🏁 Final scoring</li>
  </ul>
</div>

<!-- RESULTS -->
<section id="results" class="hidden max-w-7xl mx-auto px-6 pb-24 space-y-12">

<!-- SCORE -->
<div class="grid md:grid-cols-5 gap-6">
  <div class="md:col-span-2 card rounded-xl p-8 text-center glow">
    <svg width="160" height="160" class="mx-auto">
      <circle cx="80" cy="80" r="70" stroke="#1f2937" stroke-width="12" fill="none"/>
      <circle id="scoreRing"
        cx="80" cy="80" r="70"
        stroke="#10b981" stroke-width="12"
        fill="none"
        stroke-dasharray="440"
        stroke-dashoffset="440"
        stroke-linecap="round"
        transform="rotate(-90 80 80)"/>
      <text x="50%" y="50%" dy=".3em" text-anchor="middle"
        class="fill-emerald-400 text-3xl font-bold"
        id="overallScore">0%</text>
    </svg>
    <p id="auditedUrl" class="text-xs text-slate-500 mt-2"></p>
  </div>

  <div class="md:col-span-3 card rounded-xl p-6">
    <h4 class="font-semibold mb-4">Pillar Scores</h4>
    <div id="pillarScores" class="grid grid-cols-2 gap-4"></div>
  </div>
</div>

<!-- PERFORMANCE -->
<div class="card rounded-xl p-6">
  <h4 class="font-semibold mb-4">Core Web Vitals</h4>
  <div id="perfGrid" class="grid md:grid-cols-4 gap-4"></div>
</div>

<!-- ROADMAP -->
<div class="card rounded-xl p-6">
  <h4 class="font-semibold mb-4">Improvement Roadmap</h4>
  <div id="roadmap" class="text-sm text-slate-300 leading-relaxed"></div>
</div>

<!-- METRICS -->
<div class="card rounded-xl p-6 overflow-x-auto">
  <h4 class="font-semibold mb-4">Advanced Diagnostics</h4>
  <table class="w-full text-sm">
    <thead class="bg-slate-800">
      <tr>
        <th class="p-2 text-left">#</th>
        <th class="p-2 text-left">Metric</th>
        <th class="p-2 text-left">Category</th>
        <th class="p-2 text-right">Score</th>
        <th class="p-2 text-right">Weight</th>
      </tr>
    </thead>
    <tbody id="metricsTable"></tbody>
  </table>
</div>

<!-- PDF -->
<div class="text-center">
  <button onclick="downloadPDF()"
    class="bg-emerald-500 hover:bg-emerald-600 text-black font-semibold px-10 py-4 rounded-xl">
    Download PDF Report
  </button>
</div>

</section>

<script>
let auditData=null;

async function runAudit(){
  const url=urlInput.value.trim();
  const mode=modeInput.value;
  if(!url) return alert("Enter a valid URL");

  loader.classList.remove("hidden");
  progressSteps.classList.remove("hidden");
  results.classList.add("hidden");

  const steps=[...document.querySelectorAll(".step")];
  let i=0;
  const timer=setInterval(()=>{
    if(i<steps.length)steps[i++].classList.add("active");
  },700);

  try{
    const res=await fetch("/audit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,mode})});
    auditData=await res.json();
    clearInterval(timer);
    renderResults(auditData);
  }catch{
    alert("Audit failed");
  }finally{
    loader.classList.add("hidden");
    progressSteps.classList.add("hidden");
  }
}

function renderResults(d){
  results.classList.remove("hidden");
  auditedUrl.textContent=d.url;

  const ring=document.getElementById("scoreRing");
  const score=d.total_grade;
  ring.style.transition="1.5s ease";
  ring.style.strokeDashoffset=440-(440*score/100);
  overallScore.textContent=score+"%";

  pillarScores.innerHTML="";
  Object.entries(d.pillars||{}).forEach(([k,v])=>{
    pillarScores.innerHTML+=`
    <div class="bg-slate-800 p-4 rounded">
      <div class="text-xs text-slate-400">${k}</div>
      <div class="text-xl font-bold text-emerald-400">${v}%</div>
    </div>`;
  });

  perfGrid.innerHTML="";
  Object.entries(d.perf||{}).forEach(([k,v])=>{
    perfGrid.innerHTML+=`
    <div class="bg-slate-800 p-4 rounded">
      <div class="text-xs text-slate-400">${k}</div>
      <div class="font-semibold">${v}</div>
    </div>`;
  });

  roadmap.innerHTML=d.roadmap||"";

  metricsTable.innerHTML="";
  (d.metrics||[]).forEach(m=>{
    metricsTable.innerHTML+=`
    <tr class="border-b border-slate-800">
      <td class="p-2">${m.no}</td>
      <td class="p-2">${m.name}</td>
      <td class="p-2">${m.category}</td>
      <td class="p-2 text-right ${m.score<80?'text-red-400':'text-emerald-400'}">${m.score}%</td>
      <td class="p-2 text-right">${m.weight}</td>
    </tr>`;
  });
}

async function downloadPDF(){
  const res=await fetch("/download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(auditData)});
  const blob=await res.blob();
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="FF_TECH_ELITE_Audit_Report.pdf";
  a.click();
}
</script>

</body>
</html>
