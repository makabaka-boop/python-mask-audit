from __future__ import annotations
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import HitDetail, RunRecord


class RunRepository:

    @staticmethod
    def create(
        db: Session,
        sample_id: int,
        rule_id: int,
        group_id: int,
        input_text: str,
        output_text: str,
        hit_count: int,
        snapshot_id: int | None = None,
    ) -> RunRecord:
        record = RunRecord(
            sample_id=sample_id,
            rule_id=rule_id,
            group_id=group_id,
            input_text=input_text,
            output_text=output_text,
            hit_count=hit_count,
            snapshot_id=snapshot_id,
            executed_at=datetime.utcnow(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_by_id(db: Session, run_id: int) -> RunRecord | None:
        return db.query(RunRecord).filter(RunRecord.id == run_id).first()

    @staticmethod
    def add_hit_detail(
        db: Session,
        run_id: int,
        rule_id: int,
        matched_count: int,
        before_fragment: str,
        after_fragment: str,
    ) -> HitDetail:
        detail = HitDetail(
            run_id=run_id,
            rule_id=rule_id,
            matched_count=matched_count,
            before_fragment=before_fragment or "",
            after_fragment=after_fragment or "",
        )
        db.add(detail)
        db.commit()
        db.refresh(detail)
        return detail

    @staticmethod
    def get_hit_details(db: Session, run_id: int) -> list[HitDetail]:
        return (
            db.query(HitDetail)
            .filter(HitDetail.run_id == run_id)
            .order_by(HitDetail.id.asc())
            .all()
        )

    @staticmethod
    def list_by_sample(db: Session, sample_id: int, limit: int = 50) -> list[RunRecord]:
        return (
            db.query(RunRecord)
            .filter(RunRecord.sample_id == sample_id)
            .order_by(RunRecord.executed_at.desc(), RunRecord.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def list_by_rule(db: Session, rule_id: int, limit: int = 50) -> list[RunRecord]:
        return (
            db.query(RunRecord)
            .filter(RunRecord.rule_id == rule_id)
            .order_by(RunRecord.executed_at.desc(), RunRecord.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def list_by_group(db: Session, group_id: int, limit: int = 50) -> list[RunRecord]:
        return (
            db.query(RunRecord)
            .filter(RunRecord.group_id == group_id)
            .order_by(RunRecord.executed_at.desc(), RunRecord.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_latest_by_sample_group(db: Session, sample_id: int,
                                   group_id: int) -> "RunRecord | None":
        return (
            db.query(RunRecord)
            .filter(
                RunRecord.sample_id == sample_id,
                RunRecord.group_id == group_id,
            )
            .order_by(RunRecord.executed_at.desc(), RunRecord.id.desc())
            .first()
        )

    @staticmethod
    def get_rule_stats(db: Session, rule_id: int) -> dict:
        row = (
            db.query(
                func.count(HitDetail.id).label("total_runs"),
                func.coalesce(func.sum(HitDetail.matched_count), 0).label("total_hits"),
                func.max(RunRecord.executed_at).label("last_run_at"),
            )
            .join(RunRecord, RunRecord.id == HitDetail.run_id)
            .filter(HitDetail.rule_id == rule_id)
            .first()
        )
        return {
            "rule_id": rule_id,
            "total_runs": row.total_runs if row else 0,
            "total_hits": int(row.total_hits) if row and row.total_hits is not None else 0,
            "last_run_at": row.last_run_at if row else None,
        }

    @staticmethod
    def list_all_rule_stats(db: Session) -> list[dict]:
        rows = (
            db.query(
                HitDetail.rule_id.label("rule_id"),
                func.count(HitDetail.id).label("total_runs"),
                func.coalesce(func.sum(HitDetail.matched_count), 0).label("total_hits"),
                func.max(RunRecord.executed_at).label("last_run_at"),
            )
            .join(RunRecord, RunRecord.id == HitDetail.run_id)
            .filter(HitDetail.rule_id.isnot(None))
            .group_by(HitDetail.rule_id)
            .all()
        )
        return [
            {
                "rule_id": row.rule_id,
                "total_runs": row.total_runs,
                "total_hits": int(row.total_hits) if row.total_hits is not None else 0,
                "last_run_at": row.last_run_at,
            }
            for row in rows
        ]

    @staticmethod
    def get_hit_distribution_by_sample(db: Session, sample_id: int) -> list[dict]:
        rows = (
            db.query(
                HitDetail.rule_id.label("rule_id"),
                func.coalesce(func.sum(HitDetail.matched_count), 0).label("total_hits"),
                func.count(HitDetail.id).label("hit_count"),
                func.max(RunRecord.executed_at).label("last_hit_at"),
            )
            .join(RunRecord, RunRecord.id == HitDetail.run_id)
            .filter(RunRecord.sample_id == sample_id)
            .filter(HitDetail.rule_id.isnot(None))
            .group_by(HitDetail.rule_id)
            .all()
        )
        return [
            {
                "rule_id": row.rule_id,
                "total_hits": int(row.total_hits) if row.total_hits is not None else 0,
                "hit_count": row.hit_count,
                "last_hit_at": row.last_hit_at,
            }
            for row in rows
        ]
