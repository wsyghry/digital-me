"""接口层：只负责收参数、调业务、返回结果。不写 SQL，不调模型。"""

import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..db import store
from ..services import chat as chat_service
from ..services import draft as draft_service
from ..services import llm, retrieve
from ..services.llm import LLMError
from .schemas import (
    ChatIn,
    ChatOut,
    CreateResult,
    DayOut,
    DeleteResult,
    DraftIn,
    DraftOut,
    HealthOut,
    MessageIn,
    MessageOut,
    MessagePatch,
    PersonOut,
    PersonRebuildOut,
)

router = APIRouter(prefix="/api")


def _day(value: str | None, name: str) -> str | None:
    """把日期参数收紧成 YYYY-MM-DD，写歪了直接 422。"""
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise HTTPException(422, f"{name} 要写成 YYYY-MM-DD，比如 2026-11-10")


@router.post("/messages", response_model=CreateResult)
def create_message(body: MessageIn) -> CreateResult:
    record = store.insert_message(
        body.text.strip(),
        ts=body.ts,
        source=body.source,
        conv=body.conv,
        sender=body.sender,
        is_me=body.is_me,
        kind=body.kind,
    )
    if record is None:
        return CreateResult(ok=True, duplicated=True)
    return CreateResult(ok=True, duplicated=False, message=MessageOut(**record))


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    person: str | None = None,
) -> list[MessageOut]:
    return [
        MessageOut(**r)
        for r in store.list_messages(
            limit, before_id,
            start=_day(start, "start"), end=_day(end, "end"), person=person,
        )
    ]


@router.patch("/messages/{msg_id}", response_model=MessageOut)
def update_message(msg_id: int, body: MessagePatch) -> MessageOut:
    try:
        record = store.update_message(msg_id, body.text.strip())
    except sqlite3.IntegrityError:
        raise HTTPException(409, "改完之后和另一条记录一模一样")
    if record is None:
        raise HTTPException(404, "没有这条记录")
    return MessageOut(**record)


@router.delete("/messages/{msg_id}", response_model=DeleteResult)
def delete_message(msg_id: int) -> DeleteResult:
    if not store.delete_message(msg_id):
        raise HTTPException(404, "没有这条记录")
    return DeleteResult(ok=True, deleted=True)


@router.get("/export.md", response_class=PlainTextResponse)
def export_markdown() -> PlainTextResponse:
    return PlainTextResponse(
        store.export_markdown(),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="digital-me.md"'},
    )


@router.get("/search", response_model=list[MessageOut])
def search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    start: str | None = None,
    end: str | None = None,
    person: str | None = None,
) -> list[MessageOut]:
    return [
        MessageOut(**r)
        for r in retrieve.search(
            q, limit, start=_day(start, "start"), end=_day(end, "end"), person=person
        )
    ]


@router.get("/persons", response_model=list[PersonOut])
def persons(limit: int = Query(300, ge=1, le=2000)) -> list[PersonOut]:
    """人名 + 往来条数，给「按人看」下拉用。"""
    return [PersonOut(**p) for p in store.list_persons(limit)]


@router.post("/persons/rebuild", response_model=PersonRebuildOut)
def rebuild_persons() -> PersonRebuildOut:
    """从现有消息重新归纳人物表（幂等，导入后可跑一次）。"""
    return PersonRebuildOut(**store.rebuild_persons())


@router.get("/days", response_model=list[DayOut])
def days(limit: int = Query(120, ge=1, le=365)) -> list[DayOut]:
    """按日期汇总，给界面的日期索引用。"""
    return [DayOut(**d) for d in store.days(limit)]


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    try:
        return ChatOut(**chat_service.ask(body.question))
    except LLMError as err:
        raise HTTPException(err.status, err.message)


@router.post("/draft", response_model=DraftOut)
def draft(body: DraftIn) -> DraftOut:
    try:
        return DraftOut(candidates=draft_service.draft(body.theirs, body.intent))
    except LLMError as err:
        raise HTTPException(err.status, err.message)
    except ValueError as err:
        raise HTTPException(422, str(err))


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        ok=True,
        messages=store.count_messages(),
        db_bytes=store.db_size_bytes(),
        llm=llm.available(),
    )
