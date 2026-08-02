"""测试套件入口，统一配置临时数据库。"""
import os
import tempfile

import pytest


@pytest.fixture()
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.environ["MASK_AUDIT_DB"] = db_path

    from app.config import Config
    from app.main import create_app

    class TestConfig(Config):
        DATABASE_PATH = db_path
        TESTING = True

    app = create_app(TestConfig)

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture()
def client(app):
    return app.test_client()
