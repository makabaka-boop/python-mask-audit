from __future__ import annotations
"""演练执行与查询接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.errors import NotFoundError, RuleDisabledError, ValidationError
from app.core.snapshot import SnapshotService
from app.database import get_db
from app.repositories.group_repo import GroupRepository
from app.repositories.rule_repo import RuleRepository
from app.repositories.run_repo import RunRepository
from app.repositories.sample_repo import SampleRepository
from app.schemas.run import (
    GroupRunRequest,
    SingleRuleRunRequest,
    RunDetailResponse,
    RunResponse,
    HitDetailResponse,
    RuleStats,
)
from app.services.executor import RuleExecutor

router = APIRouter()


def _resolve_input_text(sample_id: int | None, input_text: str | None,
                        db: Session) -> tuple[str, int | None]:
    if input_text is not None and input_text != "":
        return input_text, sample_id
    if sample_id is not None:
        sample = SampleRepository.get_by_id(db, sample_id)
        if sample is None:
            raise NotFoundError(f"样例 {sample_id} 不存在")
        return sample.raw_text, sample_id
    raise ValidationError("必须提供 sample_id 或 input_text")


@router.post("/single", response_model=RunDetailResponse, status_code=201)
def run_single_rule(payload: SingleRuleRunRequest, db: Session = Depends(get_db)):
    rule = RuleRepository.get_by_id(db, payload.rule_id)
    if rule is None:
        raise NotFoundError(f"规则 {payload.rule_id} 不存在")
    if not rule.enabled:
        raise RuleDisabledError(f"规则 {payload.rule_id} 已禁用，无法执行")

    input_text, sample_id = _resolve_input_text(payload.sample_id, payload.input_text, db)

    result = RuleExecutor.execute_single(input_text, rule.to_dict())

    run = RunRepository.create(
        db,
        sample_id=sample_id,
        rule_id=rule.id,
        group_id=None,
        input_text=input_text,
        output_text=result["output_text"],
        hit_count=result["hit_count"],
    )
    for hd in result["hit_details"]:
        RunRepository.add_hit_detail(
            db, run_id=run.id, rule_id=hd["rule_id"],
            matched_count=hd["matched_count"],
            before_fragment=hd["before_fragment"],
            after_fragment=hd["after_fragment"],
        )

    AuditHelper.log_event(db, AuditHelper.RUN_SINGLE, "run", run.id,
                          {"rule_id": rule.id, "hit_count": result["hit_count"]})

    hit_details = RunRepository.get_hit_details(db, run.id)
    resp = run.to_dict()
    resp["hit_details"] = [HitDetailResponse.model_validate(h.to_dict()) for h in hit_details]
    return RunDetailResponse.model_validate(resp)


@router.post("/group", response_model=RunDetailResponse, status_code=201)
def run_group(payload: GroupRunRequest, db: Session = Depends(get_db)):
    group = GroupRepository.get_by_id(db, payload.group_id)
    if group is None:
        raise NotFoundError(f"分组 {payload.group_id} 不存在")

    sample = SampleRepository.get_by_id(db, payload.sample_id)
    if sample is None:
        raise NotFoundError(f"样例 {payload.sample_id} 不存在")

    rules = GroupRepository.get_rules(db, payload.group_id, enabled_only=True)
    if not rules:
        raise ValidationError("分组中没有启用的规则")

    rule_dicts = [r.to_dict() for r in rules]

    snapshot = SnapshotService.create_snapshot(
        db, group_id=payload.group_id, rules=rule_dicts,
        label=f"run_group_{payload.sample_id}",
    )

    result = RuleExecutor.execute_group(sample.raw_text, rule_dicts)

    run = RunRepository.create(
        db,
        sample_id=payload.sample_id,
        rule_id=None,
        group_id=payload.group_id,
        input_text=sample.raw_text,
        output_text=result["output_text"],
        hit_count=result["hit_count"],
        snapshot_id=snapshot.id,
    )
    for hd in result["hit_details"]:
        RunRepository.add_hit_detail(
            db, run_id=run.id, rule_id=hd["rule_id"],
            matched_count=hd["matched_count"],
            before_fragment=hd["before_fragment"],
            after_fragment=hd["after_fragment"],
        )

    AuditHelper.log_event(db, AuditHelper.RUN_GROUP, "run", run.id,
                          {"group_id": payload.group_id,
                           "hit_count": result["hit_count"],
                           "snapshot_id": snapshot.id})

    hit_details = RunRepository.get_hit_details(db, run.id)
    resp = run.to_dict()
    resp["hit_details"] = [HitDetailResponse.model_validate(h.to_dict()) for h in hit_details]
    return RunDetailResponse.model_validate(resp)


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    run = RunRepository.get_by_id(db, run_id)
    if run is None:
        raise NotFoundError(f"演练记录 {run_id} 不存在")
    hit_details = RunRepository.get_hit_details(db, run_id)
    resp = run.to_dict()
    resp["hit_details"] = [HitDetailResponse.model_validate(h.to_dict()) for h in hit_details]
    return RunDetailResponse.model_validate(resp)


@router.get("", response_model=list[RunResponse])
def list_runs(sample_id: int | None = None, rule_id: int | None = None,
              group_id: int | None = None, limit: int = 50,
              db: Session = Depends(get_db)):
    if sample_id is not None:
        runs = RunRepository.list_by_sample(db, sample_id, limit=limit)
    elif rule_id is not None:
        runs = RunRepository.list_by_rule(db, rule_id, limit=limit)
    elif group_id is not None:
        runs = RunRepository.list_by_group(db, group_id, limit=limit)
    else:
        from app.models.run import RunRecord
        runs = db.query(RunRecord).order_by(
            RunRecord.executed_at.desc(), RunRecord.id.desc()
        ).limit(limit).all()
    return [RunResponse.model_validate(r.to_dict()) for r in runs]


@router.get("/stats/rules", response_model=list[RuleStats])
def rule_hit_stats(rule_id: int | None = None, db: Session = Depends(get_db)):
    if rule_id is not None:
        rule = RuleRepository.get_by_id(db, rule_id)
        if rule is None:
            raise NotFoundError(f"规则 {rule_id} 不存在")
        stats = RunRepository.get_rule_stats(db, rule_id)
        return [RuleStats(rule_id=rule_id, rule_name=rule.rule_name, **stats)]
    all_stats = RunRepository.list_all_rule_stats(db)
    result = []
    for s in all_stats:
        rule = RuleRepository.get_by_id(db, s["rule_id"])
        rule_name = rule.rule_name if rule else f"deleted_{s['rule_id']}"
        result.append(RuleStats(rule_id=s["rule_id"], rule_name=rule_name,
                                total_runs=s["total_runs"],
                                total_hits=s["total_hits"],
                                last_run_at=s["last_run_at"]))
    return result
