"""What changed between two versions of a template, by question and block ID.

The publish dialog shows it, and reports moving to a newer version (Phase 3) use it
to carry answers over: an answer follows its question's ID, so a question that was
only renamed or reworded keeps its answers, and new or removed ones are flagged.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel

from app.templates.content import Block, Columns, Section, TemplateContent
from app.templates.names import questions


class Item(BaseModel):
    id: str
    label: str


class Changed(Item):
    # The parts that changed, such as "label", "key" or "settings".
    parts: list[str]


class Changes(BaseModel):
    questions_added: list[Item]
    questions_removed: list[Item]
    questions_changed: list[Changed]
    blocks_added: list[Item]
    blocks_removed: list[Item]
    blocks_changed: list[Changed]
    settings_changed: list[str]

    @property
    def any(self) -> bool:
        return any(getattr(self, name) for name in type(self).model_fields)


def _blocks(blocks: list[Block]) -> Iterator[Block]:
    for block in blocks:
        yield block
        if isinstance(block, Section):
            yield from _blocks(block.blocks)
        elif isinstance(block, Columns):
            for column in block.columns:
                yield from _blocks(column)


def _block_label(block: Block) -> str:
    for name in ("title", "text", "caption"):
        value = getattr(block, name, "")
        if isinstance(value, str) and value:
            return value
    return block.kind.replace("_", " ").capitalize()


def _own(block: Block) -> dict[str, Any]:
    """A block's settings without the blocks it holds."""
    return block.model_dump(exclude={"blocks", "columns"} if block.kind in ("section", "columns")
                            else set())


def _compare(old: dict[str, Any], new: dict[str, Any], skip: set[str]) -> list[str]:
    return [name for name in new if name not in skip and old.get(name) != new.get(name)]


def changes(old: TemplateContent | None, new: TemplateContent) -> Changes:
    old_questions = {q.id: q for q in questions(old)} if old else {}
    new_questions = {q.id: q for q in questions(new)}
    old_blocks = {b.id: b for b in _blocks(old.layout)} if old else {}
    new_blocks = {b.id: b for b in _blocks(new.layout)}
    old_settings = old.settings.model_dump() if old else {}
    return Changes(
        questions_added=[Item(id=i, label=q.label) for i, q in new_questions.items()
                         if i not in old_questions],
        questions_removed=[Item(id=i, label=q.label) for i, q in old_questions.items()
                           if i not in new_questions],
        questions_changed=[
            Changed(id=i, label=q.label, parts=parts) for i, q in new_questions.items()
            if i in old_questions and (parts := _compare(
                old_questions[i].model_dump(), q.model_dump(), {"id"}))
        ],
        blocks_added=[Item(id=i, label=_block_label(b)) for i, b in new_blocks.items()
                      if i not in old_blocks],
        blocks_removed=[Item(id=i, label=_block_label(b)) for i, b in old_blocks.items()
                        if i not in new_blocks],
        blocks_changed=[
            Changed(id=i, label=_block_label(b), parts=parts) for i, b in new_blocks.items()
            if i in old_blocks and (parts := _compare(_own(old_blocks[i]), _own(b), {"id"}))
        ],
        settings_changed=_compare(old_settings, new.settings.model_dump(), set()) if old else [],
    )
