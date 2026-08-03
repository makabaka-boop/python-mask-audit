"""脱敏规则沙盒服务 (mask-audit)。

纯标准库实现的后端脱敏规则沙盒，用于在接触真实业务数据前，
基于样例文本验证脱敏规则的稳定性、可重复性与可追踪性。
"""

__all__ = ["config", "db", "errors", "strategies", "executor", "snapshot", "repositories", "audit_queries", "selfcheck", "routes", "server"]
