<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Throughweb Elite | World-Class Web Audit AI</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .glass { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.08); }
        .red-leak { background: linear-gradient(135deg, #450a0a 0%, #1e1b4b 100%); border: 1px solid #ef4444; }
        .gain-green { background: linear-gradient(135deg, #064e3b 0%, #1e1b4b 100%); border: 1px solid #10b981; }
        .card-glass { background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.05); }
        .warn-text { color: #fbbf24; }
        .pass-text { color: #10b981; }
        .fail-text { color: #ef4444; }
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
        input:focus, button:focus { outline: 2px solid #3b82f6; outline-offset: 2px; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .animate-fade-in { animation: fadeIn 0.6s ease-out; }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
</head>
<body class="bg-[#020617] text-slate-100 p-4 md:p-8 lg:p-12 min-h-screen antialiased">
    <div class="max-w-7xl mx-auto">
        <!-- Header -->
        <header class="flex flex-col lg:flex-row justify-between items-center mb-12 md:mb-16 p-8 md:p-10 glass rounded-3xl md:rounded-[50px] gap-6 md:gap-8 shadow-2xl">
            <h1 class="text-3xl md:text-4xl lg:text-5xl font-black italic text-blue-400 uppercase tracking-tighter">
                Throughweb <span class="text-white font-light">World-Class Audit</span>
            </h1>
            <div class="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
                <label for="url" class="sr-only">Enter website URL</label>
                <input 
                    type="text" 
                    id="url" 
                    placeholder="Enter domain (e.g., example.com or https://example.com)" 
                    class="bg-slate-950/80 border border-slate-700 px-6 py-4 rounded-3xl w-full sm:w-96 outline-none text-sm focus:border-blue-500 transition-all" 
                    aria-required="true">
                <button 
                    onclick="runAudit()" 
                    id="btn" 
                    class="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-900 px-8 py-4 rounded-3xl font-bold uppercase tracking-widest transition-all text-sm md:text-base shadow-lg">
                    Launch World-Class Scan
                </button>
            </div>
        </header>

        <!-- Results Section -->
        <div id="results" class="hidden space-y-12 animate-fade-in">
            <!-- Top KPI Cards -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                <div class="red-leak p-8 md:p-10 rounded-3xl md:rounded-[50px] flex flex-col justify-center text-center shadow-xl" role="region" aria-labelledby="leak-label">
                    <span id="leak-label" class="text-red-400 font-black text-xs uppercase mb-3 tracking-widest">Estimated Revenue Leakage</span>
                    <div id="revLoss" class="text-5xl md:text-6xl font-black text-red-400 mb-2">-</div>
                    <p class="text-slate-400 text-xs italic">From performance & compliance issues</p>
                </div>

                <div class="gain-green p-8 md:p-10 rounded-3xl md:rounded-[50px] flex flex-col justify-center text-center shadow-xl" role="region" aria-labelledby="gain-label">
                    <span id="gain-label" class="text-emerald-400 font-black text-xs uppercase mb-3 tracking-widest">Potential Revenue Recovery</span>
                    <div id="revGain" class="text-5xl md:text-6xl font-black text-emerald-400 mb-2">+</div>
                    <p class="text-slate-300 text-xs italic">Through targeted optimizations</p>
                </div>

                <div class="card-glass p-8 md:p-10 rounded-3xl md:rounded-[50px] flex flex-col justify-center text-center shadow-xl border-blue-500/20" role="region" aria-labelledby="lcp-label">
                    <span id="lcp-label" class="text-blue-400 font-black text-xs uppercase mb-3 tracking-widest">Largest Contentful Paint</span>
                    <div id="lcpVal" class="text-4xl md:text-5xl font-black text-white mb-2">--</div>
                    <p class="text-slate-400 text-xs italic">Core Web Vital – Major Ranking Factor</p>
                </div>

                <div class="card-glass p-8 md:p-10 rounded-3xl md:rounded-[50px] text-center shadow-xl border-white/10" role="region" aria-labelledby="health-label">
                    <span id="health-label" class="text-slate-400 text-xs font-black uppercase mb-4 tracking-widest">Overall Health Score</span>
                    <div id="grade" class="text-7xl md:text-8xl font-black text-white leading-none">--</div>
                    <div id="score" class="text-3xl md:text-4xl font-light text-slate-300 mt-2">--</div>
                </div>
            </div>

            <!-- Broken Links Alert -->
            <div id="brokenBox" class="hidden p-8 md:p-10 rounded-3xl md:rounded-[50px] bg-red-950/30 border border-red-800/50 shadow-xl" role="alert">
                <h3 class="text-red-400 font-black text-sm uppercase mb-6 tracking-widest flex items-center gap-3">
                    <span class="w-3 h-3 bg-red-500 rounded-full animate-ping" aria-hidden="true"></span>
                    Critical Broken Links Detected
                </h3>
                <ul id="brokenList" class="text-xs font-mono text-red-300 space-y-2 max-h-64 overflow-y-auto list-disc pl-6"></ul>
            </div>

            <!-- Metrics Grid -->
            <section class="glass p-10 md:p-14 rounded-3xl md:rounded-[60px] shadow-2xl" role="region" aria-labelledby="metrics-title">
                <h2 id="metrics-title" class="text-xs md:text-sm font-black text-slate-500 uppercase mb-10 md:mb-14 text-center tracking-[0.6em]">
                    Comprehensive Diagnostic Metrics
                </h2>
                <div id="metricsGrid" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5"></div>
            </section>

            <!-- Download Report -->
            <a 
                id="dl" 
                href="#" 
                download 
                class="block w-full py-6 md:py-8 glass rounded-3xl md:rounded-[40px] text-center font-black uppercase tracking-widest text-blue-300 hover:bg-blue-600/30 hover:text-white transition-all border-2 border-blue-900/40 shadow-xl text-sm md:text-base" 
                role="button" 
                aria-label="Download full PDF report">
                Download Executive PDF Report
            </a>
        </div>
    </div>

    <script>
        async function runAudit() {
            const resultsDiv = document.getElementById('results');
            resultsDiv.classList.add('hidden');

            const urlInput = document.getElementById('url').value.trim();
            if (!urlInput) {
                alert('Please enter a website URL');
                return;
            }

            const btn = document.getElementById('btn');
            btn.innerText = 'SCANNING WEBSITE...';
            btn.disabled = true;
            btn.setAttribute('aria-busy', 'true');

            try {
                const response = await fetch('/audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: urlInput })
                });

                const result = await response.json();

                if (response.ok) {
                    const d = result.data;

                    resultsDiv.classList.remove('hidden');

                    // Financial Impact
                    document.getElementById('revLoss').innerText = `-${d.financial_data.estimated_revenue_leak}`;
                    document.getElementById('revGain').innerText = `+${d.financial_data.potential_recovery_gain}`;

                    // LCP
                    const lcpMetric = d.metrics['Largest Contentful Paint (LCP)'] || { val: 'N/A' };
                    document.getElementById('lcpVal').innerText = lcpMetric.val;

                    // Grade & Score
                    document.getElementById('grade').innerText = d.grade;
                    document.getElementById('score').innerText = `${d.score}%`;

                    // Download Link
                    document.getElementById('dl').href = `/download/${result.id}`;

                    // Broken Links
                    const brokenBox = document.getElementById('brokenBox');
                    const brokenList = document.getElementById('brokenList');
                    if (d.broken_links && d.broken_links.length > 0) {
                        brokenBox.classList.remove('hidden');
                        brokenList.innerHTML = d.broken_links
                            .map(link => `<li><a href="${link}" class="underline hover:text-red-400" target="_blank">${link}</a></li>`)
                            .join('');
                    } else {
                        brokenBox.classList.add('hidden');
                    }

                    // Metrics Grid – Clean & Color-Coded
                    let gridHTML = "";
                    Object.entries(d.metrics).forEach(([key, value]) => {
                        let colorClass = 'text-blue-300';
                        if (value.status === 'FAIL') colorClass = 'fail-text';
                        else if (value.status === 'WARN') colorClass = 'warn-text';
                        else if (value.status === 'PASS') colorClass = 'pass-text';

                        const note = value.note ? `<span class="block text-[8px] text-slate-500 mt-1">${value.note}</span>` : '';

                        gridHTML += `
                            <div class="p-5 card-glass rounded-2xl text-center shadow-md border border-white/5">
                                <div class="text-[10px] text-slate-400 font-bold uppercase truncate mb-2">${key}</div>
                                <div class="font-black text-base ${colorClass}">${value.val}</div>
                                <div class="text-[9px] text-slate-500 mt-2">${value.status || ''}</div>
                                ${note}
                            </div>`;
                    });
                    document.getElementById('metricsGrid').innerHTML = gridHTML;

                } else {
                    alert(result.detail || 'Audit failed. The site may be temporarily unavailable or blocking scans.');
                }
            } catch (err) {
                alert('Connection error. Please try again later.');
                console.error(err);
            } finally {
                btn.innerText = 'Launch World-Class Scan';
                btn.disabled = false;
                btn.removeAttribute('aria-busy');
            }
        }

        // Allow Enter key to trigger scan
        document.getElementById('url').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') runAudit();
        });
    </script>
</body>
</html>
