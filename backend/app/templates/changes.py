"""What changed between two versions of a template, by step, question and block ID.

The publish dialog shows it, and reports moving to a newer version (Phase 3) use it
to carry answers over: an answer follows its question's ID, so a question that was
only renamed, reworded or moved keeps its answers, and new or removed ones are
flagged.

Everything a designer can change is said in one of the lists: what was added and
removed, what was changed (with the parts that changed), and what was moved. Moved
means to another step, section, column or case, or to another place among the ones
it stands with; moving one question up past five others is one question moved, not
six.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterator, Sequence
from typing import Any

from pydantic import BaseModel

from app.templates.content import Block, Columns, Section, Switch, TemplateContent
from app.templates.names import questions


class Item(BaseModel):
    id: str
    label: str


class Changed(Item):
    # The parts that changed, such as "label", "key" or "settings".
    parts: list[str]


class Changes(BaseModel):
    steps_added: list[Item]
    steps_removed: list[Item]
    steps_changed: list[Changed]
    steps_moved: list[Item]
    questions_added: list[Item]
    questions_removed: list[Item]
    questions_changed: list[Changed]
    questions_moved: list[Item]
    blocks_added: list[Item]
    blocks_removed: list[Item]
    blocks_changed: list[Changed]
    blocks_moved: list[Item]
    settings_changed: list[str]
    # The answers "Try it" starts from.
    sample_changed: bool

    @property
    def any(self) -> bool:
        return any(getattr(self, name) for name in type(self).model_fields)


# Where a block stands: the top of the layout, a section, one column of a columns
# block, or one case of a switch (by its place among the cases and by what it
# matches) or its otherwise.
Place = tuple[Any, ...]


def _placed(blocks: list[Block], place: Place = ("layout",)) -> Iterator[tuple[Block, Place]]:
    """Every block with where it stands, in the order they print."""
    for block in blocks:
        yield block, place
        if isinstance(block, Section):
            yield from _placed(block.blocks, ("section", block.id))
        elif isinstance(block, Columns):
            for index, column in enumerate(block.columns):
                yield from _placed(column, ("column", block.id, index))
        elif isinstance(block, Switch):
            for index, case in enumerate(block.cases):
                yield from _placed(case.blocks, ("case", block.id, index, case.match))
            yield from _placed(block.otherwise, ("otherwise", block.id))


def _same_place(old: Place, new: Place) -> bool:
    if old[0] == new[0] == "case":
        # A case that was renamed, or that others were put before, is still that case.
        return bool(old[1] == new[1] and (old[2] == new[2] or old[3] == new[3]))
    return bool(old == new)


def _block_label(block: Block) -> str:
    for name in ("title", "text", "caption"):
        value = getattr(block, name, "")
        if isinstance(value, str) and value:
            return value
    return block.kind.replace("_", " ").capitalize()


def _own(block: Block) -> dict[str, Any]:
    """A block's settings without the blocks it holds."""
    if isinstance(block, Switch):
        return block.model_dump(exclude={"otherwise": True, "cases": {"__all__": {"blocks"}}})
    return block.model_dump(exclude={"blocks", "columns"} if block.kind in ("section", "columns")
                            else set())


def _compare(old: dict[str, Any], new: dict[str, Any], skip: set[str]) -> list[str]:
    return [name for name in new if name not in skip and old.get(name) != new.get(name)]


def _kept_in_order(old: Sequence[str], new: Sequence[str]) -> set[str]:
    """The most of the IDs that stand in the same order in both (the longest common
    run, not necessarily side by side): the rest are the ones that moved."""
    lengths = [[0] * (len(new) + 1) for _ in range(len(old) + 1)]
    for i in range(len(old) - 1, -1, -1):
        for j in range(len(new) - 1, -1, -1):
            lengths[i][j] = (lengths[i + 1][j + 1] + 1 if old[i] == new[j]
                             else max(lengths[i + 1][j], lengths[i][j + 1]))
    kept: set[str] = set()
    i = j = 0
    while i < len(old) and j < len(new):
        if old[i] == new[j]:
            kept.add(old[i])
            i, j = i + 1, j + 1
        elif lengths[i + 1][j] >= lengths[i][j + 1]:
            i += 1
        else:
            j += 1
    return kept


