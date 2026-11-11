"""接口层的入参与出参定义。"""

from pydantic import BaseModel, Field


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    ts: str | None = None
    source: str = "note"
    conv: str | None = None
    sender: str = "me"
    is_me: int = 1
    kind: str = "text"


class MessageOut(BaseModel):
    id: int
    ts: str
    source: str
    conv: str | None = None
    sender: str
    is_me: int
    text: str
    kind: str
    created_at: str


class CreateResult(BaseModel):
    ok: bool
    duplicated: bool
    message: MessageOut | None = None


class MessagePatch(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class DeleteResult(BaseModel):
    ok: bool
    deleted: bool


class DayOut(BaseModel):
    day: str
    count: int


class PersonOut(BaseModel):
    id: int
    name: str
    count: int


class PersonRebuildOut(BaseModel):
    persons: int


class HealthOut(BaseModel):
    ok: bool
    messages: int
    db_bytes: int
    llm: bool = False


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class Citation(BaseModel):
    id: int
    ts: str
    text: str


class ChatOut(BaseModel):
    answer: str
    citations: list[Citation]
    used_llm: bool


class DraftIn(BaseModel):
    theirs: str = Field(min_length=1, max_length=2000)
    intent: str = Field("", max_length=500)


class DraftOut(BaseModel):
    candidates: list[str]
