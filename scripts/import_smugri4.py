"""Import reviewed noncommercial components from the original SMUGRI-4 files."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from vro_mcp.db import _norm_gloss, normalize_db_text

REVISION = "902597137be2310f03f5b33292cb01c7585d639b"
BLOB_URL = f"https://huggingface.co/datasets/tartuNLP/smugri4-data/blob/{REVISION}/"
MONOLINGUAL = (
    ("smugri4_umaleht", "umaleht", "vro", "est_vro_stand_uma"),
    ("smugri4_setomaa_2020jne", "setomaa_2020jne", "seto", "est_vro_seto"),
    ("smugri4_ilo", "ilo", "vro", "est_vro_x"),
    ("smugri4_setomaa_archive", "setomaa", "seto", "est_vro_seto"),
    ("smugri4_vro_est", "vro-est", "vro", "est_vro_x"),
)
PAIRS = "smugri4_vro_laused"
GLOSSARY = "smugri4_vasted_n"
SEPARATOR = re.compile(r"(?<!\S)V(?!\S)")


class Snapshot:
    def __init__(self, root: Path):
        self.root = root
        entries = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-rz", REVISION])
        self.blobs = {}
        for entry in entries.split(b"\0"):
            if entry:
                meta, name = entry.split(b"\t", 1)
                self.blobs[name.decode("utf-8")] = meta.split()[2].decode("ascii")
        card = self.read("README.md").decode("utf-8")
        if "cc-by-nc-sa-4.0" not in card.split("---", 2)[1]:
            raise ValueError("Expected the pinned noncommercial dataset license")

    def read(self, path: str) -> bytes:
        payload = (self.root / path).read_bytes()
        expected = self.blobs[path]
        blob = hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()
        if blob == expected and not payload.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            return payload

        pointer = (payload if blob == expected else subprocess.check_output(
            ["git", "-C", str(self.root), "cat-file", "blob", expected]
        ))
        match = re.fullmatch(
            rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize (\d+)\n",
            pointer,
        )
        if match:
            if payload == pointer:
                payload = (self.root.parent / "lfs_objects" / path).read_bytes()
            if hashlib.sha256(payload).hexdigest() == match[1].decode("ascii") and len(payload) == int(match[2]):
                return payload
        raise ValueError(f"Provider file differs from {REVISION}: {path}")

    def records(self, path: str, component: str, kind: str):
        for record in json.loads(self.read(path)):
            features = record["features"]
            if features["corpus"] != component:
                raise ValueError(f"Unexpected component in {path}")
            yield features, record[kind]


def canonical(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def forms(value: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(text.strip() for text in value if text.strip()))


def insert_units(conn, units, credits):
    conn.executemany("""
        INSERT INTO corpus_units (unit_id, lang, unit_level, doc_id, unit_idx, source_slug,
                                  text, lid_lang, lid_conf)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, units)
    conn.executemany("INSERT INTO corpus_documents VALUES (?, ?, ?, ?)", credits)


def import_monolingual(conn, snapshot: Snapshot, seen: set[tuple[str, str]]) -> dict:
    counts = {}
    for slug, component, default_lang, field in MONOLINGUAL:
        units, credits = [], []
        skipped = Counter()
        root = f"vro/mono/{component}/"
        paths = sorted(path for path in snapshot.blobs if path.startswith(root) and path.endswith(".texts.json"))
        if not paths:
            raise ValueError(f"No reviewed files for {component}")
        for path in paths:
            file_id = snapshot.blobs[path][:20]
            for container_idx, (features, records) in enumerate(snapshot.records(path, component, "texts")):
                metadata = features.get("text_metainfo") or {}
                lang = "seto" if str(metadata.get("kiil:", "")).casefold() == "seto" else default_lang
                for doc_idx, document in enumerate(records):
                    doc_id = f"{slug}:{file_id}:{container_idx}:{doc_idx}"
                    unit_count = len(units)
                    for idx, paragraph in enumerate(document[field].splitlines()):
                        text = paragraph.strip()
                        key = (lang, canonical(text))
                        if not any(char.isalpha() for char in text):
                            skipped["blank_or_nontext"] += 1
                            continue
                        if key in seen:
                            skipped["duplicate"] += 1
                            continue
                        seen.add(key)
                        units.append((f"{doc_id}:p{idx}", lang, "paragraph", doc_id, idx, slug, text, lang))
                    if len(units) > unit_count:
                        title = metadata.get("päälkiri:") or metadata.get("Välläannõq:") or features.get("filename")
                        author = metadata.get("autor:")
                        credits.append((doc_id, title, author, BLOB_URL + quote(path)))
        insert_units(conn, units, credits)
        counts[slug] = {"files": len(paths), "documents": len(credits),
                        "units": len(units), **skipped}
    return counts


