from __future__ import annotations
from sqlalchemy.orm import Session

from app.models import GroupMember, Rule, RuleGroup


class GroupRepository:

    @staticmethod
    def create(db: Session, group_name: str, description: str = "") -> RuleGroup:
        group = RuleGroup(group_name=group_name, description=description or "")
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    @staticmethod
    def get_by_id(db: Session, group_id: int) -> RuleGroup | None:
        return db.query(RuleGroup).filter(RuleGroup.id == group_id).first()

    @staticmethod
    def list_all(db: Session) -> list[RuleGroup]:
        return db.query(RuleGroup).order_by(RuleGroup.id.asc()).all()

    @staticmethod
    def update(db: Session, group_id: int, **kwargs) -> RuleGroup | None:
        group = db.query(RuleGroup).filter(RuleGroup.id == group_id).first()
        if group is None:
            return None
        for key, value in kwargs.items():
            setattr(group, key, value)
        db.commit()
        db.refresh(group)
        return group

    @staticmethod
    def delete(db: Session, group_id: int) -> bool:
        group = db.query(RuleGroup).filter(RuleGroup.id == group_id).first()
        if group is None:
            return False
        db.delete(group)
        db.commit()
        return True

    @staticmethod
    def add_rule(db: Session, group_id: int, rule_id: int) -> GroupMember:
        existing = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == group_id, GroupMember.rule_id == rule_id)
            .first()
        )
        if existing is not None:
            raise ValueError(
                f"Rule {rule_id} is already a member of group {group_id}"
            )
        member = GroupMember(group_id=group_id, rule_id=rule_id)
        db.add(member)
        db.commit()
        db.refresh(member)
        return member

    @staticmethod
    def remove_rule(db: Session, group_id: int, rule_id: int) -> bool:
        member = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == group_id, GroupMember.rule_id == rule_id)
            .first()
        )
        if member is None:
            return False
        db.delete(member)
        db.commit()
        return True

    @staticmethod
    def get_rules(db: Session, group_id: int, enabled_only: bool = False) -> list[Rule]:
        query = (
            db.query(Rule)
            .join(GroupMember, GroupMember.rule_id == Rule.id)
            .filter(GroupMember.group_id == group_id)
        )
        if enabled_only:
            query = query.filter(Rule.enabled.is_(True))
        return query.order_by(Rule.priority.asc(), Rule.id.asc()).all()

    @staticmethod
    def get_member(db: Session, group_id: int, rule_id: int) -> GroupMember | None:
        return (
            db.query(GroupMember)
            .filter(GroupMember.group_id == group_id, GroupMember.rule_id == rule_id)
            .first()
        )

    @staticmethod
    def list_members(db: Session, group_id: int) -> list[GroupMember]:
        return (
            db.query(GroupMember)
            .filter(GroupMember.group_id == group_id)
            .order_by(GroupMember.id.asc())
            .all()
        )
