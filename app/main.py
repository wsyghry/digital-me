"""分身志 后端入口：建库、挂接口、托管前端。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .api.routes import router
from .db import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    yield


app = FastAPI(title="分身志", lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
