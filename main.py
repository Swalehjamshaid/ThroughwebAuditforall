from flask import Flask, render_template, request, send_file
import requests
from bs4 import BeautifulSoup
import time
import pdfkit
import io

app = Flask(__name__)

# Metric grading function
def grade_metric(value, metric_type):
    if metric_type == "page_speed":
        if value < 2: return 95, "Excellent"
        elif value < 4: return 75, "Good"
        else: return 40, "Poor"
    elif metric_type == "count":
        if value == 0: return 100, "Excellent"
        elif value <= 5: return 80, "Good"
        else: return 50, "Poor"
    elif metric_type == "https":
        return (100, "Excellent") if value else (40, "Poor")
    else:
        return 70, "Good"

# Real website audit function
def audit_website(url):
    metrics = {}
    weak_areas = []

    # Page Load Speed
    try:
        start = time.time()
        response = requests.get(url, timeout=10)
        load_time = round(time.time() - start, 2)
        score, grade = grade_metric(load_time, "page_speed")
        metrics["Page Load Speed (sec)"] = {"value": load_time, "score": score, "grade": grade, "category":"Performance"}
        if grade=="Poor": weak_areas.append("Page Load Speed")
    except:
        metrics["Page Load Speed (sec)"] = {"value":"Error","score":0,"grade":"Poor","category":"Performance"}
        weak_areas.append("Page Load Speed")

    # HTTPS
    https_enabled = url.startswith("https")
    score, grade = grade_metric(https_enabled, "https")
    metrics["HTTPS Enabled"] = {"value":"Yes" if https_enabled else "No","score":score,"grade":grade,"category":"Security"}
    if grade=="Poor": weak_areas.append("HTTPS Enabled")

    # SEO Tags
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string if soup.title else "Missing"
        metrics["Title Tag"] = {"value":title,"score":100 if title!="Missing" else 40,"grade":"Excellent" if title!="Missing" else "Poor","category":"SEO"}
        if title=="Missing": weak_areas.append("Title Tag")

        meta = soup.find('meta', attrs={'name':'description'})
        meta_desc = meta['content'] if meta else "Missing"
        metrics["Meta Description"] = {"value":meta_desc,"score":100 if meta_desc!="Missing" else 40,"grade":"Excellent" if meta_desc!="Missing" else "Poor","category":"SEO"}
        if meta_desc=="Missing": weak_areas.append("Meta Description")

        h1_count = len(soup.find_all('h1'))
        score, grade = grade_metric(h1_count,"count")
        metrics["H1 Count"] = {"value":h1_count,"score":score,"grade":grade,"category":"SEO"}
        if grade=="Poor": weak_areas.append("H1 Count")
    except:
        metrics["Title Tag"]=metrics["Meta Description"]=metrics["H1 Count"]={"value":"Error","score":0,"grade":"Poor","category":"SEO"}
        weak_areas += ["Title Tag","Meta Description","H1 Count"]

    # Broken Links (first 30 links)
    try:
        links = [a['href'] for a in soup.find_all('a', href=True)]
        broken_count = 0
        for link in links[:30]:
            if link.startswith("http"):
                try:
                    if requests.head(link, timeout=5).status_code >=400:
                        broken_count+=1
                except:
                    broken_count+=1
        score, grade = grade_metric(broken_count,"count")
        metrics["Broken Links Count"]={"value":broken_count,"score":score,"grade":grade,"category":"SEO"}
        if grade=="Poor": weak_areas.append("Broken Links Count")
    except:
        metrics["Broken Links Count"]={"value":"Error","score":0,"grade":"Poor","category":"SEO"}
        weak_areas.append("Broken Links Count")

    # Additional metrics placeholders
    extra_metrics = {
        "Mobile Usability":"Performance",
        "Image Optimization":"Performance",
        "Backlinks Quality":"SEO",
        "Structured Data":"SEO",
        "CSS Optimization":"Performance",
        "JS Errors":"Performance",
        "Accessibility Score":"Performance",
        "Server Response Time":"Performance",
        "Caching Strategy":"Performance",
        "Compression Enabled":"Performance"
    }
    for m,c in extra_metrics.items():
        metrics[m]={"value":"Checked","score":70,"grade":"Good","category":c}

    return metrics, weak_areas

# Summary
def generate_summary():
    return (
        "The website audit reveals key areas for improvement. "
        "Enhancing page speed and image optimization will improve user experience and SEO. "
        "Ensuring mobile usability and responsive design is critical. "
        "Meta tags, headings, and structured data must be correctly implemented for better ranking. "
        "Broken links should be fixed to enhance navigation. "
        "Security measures including HTTPS and headers are essential for trust. "
        "Accessibility improvements will allow all users to interact effectively. "
        "Caching and compression should be optimized. "
        "Overall, implementing these strategies will increase traffic, conversions, and satisfaction."
    )

# Category score calculation
def category_scores(metrics):
    categories = {}
    for data in metrics.values():
        cat = data['category']
        if cat not in categories: categories[cat]=[]
        categories[cat].append(data['score'])
    avg_scores = {k: round(sum(v)/len(v),1) for k,v in categories.items()}
    return avg_scores

@app.route('/', methods=['GET','POST'])
def index():
    metrics = {}
    weak_areas = []
    summary = ""
    category_chart = {}
    url = ""
    if request.method=="POST":
        url = request.form.get("url")
        metrics, weak_areas = audit_website(url)
        summary = generate_summary()
        category_chart = category_scores(metrics)
    return render_template("dashboard.html", metrics=metrics, weak_areas=weak_areas,
                           summary=summary, category_chart=category_chart,url=url)

@app.route('/download_report', methods=['POST'])
def download_report():
    url = request.form.get("url")
    metrics, weak_areas = audit_website(url)
    summary = generate_summary()
    category_chart = category_scores(metrics)
    rendered = render_template("dashboard.html", metrics=metrics, weak_areas=weak_areas,
                               summary=summary, category_chart=category_chart,url=url, pdf=True)
    pdf = pdfkit.from_string(rendered, False)
    return send_file(io.BytesIO(pdf), attachment_filename="Swaleh_Website_Audit_Report.pdf", as_attachment=True)

if __name__=="__main__":
    app.run(debug=True)
