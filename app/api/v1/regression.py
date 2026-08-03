from __future__ import annotations
"""回归验证接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.audit import AuditHelper
from app.core.errors import NotFoundError, ValidationError
from app.core.snapshot import SnapshotService
from app.database import get_db
from app.repositories.group_repo import GroupRepository
from app.repositories.rule_repo import RuleRepository
from app.repositories.run_repo import RunRepository
from app.repositories.sample_repo import SampleRepository
from app.repositories.snapshot_repo import SnapshotRepository
from app.schemas.conflict import (
    DiffDetail,
    ReplayRegressionRequest,
    ReplayRegressionResponse,
)
from app.schemas.run import RegressionResult
from app.services.executor import RuleExecutor

router = APIRouter()


@router.get("/group/{group_id}", response_model=RegressionResult)
def regression_check(group_id: int, db: Session = Depends(get_db)):
    group = GroupRepository.get_by_id(db, group_id)
    if group is None:
        raise NotFoundError(f"分组 {group_id} 不存在")

    snapshot = SnapshotRepository.get_latest_by_group(db, group_id)
    if snapshot is None:
        raise ValidationError(f"分组 {group_id} 没有可用于回归比较的快照")

    current_rules = GroupRepository.get_rules(db, group_id, enabled_only=False)
    current_rule_dicts = [r.to_dict() for r in current_rules]

    comparison = SnapshotService.compare_snapshot(db, snapshot.id, current_rule_dicts)

    AuditHelper.log_event(db, AuditHelper.REGRESSION, "group", group_id,
                          {"snapshot_id": snapshot.id,
                           "is_passed": comparison["is_passed"],
                           "changed": comparison["rules_changed"],
                           "added": comparison["rules_added"],
                           "removed": comparison["rules_removed"]})

    return RegressionResult(
        snapshot_id=snapshot.id,
        group_id=group_id,
        rules_changed=comparison["rules_changed"],
        rules_added=comparison["rules_added"],
        rules_removed=comparison["rules_removed"],
        rules_unchanged=comparison["rules_unchanged"],
        is_passed=comparison["is_passed"],
    )


@router.get("/snapshot/{snapshot_id}", response_model=RegressionResult)
def regression_by_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    snapshot = SnapshotRepository.get_by_id(db, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"快照 {snapshot_id} 不存在")

    if snapshot.group_id is None:
        raise ValidationError("该快照未关联分组，无法自动比较")

    current_rules = GroupRepository.get_rules(db, snapshot.group_id, enabled_only=False)
    current_rule_dicts = [r.to_dict() for r in current_rules]

    comparison = SnapshotService.compare_snapshot(db, snapshot_id, current_rule_dicts)

    AuditHelper.log_event(db, AuditHelper.REGRESSION, "snapshot", snapshot_id,
                          {"is_passed": comparison["is_passed"]})

    return RegressionResult(
        snapshot_id=snapshot_id,
        group_id=snapshot.group_id,
        rules_changed=comparison["rules_changed"],
        rules_added=comparison["rules_added"],
        rules_removed=comparison["rules_removed"],
        rules_unchanged=comparison["rules_unchanged"],
        is_passed=comparison["is_passed"],
    )


@router.post("/replay", response_model=ReplayRegressionResponse)
def replay_regression(payload: ReplayRegressionRequest,
                      db: Session = Depends(get_db)):
    group = GroupRepository.get_by_id(db, payload.group_id)
    if group is None:
        raise NotFoundError(f"分组 {payload.group_id} 不存在")

    sample = SampleRepository.get_by_id(db, payload.sample_id)
    if sample is None:
        raise NotFoundError(f"样例 {payload.sample_id} 不存在")

    historical_run = RunRepository.get_latest_by_sample_group(
        db, payload.sample_id, payload.group_id
    )
    if historical_run is None:
        raise ValidationError(
            f"样例 {payload.sample_id} 在分组 {payload.group_id} 下没有历史演练记录"
        )
    if historical_run.snapshot_id is None:
        raise ValidationError("历史演练记录未关联规则快照，无法进行回放回归")

    snapshot = SnapshotRepository.get_by_id(db, historical_run.snapshot_id)
    if snapshot is None:
        raise ValidationError(
            f"历史快照 {historical_run.snapshot_id} 不存在"
        )

    current_rules = GroupRepository.get_rules(db, payload.group_id, enabled_only=True)
    current_rule_dicts = [r.to_dict() for r in current_rules]

    current_result = RuleExecutor.execute_group(sample.raw_text, current_rule_dicts)

    historical_output = historical_run.output_text
    current_output = current_result["output_text"]
    is_consistent = historical_output == current_output

    all_current_rules = GroupRepository.get_rules(
        db, payload.group_id, enabled_only=False
    )
    all_current_dicts = [r.to_dict() for r in all_current_rules]

    detailed = SnapshotService.compare_snapshot_detailed(
        db, snapshot.id, all_current_dicts
    )

    diff_reasons: list[str] = []
    if detailed["rules_added"]:
        diff_reasons.append(
            "分组成员变化：新增规则 " + ", ".join(str(r) for r in detailed["rules_added"])
        )
    if detailed["rules_removed"]:
        diff_reasons.append(
            "分组成员变化：移除规则 " + ", ".join(str(r) for r in detailed["rules_removed"])
        )

    classified = SnapshotService.classify_diff_reasons(detailed["rules_changed"])
    diff_reasons.extend(classified)

    if is_consistent and diff_reasons:
        diff_reasons.append("规则存在差异但本次样例输出一致（差异未影响此样例）")

    if not is_consistent and not diff_reasons:
        diff_reasons.append("输出不一致但未检测到规则配置差异，可能由执行环境或规则顺序引起")

    AuditHelper.log_event(
        db, AuditHelper.REGRESSION_REPLAY, "group", payload.group_id,
        {
            "sample_id": payload.sample_id,
            "snapshot_id": snapshot.id,
            "run_id": historical_run.id,
            "is_consistent": is_consistent,
            "diff_reasons": diff_reasons,
        },
    )

    changed_details = [
        DiffDetail(
            rule_id=c["rule_id"],
            rule_name=c.get("rule_name", ""),
            diff_fields=c["diff_fields"],
        )
        for c in detailed["rules_changed"]
    ]

    return ReplayRegressionResponse(
        sample_id=payload.sample_id,
        group_id=payload.group_id,
        snapshot_id=snapshot.id,
        run_id=historical_run.id,
        historical_output=historical_output,
        current_output=current_output,
        is_consistent=is_consistent,
        diff_reasons=diff_reasons,
        rules_added=detailed["rules_added"],
        rules_removed=detailed["rules_removed"],
        rules_changed=changed_details,
        rules_unchanged=detailed["rules_unchanged"],
    )
