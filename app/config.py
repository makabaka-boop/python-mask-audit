"""应用配置。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    DATABASE_PATH = os.environ.get(
        "MASK_AUDIT_DB", os.path.join(BASE_DIR, "mask_audit.db")
    )
    HOST = os.environ.get("MASK_AUDIT_HOST", "0.0.0.0")
    PORT = int(os.environ.get("MASK_AUDIT_PORT", "18105"))
    DEBUG = os.environ.get("MASK_AUDIT_DEBUG", "0") == "1"
