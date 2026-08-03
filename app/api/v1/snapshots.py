from __future__ import annotations
"""快照查询接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.repositories.snapshot_repo import SnapshotRepository

router = APIRouter()


@router.get("/{snapshot_id}")
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    snapshot = SnapshotRepository.get_by_id(db, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"快照 {snapshot_id} 不存在")
    items = SnapshotRepository.get_items(db, snapshot_id)
    return {
        "snapshot": snapshot.to_dict(),
        "items": [item.to_dict() for item in items],
    }


@router.get("")
def list_snapshots(group_id: int, limit: int = 20, db: Session = Depends(get_db)):
    snapshots = SnapshotRepository.list_by_group(db, group_id, limit=limit)
    return [s.to_dict() for s in snapshots]
