from __future__ import annotations
"""一致性自检接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.consistency import ConsistencyChecker
from app.database import get_db
from app.schemas.consistency import CheckItem, ConsistencyReport

router = APIRouter()


@router.get("", response_model=ConsistencyReport)
def run_consistency_check(db: Session = Depends(get_db)):
    report = ConsistencyChecker.run_all_checks(db)

    AuditHelper.log_event(
        db, "CONSISTENCY_CHECK", "system", None,
        {"all_passed": report["all_passed"],
         "total_issues": report["total_issues"],
         "checks": [c["check_name"] for c in report["checks"]]},
    )

    return ConsistencyReport(
        all_passed=report["all_passed"],
        total_issues=report["total_issues"],
        checks=[CheckItem(**c) for c in report["checks"]],
    )
