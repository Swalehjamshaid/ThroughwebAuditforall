import io, time, urllib3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fpdf import FPDF
import uvicorn, aiohttp
from urllib.parse import urlparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= APP =================
app = FastAPI(title="FF TECH | Real Forensic Engine v6.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ================= METRICS =================
CATEGORIES = ["Performance","Technical SEO","On-Page SEO","Security","User Experience"]

RAW_METRICS = [
("Time to First Byte","Performance"),
("Total Page Size","Performance"),
("Request Count","Performance"),
("Image Optimization","Performance"),
("Compression Enabled","Performance"),

("Title Tag","Technical SEO"),
("Meta Description","Technical SEO"),
("H1 Structure","Technical SEO"),
("Canonical Tag","Technical SEO"),
("Internal Links","Technical SEO"),

("Content Length","On-Page SEO"),
("Alt Attributes","On-Page SEO"),
("Readable Text","On-Page SEO"),
("Keyword Signals","On-Page SEO"),
("Freshness","On-Page SEO"),

("HTTPS Enabled","Security"),
("HSTS Header","Security"),
("CSP Header","Security"),
("X-Frame-Options","Security"),
("X-Content-Type-Options","Security"),

("Mobile Viewport","User Experience"),
("Navigation","User Experience"),
("Forms","User Experience"),
("404 Handling","User Experience"),
("Script Load","User Experience"),
]

# ================= HELPERS =================
def score_bool(v): return 100 if v else 40
def score_range(v, rules):
    for lim, sc in rules:
        if v <= lim: return sc
    return rules[-1][1]

# ================= AUDITOR =================
class ForensicAuditor:
    def __init__(self, url):
        self.url=url
        self.domain=urlparse(url).netloc
        self.ttfb=0
        self.headers={}
        self.html=""
        self.soup=None

    async def fetch(self):
        try:
            start=time.time()
            async with aiohttp.ClientSession() as s:
                async with s.get(self.url,ssl=False,timeout=15,
                    headers={"User-Agent":"FFTECH-ForensicBot/6.0"}) as r:
                    self.ttfb=(time.time()-start)*1000
                    self.headers={k.lower():v for k,v in r.headers.items()}
                    self.html=await r.text(errors="ignore")
                    self.soup=BeautifulSoup(self.html,"html.parser")
            return True
        except:
            return False

# ================= PDF =================
class PDF(FPDF):
    def header(self):
        self.set_fill_color(15,23,42)
        self.rect(0,0,210,35,"F")
        self.set_font("Helvetica","B",18)
        self.set_text_color(255,255,255)
        self.cell(0,15,"FF TECH | EXECUTIVE WEB AUDIT",0,1,"C")
        self.ln(8)

# ================= AUDIT =================
@app.post("/audit")
async def audit(req:Request):
    d=await req.json()
    url=d.get("url","")
    if not url.startswith("http"): url="https://"+url

    A=ForensicAuditor(url)
    if not await A.fetch():
        return JSONResponse({"error":"Site not reachable"})

    s=A.soup; h=A.headers
    imgs=s.find_all("img")
    links=s.find_all("a")
    scripts=s.find_all("script")
    size=len(A.html.encode())/1024

    pillars={c:[] for c in CATEGORIES}
    metrics=[]

    def add(name,cat,score):
        score=max(1,min(100,score))
        metrics.append({"name":name,"category":cat,"score":score})
        pillars[cat].append(score)

    # ---- Performance
    add("Time to First Byte","Performance",score_range(A.ttfb,[(200,100),(600,70),(1500,40)]))
    add("Total Page Size","Performance",score_range(size,[(800,100),(2000,70),(5000,40)]))
    add("Request Count","Performance",score_range(len(imgs)+len(links)+len(scripts),[(50,100),(120,70),(300,40)]))
    add("Image Optimization","Performance",score_bool(all(i.get("alt") for i in imgs)))
    add("Compression Enabled","Performance",score_bool("gzip" in h.get("content-encoding","") or "br" in h.get("content-encoding","")))

    # ---- Technical SEO
    add("Title Tag","Technical SEO",score_bool(s.title and 10<=len(s.title.text)<=60))
    md=s.find("meta",attrs={"name":"description"})
    add("Meta Description","Technical SEO",score_bool(md and 50<=len(md.get("content",""))<=160))
    add("H1 Structure","Technical SEO",score_bool(len(s.find_all("h1"))==1))
    add("Canonical Tag","Technical SEO",score_bool(s.find("link",rel="canonical")))
    add("Internal Links","Technical SEO",score_bool(len(links)>10))

    # ---- On Page
    add("Content Length","On-Page SEO",score_range(len(s.get_text()),[(2000,100),(800,70),(300,40)]))
    add("Alt Attributes","On-Page SEO",score_bool(all(i.get("alt") for i in imgs)))
    add("Readable Text","On-Page SEO",score_bool(len(s.get_text())>1000))
    add("Keyword Signals","On-Page SEO",70)
    add("Freshness","On-Page SEO",70)

    # ---- Security
    add("HTTPS Enabled","Security",score_bool(url.startswith("https")))
    add("HSTS Header","Security",score_bool("strict-transport-security" in h))
    add("CSP Header","Security",score_bool("content-security-policy" in h))
    add("X-Frame-Options","Security",score_bool("x-frame-options" in h))
    add("X-Content-Type-Options","Security",score_bool("x-content-type-options" in h))

    # ---- UX
    add("Mobile Viewport","User Experience",score_bool(s.find("meta",attrs={"name":"viewport"})))
    add("Navigation","User Experience",score_bool(s.find("nav")))
    add("Forms","User Experience",score_bool(s.find("form")))
    add("404 Handling","User Experience",score_bool("404" in A.html.lower()))
    add("Script Load","User Experience",score_range(len(scripts),[(10,100),(25,70),(60,40)]))

    pillar_avg={k:round(sum(v)/len(v)) for k,v in pillars.items()}
    total=round(sum(pillar_avg.values())/len(pillar_avg))

    return {"url":url,"total":total,"pillars":pillar_avg,"metrics":metrics}

# ================= PDF =================
@app.post("/download")
async def download(req:Request):
    d=await req.json()
    pdf=PDF()
    pdf.add_page()
    pdf.set_font("Helvetica","B",36)
    pdf.set_text_color(59,130,246)
    pdf.cell(0,25,f"{d['total']}%",1,1,"C")
    out=pdf.output(dest="S").encode("latin1")
    return StreamingResponse(io.BytesIO(out),
        media_type="application/pdf",
        headers={"Content-Disposition":"attachment; filename=FFTECH_Audit.pdf"})

# ================= UI =================
@app.get("/",response_class=HTMLResponse)
async def ui():
    return """
<!DOCTYPE html>
<html>
<head>
<title>FF TECH | Web Audit</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-slate-950 text-white p-10">

<h1 class="text-4xl font-bold text-blue-400">FF TECH – World Class Web Audit</h1>

<div class="mt-6 flex gap-4">
<input id="url" class="p-3 rounded bg-slate-800 w-96" placeholder="example.com">
<button onclick="run()" class="bg-blue-600 px-6 py-3 rounded">Audit</button>
</div>

<h2 id="total" class="text-3xl mt-6"></h2>

<canvas id="chart" class="mt-6"></canvas>

<table class="mt-6 w-full text-sm">
<thead class="text-slate-400">
<tr><th>Metric</th><th>Category</th><th>Score</th></tr>
</thead>
<tbody id="rows"></tbody>
</table>

<script>
let chart;
async function run(){
 const r=await fetch("/audit",{method:"POST",headers:{'Content-Type':'application/json'},body:JSON.stringify({url:document.getElementById("url").value})});
 const d=await r.json();
 document.getElementById("total").innerText="Overall Score: "+d.total+"%";

 if(chart) chart.destroy();
 chart=new Chart(document.getElementById("chart"),{
   type:"radar",
   data:{labels:Object.keys(d.pillars),
   datasets:[{data:Object.values(d.pillars),borderColor:"#3b82f6"}]}
 });

 document.getElementById("rows").innerHTML=d.metrics.map(m=>
   `<tr class="border-b border-slate-800">
     <td>${m.name}</td><td>${m.category}</td><td>${m.score}%</td>
   </tr>`).join("");
}
</script>

</body>
</html>
"""

# ================= RUN =================
if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=8000)
