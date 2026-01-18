
from typing import Dict, Any

METRICS: Dict[int, Dict[str, Any]] = {}

def add(id, name, category, weight=1.0):
    METRICS[id] = {"id": id, "name": name, "category": category, "weight": weight}

# Populate metrics 1..200 (abbrev. with loops)
# A. Executive (1–10)
add(1, "Overall Site Health Score", "Executive", 2.0)
add(2, "Website Grade", "Executive", 2.0)
for i in range(3, 11):
    names = {
        3:"Executive Summary",4:"Strengths Highlight",5:"Weak Areas Highlight",6:"Priority Fixes",
        7:"Visual Severity Indicators",8:"Category Score Breakdown",9:"Industry-Standard Presentation",10:"Certified Export Readiness"
    }
    add(i, names[i], "Executive", 0.5)

# B. Health (11–20)
for i, name in [
 (11,'Site Health Score'),(12,'Total Errors'),(13,'Total Warnings'),(14,'Total Notices'),
 (15,'Total Crawled Pages'),(16,'Total Indexed Pages'),(17,'Issues Trend'),(18,'Crawl Budget Efficiency'),
 (19,'Orphan Pages Percentage'),(20,'Audit Completion Status')]:
    add(i, name, "Health", 1.0)

# C. Crawlability (21–40)
labels_c = ['HTTP 2xx Pages','HTTP 3xx Pages','HTTP 4xx Pages','HTTP 5xx Pages','Redirect Chains','Redirect Loops',
 'Broken Internal Links','Broken External Links','robots.txt Blocked URLs','Meta Robots Blocked URLs','Non-Canonical Pages','Missing Canonical Tags',
 'Incorrect Canonical Tags','Sitemap Missing Pages','Sitemap Not Crawled Pages','Hreflang Errors','Hreflang Conflicts','Pagination Issues','Crawl Depth Distribution','Duplicate Parameter URLs']
for idx, name in enumerate(labels_c, start=21):
    add(idx, name, 'Crawlability', 1.0)

# D. On-Page (41–75)
labels_d = ['Missing Title Tags','Duplicate Title Tags','Title Too Long','Title Too Short','Missing Meta Descriptions','Duplicate Meta Descriptions','Meta Too Long','Meta Too Short','Missing H1','Multiple H1','Duplicate Headings','Thin Content Pages','Duplicate Content Pages','Low Text-to-HTML Ratio','Missing Image Alt Tags','Duplicate Alt Tags','Large Uncompressed Images','Pages Without Indexed Content','Missing Structured Data','Structured Data Errors','Rich Snippet Warnings','Missing Open Graph Tags','Long URLs','Uppercase URLs','Non-SEO-Friendly URLs','Too Many Internal Links','Pages Without Incoming Links','Orphan Pages','Broken Anchor Links','Redirected Internal Links','NoFollow Internal Links','Link Depth Issues','External Links Count','Broken External Links','Anchor Text Issues']
for idx, name in enumerate(labels_d, start=41):
    add(idx, name, 'OnPage', 1.0)

# E. Performance (76–96)
labels_e = ['Largest Contentful Paint (LCP)','First Contentful Paint (FCP)','Cumulative Layout Shift (CLS)','Total Blocking Time','First Input Delay','Speed Index','Time to Interactive','DOM Content Loaded','Total Page Size','Requests Per Page','Unminified CSS','Unminified JavaScript','Render Blocking Resources','Excessive DOM Size','Third-Party Script Load','Server Response Time','Image Optimization','Lazy Loading Issues','Browser Caching Issues','Missing GZIP / Brotli','Resource Load Errors']
for idx, name in enumerate(labels_e, start=76):
    add(idx, name, 'Performance', 1.0)

# F. Mobile/Security/International (97–150)
labels_f = ['Mobile Friendly Test','Viewport Meta Tag','Small Font Issues','Tap Target Issues','Mobile Core Web Vitals','Mobile Layout Issues','Intrusive Interstitials','Mobile Navigation Issues','HTTPS Implementation','SSL Certificate Validity','Expired SSL','Mixed Content','Insecure Resources','Missing Security Headers','Open Directory Listing','Login Pages Without HTTPS','Missing Hreflang','Incorrect Language Codes','Hreflang Conflicts','Region Targeting Issues','Multi-Domain SEO Issues','Domain Authority','Referring Domains','Total Backlinks','Toxic Backlinks','NoFollow Backlinks','Anchor Distribution','Referring IPs','Lost / New Backlinks','JavaScript Rendering Issues','CSS Blocking','Crawl Budget Waste','AMP Issues','PWA Issues','Canonical Conflicts','Subdomain Duplication','Pagination Conflicts','Dynamic URL Issues','Lazy Load Conflicts','Sitemap Presence','Noindex Issues','Structured Data Consistency','Redirect Correctness','Broken Rich Media','Social Metadata Presence','Error Trend','Health Trend','Crawl Trend','Index Trend','Core Web Vitals Trend','Backlink Trend','Keyword Trend','Historical Comparison','Overall Stability Index']
for idx, name in enumerate(labels_f, start=97):
    add(idx, name, 'MobileSecurityIntl', 1.0)

# G. Competitors (151–167)
labels_g = ['Competitor Health Score','Competitor Performance Comparison','Competitor Core Web Vitals Comparison','Competitor SEO Issues Comparison','Competitor Broken Links Comparison','Competitor Authority Score','Competitor Backlink Growth','Competitor Keyword Visibility','Competitor Rank Distribution','Competitor Content Volume','Competitor Speed Comparison','Competitor Mobile Score','Competitor Security Score','Competitive Gap Score','Competitive Opportunity Heatmap','Competitive Risk Heatmap','Overall Competitive Rank']
for idx, name in enumerate(labels_g, start=151):
    add(idx, name, 'Competitors', 0.8)

# H. Broken Links (168–180)
labels_h = ['Total Broken Links','Internal Broken Links','External Broken Links','Broken Links Trend','Broken Pages by Impact','Status Code Distribution','Page Type Distribution','Fix Priority Score','SEO Loss Impact','Affected Pages Count','Broken Media Links','Resolution Progress','Risk Severity Index']
for idx, name in enumerate(labels_h, start=168):
    add(idx, name, 'BrokenLinks', 1.0)

# I. Opportunities (181–200)
labels_i = ['High Impact Opportunities','Quick Wins Score','Long-Term Fixes','Traffic Growth Forecast','Ranking Growth Forecast','Conversion Impact Score','Content Expansion Opportunities','Internal Linking Opportunities','Speed Improvement Potential','Mobile Improvement Potential','Security Improvement Potential','Structured Data Opportunities','Crawl Optimization Potential','Backlink Opportunity Score','Competitive Gap ROI','Fix Roadmap Timeline','Time-to-Fix Estimate','Cost-to-Fix Estimate','ROI Forecast','Overall Growth Readiness']
for idx, name in enumerate(labels_i, start=181):
    add(idx, name, 'Opportunities', 0.9)
