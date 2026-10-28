"""Field types for the Questions tab: each one's settings, and the names it gives
expressions.

Field types are plug-ins: an entry here (settings, names) and one in the browser
(frontend/src/lib/templates/fields.ts: label, editor, input). The shared examples in
shared/templates/checks.json hold both to the same names and problems.

What a type gives expressions is chosen with care. A secret never enters an
expression: a rule sees whether it's filled in and how it's printed, never the
value. Files, photos and signatures give whether there are any.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KEY_PATTERN = r"^[a-z][a-z0-9_]{0,49}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(Strict):
    value: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)


def _unique_options(options: list[Option]) -> list[Option]:
    values = [o.value for o in options]
    if len(values) != len(set(values)):
        raise ValueError("Two options have the same value.")
    return options


class NoSettings(Strict):
    pass


class TextSettings(Strict):
    max_length: int = Field(default=500, ge=1, le=10_000)
    # A regular expression (RE2) the answer must match, checked with the template.
    pattern: str | None = Field(default=None, max_length=500)
    pattern_message: str = Field(default="", max_length=300)
    placeholder: str = Field(default="", max_length=200)


class RichTextSettings(Strict):
    max_length: int = Field(default=20_000, ge=1, le=100_000)
    # Whether the technician can insert text snippets from the shared library.
    snippets: bool = True


class NumberSettings(Strict):
    whole: bool = False
    min: float | None = None
    max: float | None = None
    decimals: int = Field(default=1, ge=0, le=6)
    unit: str = Field(default="", max_length=20)


class DateTimeSettings(Strict):
    mode: Literal["date", "datetime"] = "datetime"


class YesNoSettings(Strict):
    yes_label: str = Field(default="Yes", min_length=1, max_length=50)
    no_label: str = Field(default="No", min_length=1, max_length=50)


class ChoiceSettings(Strict):
    options: list[Option] = Field(min_length=1, max_length=200)

    _unique = field_validator("options")(_unique_options)


class MultiSelectSettings(ChoiceSettings):
    min_selected: int | None = Field(default=None, ge=0, le=200)
    max_selected: int | None = Field(default=None, ge=1, le=200)


class IpSettings(Strict):
    versions: Literal["any", "v4", "v6"] = "any"
    cidr: Literal["no", "allowed", "required"] = "no"


class SerialSettings(Strict):
    pattern: str | None = Field(default=None, max_length=500)
    pattern_message: str = Field(default="", max_length=300)


class CvssSettings(Strict):
    versions: list[Literal["3.1", "4.0"]] = Field(
        default=["3.1", "4.0"], min_length=1, max_length=2)


class SecretSettings(Strict):
    # How the PDF prints it: partly (at most a quarter, three characters at each end)
    # or not at all.
    pdf: Literal["partial", "omit"] = "partial"


class FileSettings(Strict):
    multiple: bool = False
    max_files: int = Field(default=10, ge=1, le=50)


class PhotoSettings(Strict):
    multiple: bool = False
    max_photos: int = Field(default=10, ge=1, le=50)


class BarcodeSettings(Strict):
    formats: list[Literal["qr", "code128", "ean13", "datamatrix"]] = Field(
        default=["qr", "code128"], min_length=1, max_length=4)


COLUMN_TYPES = ("text", "number", "yes_no", "dropdown", "datetime", "ip", "hostname", "mac",
                "serial", "email", "phone")


class Column(Strict):
    key: str = Field(pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    type: Literal["text", "number", "yes_no", "dropdown", "datetime", "ip", "hostname", "mac",
                  "serial", "email", "phone"]
    required: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _settings(self) -> Column:
        self.settings = FIELD_TYPES[self.type].settings.model_validate(self.settings).model_dump()
        return self


class Row(Strict):
    key: str = Field(pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=200)


class RepeatingSettings(Strict):
    columns: list[Column] = Field(min_length=1, max_length=20)
    min_rows: int = Field(default=0, ge=0, le=500)
    max_rows: int = Field(default=100, ge=1, le=500)


class TableSettings(Strict):
    rows: list[Row] = Field(min_length=1, max_length=100)
    columns: list[Column] = Field(min_length=1, max_length=20)


class CalculatedSettings(Strict):
    result: Literal["text", "number", "whole", "yes_no", "date"] = "text"
    show_in_form: bool = True


@dataclass(frozen=True)
class FieldType:
    settings: type[Strict]
    # The names a question of this type adds under answers.<key>: "" for the key itself,
    # ".score" for answers.<key>.score, and their types.
    names: Callable[[Any], dict[str, str]]
    # Headings ask nothing.
    asks: bool = True


def _one(type_: str) -> Callable[[Any], dict[str, str]]:
    return lambda _settings: {"": type_}


_RESULT_TYPES = {"text": "string", "number": "double", "whole": "int", "yes_no": "bool",
                 "date": "timestamp"}

FIELD_TYPES: dict[str, FieldType] = {
    "text": FieldType(TextSettings, _one("string")),
    "rich_text": FieldType(RichTextSettings, _one("string")),
    "number": FieldType(NumberSettings, lambda s: {"": "int" if s.whole else "double"}),
    "datetime": FieldType(DateTimeSettings, _one("timestamp")),
    "yes_no": FieldType(YesNoSettings, _one("bool")),
    "dropdown": FieldType(ChoiceSettings, _one("string")),
    "multi_select": FieldType(MultiSelectSettings, _one("list<string>")),
    "ip": FieldType(IpSettings, _one("string")),
    "hostname": FieldType(NoSettings, _one("string")),
    "mac": FieldType(NoSettings, _one("string")),
    "serial": FieldType(SerialSettings, _one("string")),
    "email": FieldType(NoSettings, _one("string")),
    "phone": FieldType(NoSettings, _one("string")),
    "cvss": FieldType(CvssSettings, lambda _s: {
        ".score": "double", ".vector": "string", ".severity": "string"}),
    "secret": FieldType(SecretSettings, lambda _s: {".filled": "bool", ".printed": "string"}),
    "file": FieldType(FileSettings, lambda _s: {".filled": "bool", ".count": "int"}),
    "photo": FieldType(PhotoSettings, lambda _s: {".filled": "bool", ".count": "int"}),
    "barcode": FieldType(BarcodeSettings, _one("string")),
    "signature": FieldType(NoSettings, lambda _s: {".filled": "bool"}),
    "repeating": FieldType(RepeatingSettings, _one("list<map<string, dyn>>")),
    "table": FieldType(TableSettings, _one("list<map<string, dyn>>")),
    "calculated": FieldType(CalculatedSettings, lambda s: {"": _RESULT_TYPES[s.result]}),
    "heading": FieldType(NoSettings, lambda _s: {}, asks=False),
}
