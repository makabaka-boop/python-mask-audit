"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1 import api_router
from app.config import API_V1_PREFIX, HOST, PORT
from app.core.errors import AppError, app_error_handler, unhandled_error_handler
from app.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="脱敏规则沙盒服务",
    description="mask-audit: 数据治理脱敏规则验证沙盒",
    version=__version__,
    lifespan=lifespan,
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "details": {"errors": exc.errors()},
        },
    )


app.include_router(api_router, prefix=API_V1_PREFIX)


def main():
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
