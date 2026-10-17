#!/usr/bin/env python3
"""Safely import CodeArts/Huawei rule-set JSON exports from ZIP archives.

The importer is deliberately conservative: an archive is accepted only when
it contains JSON files (normally one), with safe relative names.  Nothing in
an archive is executed.  The original parsed JSON is copied as a raw snapshot
and a normalized catalog keeps the complete ``ruleInfos`` records keyed by
criterion-set id and rule id.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "rulesets"


class ImportErrorSafe(ValueError):
    """Raised when an archive does not satisfy the safe import contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_member(name: str) -> bool:
    # ZIP names use forward slashes, but reject backslashes too because an
    # archive may have been produced on Windows and later extracted elsewhere.
    if not name or name.endswith("/") or "\\" in name:
        return False
    if name.startswith(("/", "\\")) or ":" in name.split("/", 1)[0]:
        return False
    parts = name.split("/")
    return all(part not in ("", ".", "..") for part in parts) and posixpath.normpath(name) == name


def read_archive(path: Path) -> tuple[dict[str, Any], str, str]:
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ImportErrorSafe(f"not a ZIP archive: {path}")
    archive_sha = sha256_file(path)
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members:
                raise ImportErrorSafe(f"empty archive: {path}")
            for info in members:
                if not _safe_member(info.filename):
                    raise ImportErrorSafe(f"unsafe ZIP member name: {info.filename!r}")
                if not info.filename.lower().endswith(".json"):
                    raise ImportErrorSafe(f"archive contains non-JSON member: {info.filename}")
                # A JSON export is data only.  Refuse executable permission bits
                # even if the filename happens to end in .json.
                if (info.external_attr >> 16) & 0o111:
                    raise ImportErrorSafe(f"executable ZIP member rejected: {info.filename}")
            if len(members) != 1:
                raise ImportErrorSafe("archive must contain exactly one JSON export")
            info = members[0]
            try:
                payload = json.loads(archive.read(info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ImportErrorSafe(f"invalid UTF-8 JSON in {info.filename}: {exc}") from exc
    except zipfile.BadZipFile as exc:
        raise ImportErrorSafe(f"invalid ZIP archive: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ImportErrorSafe("rule-set JSON must be an object")
    criterion_id = payload.get("id")
    rules = payload.get("ruleInfos")
    if not isinstance(criterion_id, str) or not criterion_id:
        raise ImportErrorSafe("rule-set JSON is missing a non-empty id")
    if not isinstance(rules, list):
        raise ImportErrorSafe("rule-set JSON is missing ruleInfos array")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not rule["id"]:
            raise ImportErrorSafe(f"ruleInfos[{index}] is missing a non-empty id")
        if rule.get("criterionSetId") not in (None, criterion_id):
            raise ImportErrorSafe(f"ruleInfos[{index}].criterionSetId does not match rule-set id")
    return payload, archive_sha, info.filename


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def import_archives(archives: list[Path], out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    imported: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for archive_path in archives:
        payload, archive_sha, member = read_archive(archive_path.resolve())
        criterion_id = payload["id"]
        if criterion_id in seen_ids:
            raise ImportErrorSafe(f"duplicate criterion set id: {criterion_id}")
        seen_ids.add(criterion_id)
        raw_path = raw_dir / f"{criterion_id}.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rules = payload["ruleInfos"]
        for rule in rules:
            rule.setdefault("criterionSetId", criterion_id)
        imported.append({
            "criterion_set_id": criterion_id,
            "language": payload.get("language"),
            "name": payload.get("name"),
            "name_en": payload.get("nameEn"),
            "metadata": {k: v for k, v in payload.items() if k != "ruleInfos"},
            "rule_count": len(rules),
            "rules": rules,
            "source": {
                "archive": str(archive_path),
                "archive_sha256": archive_sha,
                "member": member,
                "imported_at": now,
            },
        })
    catalog = {
        "schema_version": "1.0",
        "generated_at": now,
        "criterion_sets": imported,
        "rules": [
            {"key": f"{item['criterion_set_id']}:{rule['id']}",
             "criterion_set_id": item["criterion_set_id"], "id": rule["id"],
             "rule": rule, "source": item["source"]}
            for item in imported for rule in item["rules"]
        ],
    }
    (out_dir / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = out_dir / "source-manifest.yaml"
    lines = ["# Generated by scripts/import_rules.py", "imports:"]
    for item in imported:
        source = item["source"]
        lines.extend([
            f"  - criterion_set_id: {_yaml_scalar(item['criterion_set_id'])}",
            f"    language: {_yaml_scalar(item['language'])}",
            f"    name: {_yaml_scalar(item['name'])}",
            f"    status: user-exported", f"    archive: {_yaml_scalar(source['archive'])}",
            f"    archive_sha256: {_yaml_scalar(source['archive_sha256'])}",
            f"    raw_snapshot: {_yaml_scalar(str(raw_dir / (item['criterion_set_id'] + '.json')))}",
            f"    rule_count: {item['rule_count']}",
        ])
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        catalog = import_archives(args.archives, args.out)
    except (OSError, ImportErrorSafe, zipfile.BadZipFile) as exc:
        print(f"import_rules: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"criterion_sets": len(catalog["criterion_sets"]), "rules": len(catalog["rules"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
