"""应用工厂与启动入口。"""
from __future__ import annotations

import os

from flask import Flask, jsonify

from .config import Config
from .database import init_app as init_db_app
from .database import init_db
from .errors import register_error_handlers
from .routers import ALL_BLUEPRINTS


def create_app(config: object = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

    init_db_app(app)
    register_error_handlers(app)

    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)

    @app.get("/")
    def index():
        return jsonify(
            {
                "service": "mask-audit",
                "version": "1.0.0",
                "api_prefix": "/api/v1",
            }
        )

    with app.app_context():
        init_db(app)

    return app


def main() -> None:
    app = create_app()
    host = os.environ.get("MASK_AUDIT_HOST", Config.HOST)
    port = int(os.environ.get("MASK_AUDIT_PORT", Config.PORT))
    debug = os.environ.get("MASK_AUDIT_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
