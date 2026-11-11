"""分身志 后端入口：建库、挂接口、托管前端。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import auth, config
from .api.routes import router
from .db import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    yield


app = FastAPI(title="分身志", lifespan=lifespan)


@app.middleware("http")
async def require_password(request, call_next):
    blocked = auth.check(request)
    if blocked is not None:
        return blocked
    return await call_next(request)


app.add_api_route("/login", auth.login_page, methods=["GET"])
app.add_api_route("/api/login", auth.login, methods=["POST"])
app.add_api_route("/api/logout", auth.logout, methods=["POST"])
app.include_router(router)
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
