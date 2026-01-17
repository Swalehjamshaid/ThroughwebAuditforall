from fastapi import APIRouter
from ..schemas import CompetitorRequest
from ..audit.metrics import compute_metrics
from ..audit.scoring import score_category, overall_score, letter_grade

router = APIRouter(prefix='/api', tags=['competitor'])

@router.post('/competitor')
async def competitor_compare(payload: CompetitorRequest):
    def audit(url:str):
        m = compute_metrics(url)
        s = score_category(m)
        return {'url': url, 'scores': {**s, 'overall': overall_score(s), 'grade': letter_grade(overall_score(s))}, 'metrics': m}
    main = audit(payload.main_url)
    rivals = [audit(u) for u in payload.competitors]
    return { 'main': main, 'competitors': rivals }
