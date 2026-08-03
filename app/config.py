"""应用配置。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = os.environ.get("MASK_AUDIT_DB", str(BASE_DIR / "mask_audit.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

HOST = os.environ.get("MASK_AUDIT_HOST", "0.0.0.0")
PORT = int(os.environ.get("MASK_AUDIT_PORT", "18105"))

API_V1_PREFIX = "/api/v1"
