"""全局配置常量。"""

# 服务监听端口
HOST = "0.0.0.0"
PORT = 18105

# SQLite 数据库文件路径（可通过环境变量覆盖，方便测试）
import os

DB_PATH = os.environ.get("MASK_AUDIT_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "mask_audit.db"))

# 统一 API 前缀
API_PREFIX = "/api/v1"

# 允许的枚举取值
MATCH_TYPES = ("exact", "contains", "regex")
REPLACE_STRATEGIES = ("fixed", "keep_edges", "middle_mask")

# 默认脱敏掩码字符
DEFAULT_MASK_CHAR = "*"
