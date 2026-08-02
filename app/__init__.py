"""脱敏规则沙盒服务包。"""

from flask import Flask

from .database import Database
from .errors import register_error_handlers
from .routes import api_blueprint


def create_app(db_path: str = "mask_audit.db") -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False

    db = Database(db_path)
    db.init_schema()
    app.extensions["db"] = db

    register_error_handlers(app)
    app.register_blueprint(api_blueprint)
    return app
