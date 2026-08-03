"""健康检查路由。"""
from flask import Blueprint, jsonify

from ..database import get_db

health_bp = Blueprint("health", __name__, url_prefix="/api/v1")


@health_bp.get("/health")
def health():
    db = get_db()
    db.execute("SELECT 1").fetchone()
    return jsonify({"status": "ok", "service": "mask-audit"})
