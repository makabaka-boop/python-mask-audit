"""统计与审计路由。"""
from flask import Blueprint, jsonify, request

from ..repositories import AuditRepository
from ..services import MaskService

stats_bp = Blueprint("stats", __name__, url_prefix="/api/v1")


@stats_bp.get("/stats/hits")
def hit_stats():
    return jsonify(MaskService().stats())


@stats_bp.get("/audit/events")
def audit_events():
    limit = request.args.get("limit", default=100, type=int)
    events = AuditRepository().list(limit=limit)
    return jsonify({"items": events, "total": len(events)})
