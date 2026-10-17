from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import_rules.py"
spec = importlib.util.spec_from_file_location("import_rules", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


DOWNLOADS = Path("/Users/wangminghai/Downloads")


class ImportRulesTests(unittest.TestCase):
    def test_real_exports_create_raw_catalog_and_manifest(self):
        archives = [
            DOWNLOADS / "华为python编程规范集.zip",
            DOWNLOADS / "typescript编程集.zip",
            DOWNLOADS / "华为javascript编程规范集.zip",
            DOWNLOADS / "华为java编程规范集.zip",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            catalog = module.import_archives(archives, Path(tmp))
            self.assertEqual(len(catalog["criterion_sets"]), 4)
            self.assertGreater(len(catalog["rules"]), 400)
            self.assertTrue((Path(tmp) / "catalog.json").is_file())
            self.assertTrue((Path(tmp) / "source-manifest.yaml").is_file())
            for item in catalog["criterion_sets"]:
                raw = Path(tmp) / "raw" / f"{item['criterion_set_id']}.json"
                self.assertTrue(raw.is_file())
                self.assertEqual(json.loads(raw.read_text())["id"], item["criterion_set_id"])
                digest = hashlib.sha256(item["source"]["archive"].encode()).hexdigest()
                self.assertNotEqual(digest, item["source"]["archive_sha256"])

    def make_zip(self, directory: Path, members: dict[str, bytes]) -> Path:
        path = directory / "fixture.zip"
        with zipfile.ZipFile(path, "w") as z:
            for name, body in members.items():
                z.writestr(name, body)
        return path

    def test_path_traversal_and_non_json_are_rejected(self):
        payload = json.dumps({"id": "set", "ruleInfos": []}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for members in ({"../escape.json": payload}, {"rules.json": payload, "run.sh": b"echo bad"}):
                with self.subTest(members=list(members)):
                    with self.assertRaises(module.ImportErrorSafe):
                        module.read_archive(self.make_zip(root, members))

    def test_rule_identity_is_set_id_plus_rule_id_and_names_are_not_deduped(self):
        def payload(set_id, rule_ids):
            return {"id": set_id, "language": "PYTHON", "ruleInfos": [{"id": i, "name": "same"} for i in rule_ids]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name, data in (("a", payload("set-a", ["r1"])), ("b", payload("set-b", ["r1"]))):
                p = root / f"{name}.zip"
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr(f"{name}.json", json.dumps(data))
                paths.append(p)
            catalog = module.import_archives(paths, root / "out")
            self.assertEqual({x["key"] for x in catalog["rules"]}, {"set-a:r1", "set-b:r1"})

    def test_invalid_rule_set_shape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_zip(Path(tmp), {"x.json": b'{"id":"x","ruleInfos":{}}'})
            with self.assertRaises(module.ImportErrorSafe):
                module.read_archive(path)


if __name__ == "__main__":
    unittest.main()
