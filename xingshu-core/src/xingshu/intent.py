"""作者意图声明（对应设计 `06` §3）。

用户在暂停状态可为某章/某实体声明"此现象是有意为之的文学手法"（如非线性
叙事、不可靠叙述者、欲扬先抑）。声明进入审计提示词后，对应内容只会被记作
Creative Choice，不再判为 Blocker/Major——这是 `07` 五级严重度里 Creative
Choice 的可操作化入口。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class AuthorIntent:
    chapter: int
    target: str      # 被声明的现象/实体（如"时间线跳跃""诡叙"）
    reason: str = ""  # 文学手法说明（供审计参考）


class IntentBook:
    """章的意图声明簿（内存版；可经 to_yaml/load 持久化到 settings/）。"""

    def __init__(self) -> None:
        self._intents: list[AuthorIntent] = []

    def add(self, intent: AuthorIntent) -> None:
        self._intents.append(intent)

    def by_chapter(self, chapter: int) -> list[AuthorIntent]:
        return [i for i in self._intents if i.chapter == chapter]

    def all(self) -> list[AuthorIntent]:
        return list(self._intents)


def declare_intent(book: IntentBook, *, chapter: int, target: str, reason: str = "") -> AuthorIntent:
    intent = AuthorIntent(chapter=chapter, target=target, reason=reason)
    book.add(intent)
    return intent


def intents_to_yaml(intents: list[AuthorIntent]) -> str:
    return yaml.safe_dump([{"chapter": i.chapter, "target": i.target, "reason": i.reason}
                           for i in intents], allow_unicode=True, sort_keys=False)


def load_intents_from_yaml(text: str) -> list[AuthorIntent]:
    data = yaml.safe_load(text) or []
    return [AuthorIntent(chapter=int(d["chapter"]), target=str(d["target"]),
                         reason=str(d.get("reason", ""))) for d in data]


def save_intent_book(book: IntentBook, path: str | Path) -> Path:
    """持久化到 settings/author_intents.yaml（06 §3：声明记录在真相文件体系内）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(intents_to_yaml(book.all()), encoding="utf-8")
    return p


def load_intent_book(path: str | Path) -> IntentBook:
    book = IntentBook()
    for i in load_intents_from_yaml(Path(path).read_text(encoding="utf-8")):
        book.add(i)
    return book