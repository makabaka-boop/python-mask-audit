from __future__ import annotations
"""审计日志辅助工具。"""
from app.models.audit import AuditEvent
from app.repositories.audit_repo import AuditRepository


class AuditHelper:

    RULE_CREATE = "RULE_CREATE"
    RULE_UPDATE = "RULE_UPDATE"
    RULE_ENABLE = "RULE_ENABLE"
    RULE_DISABLE = "RULE_DISABLE"
    RULE_PRIORITY = "RULE_PRIORITY"
    GROUP_CREATE = "GROUP_CREATE"
    GROUP_UPDATE = "GROUP_UPDATE"
    GROUP_DELETE = "GROUP_DELETE"
    GROUP_ADD_RULE = "GROUP_ADD_RULE"
    GROUP_REMOVE_RULE = "GROUP_REMOVE_RULE"
    SAMPLE_CREATE = "SAMPLE_CREATE"
    SAMPLE_UPDATE = "SAMPLE_UPDATE"
    SAMPLE_DELETE = "SAMPLE_DELETE"
    RUN_SINGLE = "RUN_SINGLE"
    RUN_GROUP = "RUN_GROUP"
    PREVIEW = "PREVIEW"
    REGRESSION = "REGRESSION"
    REGRESSION_REPLAY = "REGRESSION_REPLAY"
    CONFLICT_DETECT = "CONFLICT_DETECT"
    CONSISTENCY_CHECK = "CONSISTENCY_CHECK"

    @staticmethod
    def log_event(
        db,
        event_type: str,
        target_type: str = "",
        target_id: int | None = None,
        detail: dict | None = None,
    ) -> AuditEvent:
        return AuditRepository.log(
            db,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
