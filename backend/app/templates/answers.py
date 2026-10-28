"""Whether an answer to a typed question is valid, in words fit to show beside it.

The form in the browser checks answers as they're typed (frontend/src/lib/templates/
answers.ts, the same rules); the server checks them again when a report is saved
(Phase 3). shared/fields/cases.json holds both to the same verdicts and words.
Addresses are parsed by hand rather than with each language's own library, so the
two can't disagree on the edges (leading zeros, IPv6 zone IDs). An empty answer
isn't checked here: whether one is needed is the question's "required".
"""

from __future__ import annotations

import re
from typing import Any

import re2
from cvss import CVSS3, CVSS4

V31_EXAMPLE = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
MESSAGES = {
    "ip": "Enter an IP address, such as 198.51.100.23 or 2001:db8::5.",
    "v4": "Enter an IPv4 address, such as 198.51.100.23.",
    "v6": "Enter an IPv6 address, such as 2001:db8::5.",
    "no_prefix": "Enter the address without a prefix such as /24.",
    "prefix": "Add the prefix length, such as /24.",
    "hostname": "Enter a host name, such as srv-01.fjordvik.example.",
    "mac": "Enter a MAC address: six pairs of hex digits, such as 00:1A:2B:3C:4D:5E.",
    "email": "Enter an email address, such as name@fjordvik.example.",
    "phone": "Enter a phone number: digits, spaces and + ( ) - only.",
    "cvss": f"Enter a CVSS 3.1 or 4.0 vector, such as {V31_EXAMPLE}.",
    "pattern": "This doesn't match what the template asks for.",
}

_OCTET = re.compile(r"^(0|[1-9][0-9]{0,2})$")
_HEX = re.compile(r"^[0-9A-Fa-f]{1,4}$")
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")
_MAC = (
    re.compile(r"^[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$"),
    re.compile(r"^[0-9A-Fa-f]{12}$"),
    re.compile(r"^[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}$"),
)
_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_PHONE = re.compile(r"^\+?[0-9 ()\-.]+$")


def is_ipv4(text: str) -> bool:
    parts = text.split(".")
    return len(parts) == 4 and all(_OCTET.match(p) and int(p) <= 255 for p in parts)


def is_ipv6(text: str) -> bool:
    if text.count("::") > 1:
        return False
    if "::" in text:
        head, tail = text.split("::")
        groups = (head.split(":") if head else []) + (tail.split(":") if tail else [])
    else:
        groups = text.split(":")
    count = 0
    for index, group in enumerate(groups):
        if index == len(groups) - 1 and "." in group:
            if not is_ipv4(group):
                return False
            count += 2
        elif _HEX.match(group):
            count += 1
        else:
            return False
    return count <= 7 if "::" in text else count == 8


def _ip(value: str, settings: dict[str, Any]) -> str | None:
    versions = settings.get("versions", "any")
    wrong = MESSAGES["v4" if versions == "v4" else "v6" if versions == "v6" else "ip"]
    address, slash, prefix = value.partition("/")
    v4, v6 = is_ipv4(address), is_ipv6(address)
    if not (v4 or v6):
        return wrong
    if slash:
        if not _OCTET.match(prefix) or int(prefix) > (32 if v4 else 128):
            return wrong
    if versions == "v4" and not v4:
        return MESSAGES["v4"]
    if versions == "v6" and not v6:
        return MESSAGES["v6"]
    cidr = settings.get("cidr", "no")
    if slash and cidr == "no":
        return MESSAGES["no_prefix"]
    if not slash and cidr == "required":
        return MESSAGES["prefix"]
    return None


def is_hostname(text: str) -> bool:
    labels = text.split(".")
    return len(text) <= 253 and all(len(label) <= 63 and _LABEL.match(label) for label in labels)


def _email(value: str) -> bool:
    local, at, domain = value.rpartition("@")
    return (bool(at) and len(value) <= 254 and len(local) <= 64 and bool(_LOCAL.match(local))
            and "." in domain and is_hostname(domain))


def _phone(value: str) -> bool:
    digits = sum(c.isdigit() for c in value)
    return bool(_PHONE.match(value)) and 4 <= digits <= 20


