from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .copula_agreement import copula_findings, opening_pairs

GIELLA_LANGS: tuple[str, ...] = ("vro", "mulgi", "seto")

_GIELLA_LANG_ALIASES: dict[str, str] = {
    "vro": "vro",
    "voro": "vro",
    "võro": "vro",
    "voru": "vro",
    "võru": "vro",
    "mulgi": "mulgi",
    "mulk": "mulgi",
    "seto": "seto",
    "setu": "seto",
}

GIELLA_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "vro": ("analyzer", "generator", "speller", "grammar"),
    "mulgi": ("analyzer", "generator", "speller", "grammar"),
    "seto": ("analyzer", "generator", "speller", "grammar"),
}


def normalize_giella_lang(lang: str | None = None) -> str:
    if lang is None:
        return "vro"
    key = str(lang).strip().casefold()
    resolved = _GIELLA_LANG_ALIASES.get(key)
    if resolved is None:
        raise ValueError(
            f"Unsupported GiellaLT language {lang!r}. Expected one of: {', '.join(GIELLA_LANGS)}."
        )
    return resolved


@dataclass(frozen=True)
class CommandSpec:
    name: str
    command: str
    env_var: str
    setup_hint: str


class GiellaAdapter:
    def __init__(
        self,
        analyzer_cmd: str,
        generator_cmd: str,
        speller_cmd: str,
        grammar_cmd: str,
        *,
        giella_share_dir: Path | None = None,
    ):
        self.giella_share_dir = giella_share_dir
        self.commands = {
            "analyzer": CommandSpec(
                "analyzer",
                analyzer_cmd,
                "VRO_ANALYZER_CMD",
                "Create a repo-local analyzer wrapper, for example tools/giella/bin/analyze-vro.",
            ),
            "generator": CommandSpec(
                "generator",
                generator_cmd,
                "VRO_GENERATOR_CMD",
                "Create a repo-local generator wrapper, for example tools/giella/bin/generate-vro.",
            ),
            "speller": CommandSpec(
                "speller",
                speller_cmd,
                "VRO_SPELLER_CMD",
                "Create a repo-local speller wrapper, for example tools/giella/bin/spellcheck-vro.",
            ),
            "grammar": CommandSpec(
                "grammar",
                grammar_cmd,
                "VRO_GRAMMAR_CMD",
                "Create a repo-local grammar wrapper, for example tools/giella/bin/grammar-check-vro.",
            ),
        }
        self._availability_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._availability_lock = threading.Lock()

    def analyze_word(self, word: str, *, lang: str = "vro") -> dict[str, Any]:
        return self._run_text_tool("analyzer", word.strip(), lang=lang)

    def analyze_words(self, words: list[str], *, lang: str = "vro") -> dict[str, Any]:
        """Analyze many words in ONE analyzer process. Results are keyed by the
        surface form (the analyzer echoes it as the first tab-column)."""
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"available": False, "error": "invalid_parameter", "detail": str(exc), "results": {}}

        spec = self.commands["analyzer"]
        availability = self._availability_for(spec, lang=canon_lang)
        if not availability["available"]:
            return {"available": False, "lang": canon_lang, "setup": availability, "results": {}}

        cleaned = [w.strip() for w in words if w and w.strip()]
        if not cleaned:
            return {"available": True, "lang": canon_lang, "command": spec.command, "results": {}}

        args = shlex.split(spec.command)
        try:
            completed = subprocess.run(
                args,
                input="\n".join(cleaned) + "\n",
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
                env=self._env_for_lang(canon_lang),
            )
        except OSError as exc:
            self._invalidate_availability(spec.name, canon_lang)
            return {"available": False, "lang": canon_lang, "setup": self._unavailable(spec, str(exc), lang=canon_lang), "results": {}}
        except subprocess.TimeoutExpired:
            return {"available": False, "lang": canon_lang, "error": "analyzer timed out after 60 seconds", "results": {}}

        grouped: dict[str, list[str]] = {}
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            surface = line.split("\t", 1)[0]
            grouped.setdefault(surface, []).append(line)

        results: dict[str, Any] = {}
        for word in cleaned:
            lines = grouped.get(word, [])
            # A word is unrecognized when its only analysis line ends in "+?".
            recognized = any(not line.rstrip().endswith("+?") for line in lines)
            results[word] = {
                "available": True,
                "recognized": recognized,
                "lines": lines,
                "output": "\n".join(lines),
            }
        return {
            "available": True,
            "lang": canon_lang,
            "command": spec.command,
            "exit_code": completed.returncode,
            "results": results,
            "stderr": completed.stderr.strip(),
        }

    def generate_forms(
        self,
        lemma: str,
        tags: str | None = None,
        *,
        lang: str = "vro",
    ) -> dict[str, Any]:
        suffix = tags.strip() if tags else None
        text = lemma.strip() if suffix is None else f"{lemma.strip()}\t{suffix.strip()}"
        return self._run_text_tool("generator", text, lang=lang)

    def generate_many(
        self,
        queries: list[str],
        *,
        lang: str = "vro",
    ) -> dict[str, Any]:
        """Generate forms for many `lemma+tags` strings in ONE generator process.
        Results are keyed by the input analysis string."""
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"available": False, "error": "invalid_parameter", "detail": str(exc), "results": {}}

        spec = self.commands["generator"]
        availability = self._availability_for(spec, lang=canon_lang)
        if not availability["available"]:
            return {"available": False, "lang": canon_lang, "setup": availability, "results": {}}

        cleaned = [q.strip() for q in queries if q and q.strip()]
        if not cleaned:
            return {"available": True, "lang": canon_lang, "command": spec.command, "results": {}}

        args = shlex.split(spec.command)
        try:
            completed = subprocess.run(
                args,
                input="\n".join(cleaned) + "\n",
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
                env=self._env_for_lang(canon_lang),
            )
        except OSError as exc:
            self._invalidate_availability(spec.name, canon_lang)
            return {
                "available": False,
                "lang": canon_lang,
                "setup": self._unavailable(spec, str(exc), lang=canon_lang),
                "results": {},
            }
        except subprocess.TimeoutExpired:
            return {"available": False, "lang": canon_lang, "error": "generator timed out after 60 seconds", "results": {}}

        grouped: dict[str, list[str]] = {}
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            key = parts[0].strip()
            form = parts[1].strip()
            if len(parts) >= 3 and parts[2].strip() != "0":
                continue
            if not form or form.endswith("+?"):
                continue
            bucket = grouped.setdefault(key, [])
            if form not in bucket:
                bucket.append(form)

        return {
            "available": True,
            "lang": canon_lang,
            "command": spec.command,
            "exit_code": completed.returncode,
            "results": {q: grouped.get(q, []) for q in cleaned},
            "stderr": completed.stderr.strip(),
        }

    def spellcheck(self, text: str, *, lang: str = "vro") -> dict[str, Any]:
        return self._run_text_tool("speller", text, lang=lang)

    def grammar_check(self, text: str, *, lang: str = "vro") -> dict[str, Any]:
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"available": False, "error": "invalid_parameter", "detail": str(exc)}
        if canon_lang == "vro":
            return self._run_text_tool("grammar", text, lang=canon_lang)

        pairs = opening_pairs(text)
        words = list(dict.fromkeys(word for subject, verb, _ in pairs for word in (subject, verb)))
        result = self.analyze_words(words, lang=canon_lang)
        if not result["available"]:
            return result
        if result.get("exit_code", 0):
            return {
                "available": False,
                "lang": canon_lang,
                "error": "grammar_analyzer_failed",
                "detail": result["stderr"],
            }
        analyses = {}
        for word, analysis in result["results"].items():
            readings = (line.split("\t") for line in analysis["lines"])
            analyses[word] = {fields[1] for fields in readings if len(fields) >= 3 and fields[2] != "+?"}
        return {
            "available": True,
            "lang": canon_lang,
            "findings": list(copula_findings(canon_lang, pairs, analyses)),
        }

    def availability(self, *, refresh: bool = True, lang: str = "vro") -> dict[str, Any]:
        canon_lang = normalize_giella_lang(lang)
        return {
            key: self._availability_for(spec, lang=canon_lang, refresh=refresh)
            for key, spec in self.commands.items()
        }

    def availability_by_language(self, *, refresh: bool = True) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for lang_code in GIELLA_LANGS:
            caps = GIELLA_CAPABILITIES.get(lang_code, tuple(self.commands.keys()))
            out[lang_code] = {
                key: self._availability_for(self.commands[key], lang=lang_code, refresh=refresh)
                for key in caps
            }
        return out

    def _invalidate_availability(self, name: str, lang: str) -> None:
        with self._availability_lock:
            self._availability_cache.pop((name, lang), None)

    def _env_for_lang(self, lang: str) -> dict[str, str]:
        env = dict(os.environ)
        env["GIELLA_LANG"] = lang
        if self.giella_share_dir is not None:
            env.setdefault("VRO_GIELLA_SHARE_DIR", str(self.giella_share_dir))
        return env

    def _run_text_tool(self, key: str, text: str, *, lang: str = "vro") -> dict[str, Any]:
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"available": False, "error": "invalid_parameter", "detail": str(exc)}

        spec = self.commands[key]
        availability = self._availability_for(spec, lang=canon_lang)
        if not availability["available"]:
            return {"available": False, "lang": canon_lang, "setup": availability}
        if not text:
            return {"available": True, "lang": canon_lang, "output": "", "lines": []}

        args = shlex.split(spec.command)
        try:
            completed = subprocess.run(
                args,
                input=text + "\n",
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
                env=self._env_for_lang(canon_lang),
            )
        except OSError as exc:
            self._invalidate_availability(spec.name, canon_lang)
            return {"available": False, "lang": canon_lang, "setup": self._unavailable(spec, str(exc), lang=canon_lang)}
        except subprocess.TimeoutExpired:
            return {
                "available": False,
                "lang": canon_lang,
                "error": f"{spec.name} timed out after 30 seconds",
            }

        output = completed.stdout.strip()
        error = completed.stderr.strip()
        return {
            "available": True,
            "lang": canon_lang,
            "command": spec.command,
            "exit_code": completed.returncode,
            "output": output,
            "lines": [line for line in output.splitlines() if line],
            "stderr": error,
        }

    def _availability_for(self, spec: CommandSpec, *, lang: str = "vro", refresh: bool = False) -> dict[str, Any]:
        if spec.name == "grammar" and lang in ("mulgi", "seto"):
            return self._availability_for(self.commands["analyzer"], lang=lang, refresh=refresh)
        cache_key = (spec.name, lang)
        if not refresh:
            with self._availability_lock:
                cached = self._availability_cache.get(cache_key)
                if cached is not None:
                    return cached

        result = self._probe_availability(spec, lang=lang)
        with self._availability_lock:
            self._availability_cache[cache_key] = result
        return result

    def _probe_availability(self, spec: CommandSpec, *, lang: str = "vro") -> dict[str, Any]:
        args = shlex.split(spec.command)
        if not args:
            return self._unavailable(spec, "empty command", lang=lang)

        executable = args[0]
        if os.sep in executable:
            path = Path(executable)
            if path.exists() and os.access(path, os.X_OK):
                check = self._run_check(args, env=self._env_for_lang(lang))
                if check is not None and check.returncode != 0:
                    reason = check.stderr.strip() or check.stdout.strip() or f"{spec.name} --check failed"
                    return self._unavailable(spec, reason, lang=lang)
                return {"available": True, "lang": lang, "command": spec.command}
            return self._unavailable(spec, f"{path} is missing or not executable", lang=lang)

        if shutil.which(executable):
            return {"available": True, "lang": lang, "command": spec.command}
        return self._unavailable(spec, f"{executable} was not found on PATH", lang=lang)

    @staticmethod
    def _run_check(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                [*args, "--check"],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _unavailable(spec: CommandSpec, reason: str, *, lang: str = "vro") -> dict[str, Any]:
        return {
            "available": False,
            "name": spec.name,
            "lang": lang,
            "command": spec.command,
            "env_var": spec.env_var,
            "reason": reason,
            "setup_hint": spec.setup_hint,
        }
