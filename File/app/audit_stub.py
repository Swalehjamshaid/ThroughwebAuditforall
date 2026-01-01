
import random

def stub_open_metrics(url):
    score=round(random.uniform(5.0,9.8),2)
    grade='A+' if score>=9.5 else 'A' if score>=8.5 else 'B' if score>=7.0 else 'C' if score>=5.5 else 'D'
    return {
        'site_health': {'score':score,'errors':random.randint(0,25),'warnings':random.randint(5,60),'notices':random.randint(10,100),'grade':grade},
        'highlights':['Missing alt texts on several images','Unminified CSS/JS increasing load time','Potential redirect chain detected','Improve meta descriptions and titles'],
        'recommendations':['Compress and lazy-load large images','Fix broken internal/external links','Add canonical tags consistently','Enable GZIP/Brotli and browser caching']
    }