def _moved(old: Sequence[tuple[str, Place]], new: Sequence[tuple[str, Place]]) -> set[str]:
    """The IDs, among those in both, that stand somewhere else: in another place, or
    at another point among the ones they stand with."""
    before = dict(old)
    after = dict(new)
    stayed = {i for i in before if i in after and _same_place(before[i], after[i])}
    moved = {i for i in before if i in after} - stayed
    places: dict[Hashable, list[str]] = {}
    for i, place in new:
        if i in stayed:
            places.setdefault(place, []).append(i)
    for ids in places.values():
        together = set(ids)
        was = [i for i, _ in old if i in together]
        if was != ids:
            moved |= together - _kept_in_order(was, ids)
    return moved


def changes(old: TemplateContent | None, new: TemplateContent) -> Changes:
    old_steps = {s.id: s for s in old.form} if old else {}
    new_steps = {s.id: s for s in new.form}
    old_questions = {q.id: q for q in questions(old)} if old else {}
    new_questions = {q.id: q for q in questions(new)}
    old_blocks = {b.id: b for b, _ in _placed(old.layout)} if old else {}
    new_blocks = {b.id: b for b, _ in _placed(new.layout)}
    old_settings = old.settings.model_dump() if old else {}
    steps_moved = _moved([(s.id, ("form",)) for s in old.form] if old else [],
                         [(s.id, ("form",)) for s in new.form])
    questions_moved = _moved(
        [(q.id, ("step", s.id)) for s in old.form for q in s.questions] if old else [],
        [(q.id, ("step", s.id)) for s in new.form for q in s.questions])
    blocks_moved = _moved([(b.id, place) for b, place in _placed(old.layout)] if old else [],
                          [(b.id, place) for b, place in _placed(new.layout)])
    return Changes(
        steps_added=[Item(id=i, label=s.title) for i, s in new_steps.items()
                     if i not in old_steps],
        steps_removed=[Item(id=i, label=s.title) for i, s in old_steps.items()
                       if i not in new_steps],
        steps_changed=[
            Changed(id=i, label=s.title, parts=parts) for i, s in new_steps.items()
            if i in old_steps and (parts := _compare(
                old_steps[i].model_dump(exclude={"questions"}),
                s.model_dump(exclude={"questions"}), {"id"}))
        ],
        steps_moved=[Item(id=i, label=s.title) for i, s in new_steps.items() if i in steps_moved],
        questions_added=[Item(id=i, label=q.label) for i, q in new_questions.items()
                         if i not in old_questions],
        questions_removed=[Item(id=i, label=q.label) for i, q in old_questions.items()
                           if i not in new_questions],
        questions_changed=[
            Changed(id=i, label=q.label, parts=parts) for i, q in new_questions.items()
            if i in old_questions and (parts := _compare(
                old_questions[i].model_dump(), q.model_dump(), {"id"}))
        ],
        questions_moved=[Item(id=i, label=q.label) for i, q in new_questions.items()
                         if i in questions_moved],
        blocks_added=[Item(id=i, label=_block_label(b)) for i, b in new_blocks.items()
                      if i not in old_blocks],
        blocks_removed=[Item(id=i, label=_block_label(b)) for i, b in old_blocks.items()
                        if i not in new_blocks],
        blocks_changed=[
            Changed(id=i, label=_block_label(b), parts=parts) for i, b in new_blocks.items()
            if i in old_blocks and (parts := _compare(_own(old_blocks[i]), _own(b), {"id"}))
        ],
        blocks_moved=[Item(id=i, label=_block_label(b)) for i, b in new_blocks.items()
                      if i in blocks_moved],
        settings_changed=_compare(old_settings, new.settings.model_dump(), set()) if old else [],
        sample_changed=old is not None and old.sample.model_dump() != new.sample.model_dump(),
    )
