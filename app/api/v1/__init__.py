"""API v1 路由汇总。"""
from fastapi import APIRouter

from app.api.v1 import health, rules, groups, samples, runs, preview, regression, snapshots, conflicts, audit, consistency

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(rules.router, prefix="/rules", tags=["rules"])
api_router.include_router(groups.router, prefix="/groups", tags=["groups"])
api_router.include_router(samples.router, prefix="/samples", tags=["samples"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(preview.router, prefix="/preview", tags=["preview"])
api_router.include_router(regression.router, prefix="/regression", tags=["regression"])
api_router.include_router(snapshots.router, prefix="/snapshots", tags=["snapshots"])
api_router.include_router(conflicts.router, prefix="/conflicts", tags=["conflicts"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(consistency.router, prefix="/consistency", tags=["consistency"])
