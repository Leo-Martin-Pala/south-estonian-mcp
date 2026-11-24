from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import TypedDict


# Restrict the check to adjacent words at the start of a simple clause.
_OPENING_PAIR = re.compile(r"(?:\A|(?<=[.!?])\s+)\s*([^\s.,!?;:]+)[ \t]+([^\s.,!?;:]+)")
_PROFILES = {
    "mulgi": ("olema", {"Sg1": "ole", "Sg2": "olet"}),
    "seto": ("olõma", {"Sg1": "olõ", "Sg2": "olõt"}),
}
_PRONOUNS = {"mina+Pron+Pers+Sg1+Nom": "Sg1", "sina+Pron+Pers+Sg2+Nom": "Sg2"}
_OTHER_PERSONS = {
    "Sg1": frozenset({"Sg2", "Sg3", "Pl3"}),
    "Sg2": frozenset({"Sg3", "Pl3"}),
}


class GrammarFinding(TypedDict):
    word: str
    span: list[int]
    code: str
    suggestions: list[str]


def opening_pairs(text: str) -> list[tuple[str, str, re.Match[str]]]:
    return [
        (unicodedata.normalize("NFC", match[1].lower()),
         unicodedata.normalize("NFC", match[2].lower()), match)
        for match in _OPENING_PAIR.finditer(text)
    ]


def copula_findings(
    lang: str,
    pairs: list[tuple[str, str, re.Match[str]]],
    analyses: dict[str, set[str]],
) -> Iterator[GrammarFinding]:
    lemma, forms = _PROFILES[lang]
    prefix = f"{lemma}+V+Act+Ind+Prs+"
    previous_start = 0
    start = 0
    for subject, verb, match in pairs:
        subject_readings = analyses.get(subject, set())
        if len(subject_readings) != 1:
            continue
        person = _PRONOUNS.get(next(iter(subject_readings)))
        if person is None:
            continue
        verb_readings = analyses.get(verb, set())
        if not verb_readings or not all(
            reading.startswith(prefix) and reading.removeprefix(prefix) in _OTHER_PERSONS[person]
            for reading in verb_readings
        ):
            continue
        replacement = forms[person]
        if match[2].isupper():
            replacement = replacement.upper()
        elif match[2].istitle():
            replacement = replacement.title()
        # Divvun uses UTF-16 code units for the public grammar span.
        start += len(match.string[previous_start:match.start(2)].encode(
            "utf-16-le", errors="surrogatepass",
        )) // 2
        previous_start = match.start(2)
        end = start + len(match[2].encode("utf-16-le", errors="surrogatepass")) // 2
        yield {
            "word": match[2],
            "span": [start, end],
            "code": "copula-agreement",
            "suggestions": [replacement],
        }