def phrase_blocks(snapshot: Snapshot, component: str):
    for variant, suffix in enumerate(("phrases.dict.json", "phrases.json")):
        path = f"vro/multi/{component}/{component}.est-vro.{suffix}"
        for block, (_, records) in enumerate(snapshot.records(path, component, "phrases")):
            yield f"{variant}:{block}", BLOB_URL + path, records


def import_pairs(conn, snapshot: Snapshot) -> dict:
    existing = {
        (canonical(source), canonical(target))
        for source, target in conn.execute("""
            SELECT u.text, t.translated_text FROM corpus_translations t JOIN corpus_units u ON u.id=t.unit_rowid
            WHERE u.lang='vro' AND t.target_lang='et'
        """).fetchall()
    }
    units, credits, translations = [], [], []
    skipped = Counter()
    for block, url, records in phrase_blocks(snapshot, "laused_n"):
        for index, row in enumerate(records):
            vro, et = forms(row["est_vro_stand_sõnaq"]), forms(row["est"])
            if len(vro) != 1 or len(et) != 1 or SEPARATOR.search(vro[0]) or SEPARATOR.search(et[0]):
                skipped["ambiguous"] += 1
                continue
            key = canonical(vro[0]), canonical(et[0])
            if key[0] == key[1]:
                skipped["identical_sides"] += 1
                continue
            if key in existing:
                skipped["duplicate"] += 1
                continue
            existing.add(key)
            unit_id = f"{PAIRS}:{block}:{index}"
            units.append((unit_id, "vro", "sentence", unit_id, 0, PAIRS, vro[0], "vro"))
            credits.append((unit_id, "laused_n", None, url))
            translations.append((et[0], unit_id))
    insert_units(conn, units, credits)
    conn.executemany("""
        INSERT INTO corpus_translations (unit_rowid, lang, target_lang, translated_text, origin, engine, reliability)
        SELECT id, 'vro', 'et', ?, 'human', 'smugri4-laused_n', 750 FROM corpus_units WHERE unit_id = ?
    """, translations)
    return {"units": len(units), "translations": len(translations), **skipped}


def import_glossary(conn, snapshot: Snapshot) -> dict:
    seen = set()
    entries, definitions = [], []
    skipped = Counter()
    for block, url, records in phrase_blocks(snapshot, "vasted_n"):
        for index, row in enumerate(records):
            vro, et = forms(row["est_vro_stand_sõnaq"]), forms(row["est"])
            if not vro or not et or any(SEPARATOR.search(form) for form in (*vro, *et)):
                skipped["ambiguous"] += 1
                continue
            key = tuple(sorted(map(canonical, vro))), tuple(sorted(map(canonical, et)))
            if key in seen:
                skipped["duplicate"] += 1
                continue
            seen.add(key)
            entry_id = f"{GLOSSARY}:{block}:{index}"
            entries.append((entry_id, vro[0], normalize_db_text(vro[0]), json.dumps(vro[1:], ensure_ascii=False), GLOSSARY, url))
            definitions.extend((gloss, _norm_gloss(gloss), entry_id) for gloss in et)
    conn.executemany("""
        INSERT INTO dict_entries (entry_id, lang, headword, lookup_key, variants, source_slug, source_url)
        VALUES (?, 'vro', ?, ?, ?, ?, ?)
    """, entries)
    # Resolve row IDs in one scan because entry_id has no global index.
    row_ids = {key: rid for key, rid in conn.execute("SELECT entry_id, id FROM dict_entries WHERE source_slug = ?", (GLOSSARY,)).fetchall()}
    conn.executemany("""
        INSERT INTO dict_definitions (entry_rowid, lang, target_lang, definition_text, norm_def)
        VALUES (?, 'vro', 'et', ?, ?)
    """, [(row_ids[key], gloss, norm) for gloss, norm, key in definitions])
    return {"entries": len(entries), "definitions": len(definitions), **skipped}


# Zero-based records whose Estonian sides failed the corpus direction audit.
SETO_BAD_TARGETS = {33330, 36550, 38061, 40146}