# CVSS vectors: every base metric once, and only the metrics each version has.
_CVSS31 = {
    "AV": "NALP", "AC": "LH", "PR": "NLH", "UI": "NR", "S": "UC", "C": "HLN", "I": "HLN",
    "A": "HLN",
}
_CVSS31_MORE = {
    "E": "XUPFH", "RL": "XOTWU", "RC": "XURC", "CR": "XLMH", "IR": "XLMH", "AR": "XLMH",
    "MAV": "XNALP", "MAC": "XLH", "MPR": "XNLH", "MUI": "XNR", "MS": "XUC", "MC": "XNLH",
    "MI": "XNLH", "MA": "XNLH",
}
_CVSS40 = {
    "AV": "NALP", "AC": "LH", "AT": "NP", "PR": "NLH", "UI": "NPA", "VC": "HLN", "VI": "HLN",
    "VA": "HLN", "SC": "HLN", "SI": "HLN", "SA": "HLN",
}
_CVSS40_MORE = {
    "E": "XAPU", "CR": "XHML", "IR": "XHML", "AR": "XHML", "MAV": "XNALP", "MAC": "XLH",
    "MAT": "XNP", "MPR": "XNLH", "MUI": "XNPA", "MVC": "XHLN", "MVI": "XHLN", "MVA": "XHLN",
    "MSC": "XHLN", "MSI": "XSHLN", "MSA": "XSHLN", "S": "XNP", "AU": "XNY", "R": "XAUI",
    "V": "XDC", "RE": "XLMH",
}
_CVSS40_URGENCY = ("X", "Clear", "Green", "Amber", "Red")


def cvss_version(vector: str) -> str | None:
    """3.1 or 4.0 for a well-formed vector, else None."""
    for version, base, more in (("3.1", _CVSS31, _CVSS31_MORE), ("4.0", _CVSS40, _CVSS40_MORE)):
        prefix = f"CVSS:{version}/"
        if not vector.startswith(prefix):
            continue
        seen: dict[str, str] = {}
        for part in vector[len(prefix):].split("/"):
            name, colon, value = part.partition(":")
            if not colon or name in seen:
                return None
            allowed = base.get(name) or more.get(name)
            if version == "4.0" and name == "U":
                if value not in _CVSS40_URGENCY:
                    return None
            elif allowed is None or len(value) != 1 or value not in allowed:
                return None
            seen[name] = value
        return version if all(name in seen for name in base) else None
    return None


def severity(score: float) -> str:
    if score == 0:
        return "None"
    if score < 4:
        return "Low"
    if score < 7:
        return "Medium"
    if score < 9:
        return "High"
    return "Critical"


def cvss_score(vector: str) -> tuple[float, str] | None:
    """The score (3.1: the base score; 4.0: the vector's own) and its severity."""
    version = cvss_version(vector)
    if version is None:
        return None
    if version == "3.1":
        score = float(CVSS3(vector).scores()[0])
    else:
        score = float(CVSS4(vector).base_score)
    return round(score, 1), severity(score)


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def check_answer(type_: str, settings: dict[str, Any], value: Any) -> str | None:
    """What's wrong with the answer, or None if it's fine (or empty)."""
    if value is None or value == "":
        return None
    if type_ == "ip":
        return _ip(str(value), settings)
    if type_ == "hostname":
        return None if is_hostname(str(value)) else MESSAGES["hostname"]
    if type_ == "mac":
        return None if any(p.match(str(value)) for p in _MAC) else MESSAGES["mac"]
    if type_ == "email":
        return None if _email(str(value)) else MESSAGES["email"]
    if type_ == "phone":
        return None if _phone(str(value)) else MESSAGES["phone"]
    if type_ == "cvss":
        version = cvss_version(str(value))
        if version is None:
            return MESSAGES["cvss"]
        allowed = settings.get("versions", ["3.1", "4.0"])
        if version not in allowed:
            return f"This template takes CVSS {allowed[0]} vectors only."
        return None
    if type_ == "number":
        number = float(value)
        if settings.get("whole") and not number.is_integer():
            return "Enter a whole number."
        low, high = settings.get("min"), settings.get("max")
        if low is not None and high is not None and not low <= number <= high:
            return f"Enter a number from {_number(low)} to {_number(high)}."
        if low is not None and high is None and number < low:
            return f"Enter a number of at least {_number(low)}."
        if high is not None and low is None and number > high:
            return f"Enter a number of at most {_number(high)}."
        return None
    if type_ in ("text", "serial"):
        text = str(value)
        most = settings.get("max_length")
        if most is not None and len(text) > most:
            return f"Keep it to {most} characters."
        pattern = settings.get("pattern")
        if pattern:
            try:
                matched = re2.search(pattern, text) is not None
            except Exception:
                return None
            if not matched:
                return settings.get("pattern_message") or MESSAGES["pattern"]
    return None
