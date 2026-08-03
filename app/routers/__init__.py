"""路由蓝图。"""
from .health import health_bp
from .rules import rules_bp
from .groups import groups_bp
from .samples import samples_bp
from .runs import runs_bp
from .preview import preview_bp
from .regression import regression_bp
from .stats import stats_bp
from .audit import audit_bp
from .consistency import consistency_bp

ALL_BLUEPRINTS = [
    health_bp,
    rules_bp,
    groups_bp,
    samples_bp,
    runs_bp,
    preview_bp,
    regression_bp,
    stats_bp,
    audit_bp,
    consistency_bp,
]
