
from __future__ import annotations
from typing import Dict, Any, List, Optional
import json
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models import AuditRun, User
from ..services.config import FREE_AUDIT_LIMIT


def count_user_audits(session: Session, user_id: int) -> int:
    return session.scalar(select(func.count()).select_from(AuditRun).where(AuditRun.user_id == user_id)) or 0


def can_run_audit(session: Session, user: User) -> bool:
    if (user.plan or 'free') != 'free':
        return True
    return count_user_audits(session, user.id) < FREE_AUDIT_LIMIT


def save_audit(session: Session, user: Optional[User], url: str, result: Dict[str, Any], graphs: List[str], pdf_path: str | None) -> AuditRun:
    run = AuditRun(
        user_id=user.id if user else None,
        url=url,
        score=int(result.get('score', 0)),
        grade=str(result.get('grade', 'D')),
        metrics_json=json.dumps(result.get('metrics', {})),
        pdf_path=pdf_path,
        graphs_json=json.dumps(graphs),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def list_user_runs(session: Session, user: User, limit: int = 25) -> List[AuditRun]:
    stmt = select(AuditRun).where(AuditRun.user_id == user.id).order_by(AuditRun.created_at.desc()).limit(limit)
    return session.execute(stmt).scalars().all()

