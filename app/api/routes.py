"""接口层：只负责收参数、调业务、返回结果。不写 SQL，不调模型。"""

import sqlite3
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from .. import config
from ..db import store
from ..services import chat as chat_service
from ..services import cost
from ..services import draft as draft_service
from ..services import llm, retrieve
from ..services.llm import LLMError
from .schemas import (
    AliasIn,
    AliasOut,
    AliasSuggestOut,
    ChatIn,
    ChatOut,
    CostOut,
    CreateResult,
    DayOut,
    DeleteAliasResult,
    DeleteResult,
    DraftIn,
    DraftOut,
    HealthOut,
    InboxItem,
    InboxOut,
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
def export_markdown(
    start: str | None = None,
    end: str | None = None,
    person: str | None = None,
) -> PlainTextResponse:
    label = "digital-me"
    if start or end:
        label += f"-{start or ''}_{end or ''}"
    # 头里只能放 latin-1：文件名用 ASCII，中文名走 filename*（RFC 5987）
    ascii_name = label + ".md"
    utf8_name = quote(f"分身志导出{'-' + person if person else ''}{'-' + label if start or end else ''}.md")
    return PlainTextResponse(
        store.export_markdown(
            start=_day(start, "start"), end=_day(end, "end"), person=person
        ),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
        },
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


@router.get("/aliases", response_model=list[AliasOut])
def aliases() -> list[AliasOut]:
    """别名表：哪些名字被并到了谁名下。"""
    return [AliasOut(**a) for a in store.list_aliases()]


@router.get("/persons/suggest", response_model=list[AliasSuggestOut])
def persons_suggest(limit: int = Query(50, ge=1, le=300)) -> list[AliasSuggestOut]:
    """疑似同一个人的候选，交给前端一键合并。只做保守规则，宁漏不误并。"""
    return [AliasSuggestOut(**s) for s in store.suggest_aliases(limit)]


@router.post("/aliases", response_model=AliasOut)
def add_alias(body: AliasIn) -> AliasOut:
    """把一个人的另一个名字并到正名下。"""
    try:
        return AliasOut(**store.set_alias(body.name, body.person))
    except ValueError as err:
        raise HTTPException(422, str(err))


@router.delete("/aliases/{name}", response_model=DeleteAliasResult)
def remove_alias(name: str) -> DeleteAliasResult:
    return DeleteAliasResult(ok=True, deleted=store.delete_alias(name))


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


@router.get("/cost", response_model=CostOut)
def cost_summary() -> CostOut:
    """一共调了几次模型、花了多少钱（按官方价目表估算）。"""
    return CostOut(**cost.summary())


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        ok=True,
        messages=store.count_messages(),
        db_bytes=store.db_size_bytes(),
        llm=llm.available(),
        auth=config.auth_required(),
    )


@router.get("/inbox", response_model=InboxOut)
def inbox(
    minutes: int = Query(2, ge=0, le=1440),
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(30, ge=1, le=200),
    include_groups: bool = False,
) -> InboxOut:
    """谁在等我回话（只读）：最后一个说话的是对方，且已经过了几分钟。"""
    items = store.pending_replies(
        minutes=minutes, limit=limit, active_days=days, include_groups=include_groups
    )
    return InboxOut(items=[InboxItem(**m) for m in items])


