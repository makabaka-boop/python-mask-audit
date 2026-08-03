from __future__ import annotations
import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Rule

VALID_MATCH_TYPES = ("exact", "contains", "regex")
VALID_REPLACE_STRATEGIES = ("fixed", "keep_edges", "middle_mask")


def _validate_rule_fields(match_type: str, match_value: str, replace_strategy: str) -> None:
    if match_type not in VALID_MATCH_TYPES:
        raise ValueError(f"match_type must be one of {VALID_MATCH_TYPES}, got '{match_type}'")
    if replace_strategy not in VALID_REPLACE_STRATEGIES:
        raise ValueError(
            f"replace_strategy must be one of {VALID_REPLACE_STRATEGIES}, "
            f"got '{replace_strategy}'"
        )
    if not match_value or not str(match_value).strip():
        raise ValueError("match_value must not be empty")
    if match_type == "regex":
        try:
            re.compile(match_value)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc


def _serialize_replace_config(replace_config) -> str:
    if replace_config is None:
        return "{}"
    if isinstance(replace_config, str):
        return replace_config
    return json.dumps(replace_config, ensure_ascii=False)


class RuleRepository:

    @staticmethod
    def create(db: Session, **kwargs) -> Rule:
        match_type = kwargs.get("match_type", "")
        match_value = kwargs.get("match_value", "")
        replace_strategy = kwargs.get("replace_strategy", "")
        _validate_rule_fields(match_type, match_value, replace_strategy)

        if "replace_config" in kwargs:
            kwargs["replace_config"] = _serialize_replace_config(kwargs["replace_config"])

        now = datetime.utcnow()
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)

        rule = Rule(**kwargs)
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def get_by_id(db: Session, rule_id: int) -> Rule | None:
        return db.query(Rule).filter(Rule.id == rule_id).first()

    @staticmethod
    def list_all(db: Session, enabled_only: bool = False) -> list[Rule]:
        query = db.query(Rule)
        if enabled_only:
            query = query.filter(Rule.enabled.is_(True))
        return query.order_by(Rule.priority.asc(), Rule.id.asc()).all()

    @staticmethod
    def update(db: Session, rule_id: int, **kwargs) -> Rule | None:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if rule is None:
            return None

        match_type = kwargs.get("match_type", rule.match_type)
        match_value = kwargs.get("match_value", rule.match_value)
        replace_strategy = kwargs.get("replace_strategy", rule.replace_strategy)
        _validate_rule_fields(match_type, match_value, replace_strategy)

        if "replace_config" in kwargs:
            kwargs["replace_config"] = _serialize_replace_config(kwargs["replace_config"])

        kwargs["updated_at"] = datetime.utcnow()

        for key, value in kwargs.items():
            setattr(rule, key, value)

        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def delete(db: Session, rule_id: int) -> bool:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if rule is None:
            return False
        db.delete(rule)
        db.commit()
        return True

    @staticmethod
    def set_enabled(db: Session, rule_id: int, enabled: bool) -> Rule | None:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if rule is None:
            return None
        rule.enabled = enabled
        rule.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def set_priority(db: Session, rule_id: int, priority: int) -> Rule | None:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if rule is None:
            return None
        rule.priority = priority
        rule.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def get_by_ids(db: Session, rule_ids: list[int]) -> list[Rule]:
        if not rule_ids:
            return []
        return db.query(Rule).filter(Rule.id.in_(rule_ids)).all()