def paired_units(row, component, field):
    source = row[field]
    targets = {code: row[key] for key, code in (("est", "et"), ("eng", "en"), ("deu", "de")) if key in row}
    if component != "vro-est":
        yield 0, "sentence" if component == "eki_dictionary" else "paragraph", source, targets
        return

    lines = source.splitlines()
    target_lines = {code: text.splitlines() for code, text in targets.items()}
    # Preserve the published line positions only when every side has matching
    # line and blank-line boundaries. Otherwise retain the published document pair.
    if all(len(side) == len(lines) and all(bool(a.strip()) == bool(b.strip()) for a, b in zip(lines, side))
           for side in target_lines.values()):
        for idx, line in enumerate(lines):
            yield idx, "sentence", line, {code: side[idx] for code, side in target_lines.items()}
    else:
        yield 0, "document", source, targets


def import_additional_pairs(conn, snapshot: Snapshot) -> dict:
    providers = (
        ("smugri4_vro_est", "vro/multi/vro-est/", "vro-est", "vro", "est_vro_x", "texts", "smugri4-vro-est"),
        ("smugri4_cifu_appeal", "vro/multi/cifu_poordamine/", "cifu_poordamine", "vro", "est_vro_x", "texts", "smugri4-cifu"),
        ("smugri4_mulgi_dictionary", "eesti_murded/mulgi/multi/eki_dictionary/", "eki_dictionary", "mulgi", "est_mulgi_ekidct", "sentences", "smugri4-eki-dictionary"),
        ("smugri4_seto_dictionary", "eesti_murded/setu/multi/eki_dictionary/", "eki_dictionary", "seto", "est_setu_ekidct", "sentences", "smugri4-eki-dictionary"),
    )
    existing = {(lang, code, canonical(src), canonical(tgt)) for lang, code, src, tgt in conn.execute("""
        SELECT u.lang, t.target_lang, u.text, t.translated_text
        FROM corpus_translations t JOIN corpus_units u ON u.id=t.unit_rowid
    """).fetchall()}
    results = {}
    for slug, folder, component, lang, field, kind, engine in providers:
        units, credits, translations = [], [], []
        skipped = Counter()
        paths = sorted(path for path in snapshot.blobs if path.startswith(folder) and path.endswith(".json"))
        if not paths:
            raise ValueError(f"No published files under {folder}")
        for path in paths:
            url = BLOB_URL + quote(path)
            file_id = hashlib.sha256(path.encode()).hexdigest()[:20]
            for block, (features, records) in enumerate(snapshot.records(path, component, kind)):
                for row_index, row in enumerate(records):
                    doc_id = f"{slug}:{file_id}:{block}:{row_index}"
                    before = len(units)
                    for part, level, text, targets in paired_units(row, component, field):
                        text = text.strip()
                        if not any(char.isalpha() for char in text):
                            continue
                        unit_id = f"{doc_id}:{part}"
                        source_key = canonical(text)
                        new_targets = 0
                        omit_gloss = lang == "seto" and block == 0 and row_index in SETO_BAD_TARGETS
                        for code, target in targets.items():
                            target = target.strip()
                            key = (lang, code, source_key, canonical(target))
                            if not target or omit_gloss:
                                if omit_gloss:
                                    skipped["audited_glosses_omitted"] += 1
                                continue
                            if key in existing:
                                skipped["duplicate_pairs"] += 1
                                continue
                            existing.add(key)
                            # Dictionary rows are contextual examples and can also be single-word glosses.
                            reliability = 700 if component == "eki_dictionary" else 850
                            translations.append((lang, code, target, engine, reliability, unit_id))
                            new_targets += 1
                        if new_targets or omit_gloss:
                            units.append((unit_id, lang, level, doc_id, part, slug, text, lang))
                    if len(units) > before:
                        credits.append((doc_id, features["filename"], None, url))
        insert_units(conn, units, credits)
        conn.executemany("""
            INSERT INTO corpus_translations (unit_rowid, lang, target_lang, translated_text, origin, engine, reliability)
            SELECT id, ?, ?, ?, 'human', ?, ? FROM corpus_units WHERE unit_id = ?
        """, translations)
        results[slug] = {"files": len(paths), "units": len(units),
                         "translations": len(translations), **skipped}
    return results


def import_smugri4(conn, root: Path) -> dict:
    snapshot = Snapshot(root)
    seen = {(lang, canonical(text)) for lang, text in conn.execute("SELECT lang,text FROM corpus_units").fetchall()}
    mono = import_monolingual(conn, snapshot, seen)
    results = {
        **mono,
        PAIRS: import_pairs(conn, snapshot),
        GLOSSARY: import_glossary(conn, snapshot),
    }
    additional = import_additional_pairs(conn, snapshot)
    parallel = additional["smugri4_vro_est"]
    for key in ("files", "units"):
        parallel[key] += mono["smugri4_vro_est"][key]
    return {**results, **additional}
