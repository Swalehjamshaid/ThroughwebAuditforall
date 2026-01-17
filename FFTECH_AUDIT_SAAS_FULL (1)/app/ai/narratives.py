from typing import Dict, Any
import requests
from ..config import get_settings

GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent'
PROMPT = (
    "You are a senior SEO and web performance analyst. Given the JSON metrics and category scores, "
    "write a crisp executive summary (~200 words), list top 3 strengths and top 3 weaknesses, and "
    "recommend 3 priority fixes (action oriented). Keep tone executive, specific, and constructive."
)

def _format_input(url: str, metrics: Dict[str, Any], scores: Dict[str, float]) -> Dict[str, Any]:
    return {'contents':[{'parts':[{'text':PROMPT},{'text':f'TARGET URL: {url}'},{'text':f'SCORES: {scores}'},{'text':f'METRICS: {metrics}'}]}]}


def generate_narrative(url: str, metrics: Dict[str, Any], scores: Dict[str, float]) -> Dict[str, Any]:
    key = get_settings().GEMINI_API_KEY
    if not key:
        strengths = [f"{k}: {v:.1f}" for k,v in sorted(scores.items(), key=lambda x:x[1], reverse=True)[:3]]
        weaknesses = [f"{k}: {v:.1f}" for k,v in sorted(scores.items(), key=lambda x:x[1])[:3]]
        return {
            'summary': 'This audit evaluates technical health, crawlability, on-page SEO, and performance. Address the noted weak areas and prioritize quick wins to raise overall quality and stability.',
            'strengths': strengths,
            'weaknesses': weaknesses,
            'priorities': [w.split(':')[0] for w in weaknesses]
        }
    try:
        r = requests.post(GEMINI_URL, params={'key': key}, json=_format_input(url, metrics, scores), timeout=45)
        data = r.json()
        text = data['candidates'][0]['content']['parts'][0]['text'] if r.status_code==200 else None
        strengths = [f"{k}: {v:.1f}" for k,v in sorted(scores.items(), key=lambda x:x[1], reverse=True)[:3]]
        weaknesses = [f"{k}: {v:.1f}" for k,v in sorted(scores.items(), key=lambda x:x[1])[:3]]
        return {'summary': text or 'Executive summary unavailable.', 'strengths': strengths, 'weaknesses': weaknesses, 'priorities': [w.split(':')[0] for w in weaknesses]}
    except Exception:
        return generate_narrative(url, metrics, scores)
