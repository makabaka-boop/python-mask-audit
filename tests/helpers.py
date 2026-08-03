"""共享测试工具：创建临时数据库并在后台线程启动服务。"""

import json
import os
import tempfile
import threading
import urllib.request
import urllib.error


def make_env():
    """返回一个隔离的临时数据库路径，并让服务使用该库。

    ``config.DB_PATH`` 在模块导入时求值，因此仅设置环境变量无法在同一进程
    内为不同测试类切换数据库；这里同时覆盖已导入的 ``config.DB_PATH``，保证
    每个测试夹具拥有独立、干净的数据库。
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["MASK_AUDIT_DB"] = path
    try:
        from app import config

        config.DB_PATH = path
    except Exception:
        pass
    return path


class ServerFixture:
    """在随机端口启动服务，供集成测试使用。"""

    def __init__(self):
        # 延迟导入，确保 MASK_AUDIT_DB 已设置。
        from app import server

        self.httpd = server.create_server(host="127.0.0.1", port=0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def request(self, method, path, body=None):
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.url(path), data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def stop(self):
        self.httpd.shutdown()
