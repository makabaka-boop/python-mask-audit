"""HTTP 服务器。

基于标准库 ``http.server`` 实现，监听 18105 端口，将请求交给
路由分发，并统一处理 JSON 编解码与错误响应。
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, db, routes
from .errors import ApiError


class Handler(BaseHTTPRequestHandler):
    server_version = "MaskAudit/1.0"

    # 静默默认日志，改为简洁输出。
    def log_message(self, fmt, *args):
        return

    def _send(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_payload(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError(
                "请求体不是合法 JSON",
                details={"reason": str(exc)},
                error_code="invalid_json",
                status_code=400,
            )

    def _handle(self, method):
        # 去掉 query string。
        path = self.path.split("?", 1)[0].rstrip("/") or self.path.split("?", 1)[0]
        if path == "":
            path = "/"
        conn = db.get_connection()
        try:
            payload = self._read_payload() if method in ("POST", "PUT", "DELETE") else {}
            status, body = routes.dispatch(conn, method, path, payload)
            self._send(status, body)
        except ApiError as exc:
            self._send(exc.status_code, exc.to_dict())
        except Exception as exc:  # noqa: BLE001 —— 兜底防止连接挂死
            self._send(
                500,
                {"error_code": "internal_error", "message": str(exc), "details": {}},
            )
        finally:
            conn.close()

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PUT(self):
        self._handle("PUT")


def create_server(host=None, port=None):
    db.init_db()
    bind_host = host if host is not None else config.HOST
    bind_port = port if port is not None else config.PORT
    server = ThreadingHTTPServer((bind_host, bind_port), Handler)
    return server


def main():
    server = create_server()
    host, port = server.server_address
    print(f"mask-audit 服务已启动，监听 http://{host}:{port}{config.API_PREFIX}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("正在关闭服务 ...")
        server.shutdown()


if __name__ == "__main__":
    main()
