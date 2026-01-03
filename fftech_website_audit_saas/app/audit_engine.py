from typing import Dict
import requests
from bs4 import BeautifulSoup

def strict_score(metrics: Dict) -> (int, str):
    # Weights for international standards
    category_weights = {
        "Security & HTTPS": 0.25,
        "Technical & Performance": 0.20,
        "On-Page SEO": 0.20,
        "Crawlability": 0.15,
        "Mobile & Usability": 0.15,
        "Accessibility": 0.05
    }
    
    # Calculate weighted score logic...
    score = 85 # Example calculated score
    
    # Strict Security Check: Any critical security issue prevents an "A" grade
    sec = metrics["categories"].get("Security & HTTPS", {})
    if any(v.get("status") == "critical" for v in sec.values()):
        grade = "B" if score >= 70 else "D"
    else:
        if score >= 95: grade = "A+"
        elif score >= 85: grade = "A"
        elif score >= 70: grade = "B"
        else: grade = "D"
        
    return score, grade

def generate_summary_200(metrics: Dict, score: int, grade: str) -> str:
    # Logic to summarize the top 3 weaknesses and strengths in 200 words
    return f"This audit assigns a grade of {grade}... [200 word summary here]"
