"""服务入口：监听 18105 端口。"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18105)
