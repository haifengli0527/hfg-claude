import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = {
    "README.md": ROOT / "README.md",
    "SKILL.md": ROOT / "skills/hfg/SKILL.md",
    "builder.md": ROOT / "agents/builder.md",
    "example": ROOT / "examples/HFG_example-env-guards.md",
}


def read_document(path):
    return path.read_text(encoding="utf-8")


def markdown_slug(heading):
    heading = re.sub(r"<[^>]+>", "", heading).strip().lower()
    heading = re.sub(r"[^\w\u0080-\uffff -]", "", heading)
    return re.sub(r"\s+", "-", heading)


def heading_anchors(text):
    anchors = set()
    for match in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        base = markdown_slug(match.group(1))
        candidate = base
        suffix = 1
        while candidate in anchors:
            candidate = f"{base}-{suffix}"
            suffix += 1
        anchors.add(candidate)
    return anchors


class RepositoryContractTests(unittest.TestCase):
    def test_skill_and_agent_frontmatter(self):
        for label, path in (("SKILL.md", DOCUMENTS["SKILL.md"]), ("builder.md", DOCUMENTS["builder.md"])):
            self.assertTrue(path.is_file(), f"missing {label}")
            text = read_document(path)
            match = re.match(r"\A---\s*\n(?P<body>.*?)\n---\s*(?:\n|\Z)", text, re.DOTALL)
            self.assertIsNotNone(match, f"{label} must start with YAML frontmatter")
            body = match.group("body")
            for field in ("name", "description"):
                self.assertRegex(body, rf"(?m)^{field}:\s*\S.+$", f"{label} missing {field}")

    def test_local_markdown_links_exist(self):
        pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
        for label, path in DOCUMENTS.items():
            text = read_document(path)
            for target in pattern.findall(text):
                file_target, separator, anchor = target.partition("#")
                file_target = file_target.strip()
                if not file_target and not separator:
                    continue
                if file_target and re.match(r"(?:[a-z][a-z0-9+.-]*:|//)", file_target, re.I):
                    continue
                target_path = path if not file_target else (path.parent / file_target).resolve()
                self.assertTrue(target_path.is_file(), f"{label}: broken link {file_target or target}")
                if separator:
                    self.assertIn(anchor, heading_anchors(read_document(target_path)), f"{label}: broken anchor #{anchor}")

    def test_planning_sections_are_complete(self):
        expected = {"0", "1", "2", "3", "4", "5", "6", "7", "7b", "8"}
        section_pattern = re.compile(r"(?m)^##\s+(0|1|2|3|4|5|6|7b|7|8)\.")
        for label in ("SKILL.md", "example"):
            sections = set(section_pattern.findall(read_document(DOCUMENTS[label])))
            self.assertEqual(expected, sections, f"{label}: planning sections mismatch")

    def test_readme_does_not_claim_nine_sections(self):
        text = read_document(DOCUMENTS["README.md"])
        self.assertNotRegex(text, r"九個區塊")
        self.assertRegex(text, r"十個區塊（0–8 加 7b）")

    def test_example_acceptance_rows_are_executable(self):
        text = read_document(DOCUMENTS["example"])
        table = text.split("## 1. 目標與驗收標準", 1)[1].split("## 2.", 1)[0]
        rows = [line for line in table.splitlines() if line.startswith("|") and "---" not in line]
        self.assertGreater(len(rows), 1)
        semantic_outputs = ("通過", "失敗", "輸出", "變更", "字串", "測試", "UUID", "項數", "0810", "true", "無 diff", "一致")
        for row in rows:
            self.assertGreaterEqual(row.count("|"), 3, row)
            command = row.split("|", 2)[2].strip()
            expected = row.rsplit("|", 2)[1].strip()
            self.assertTrue(command, row)
            self.assertNotIn("人工確認", command, row)
            self.assertTrue(any(token in expected for token in semantic_outputs), row)

    def test_skill_core_sections(self):
        text = read_document(DOCUMENTS["SKILL.md"])
        for phrase in ("偵察", "提問閘門", "交付前的機械稽核", "規劃書模板", "卡住時怎麼辦"):
            self.assertIn(phrase, text)

    def test_builder_contract(self):
        text = read_document(DOCUMENTS["builder.md"])
        self.assertRegex(text, r"卡在第 N 步\s*\n預期：X\s*\n實際：Y\s*\n已完成到：第 M 步")
        self.assertRegex(text, r"(?:不要|不) commit")
        self.assertRegex(text, r"(?:不要|不) push")

    def test_example_sections(self):
        text = read_document(DOCUMENTS["example"])
        for phrase in ("前置條件", "驗收標準", "逐步操作", "卡住時怎麼辦"):
            self.assertIn(phrase, text)

    def test_readme_install_sources_exist(self):
        text = read_document(DOCUMENTS["README.md"])
        for source in ("skills/hfg/SKILL.md", "agents/builder.md"):
            self.assertIn(source, text)
            self.assertTrue((ROOT / source).is_file(), f"missing installation source {source}")

    def test_ci_workflow_contract(self):
        path = ROOT / ".github/workflows/ci.yml"
        self.assertTrue(path.is_file(), "missing CI workflow")
        text = read_document(path)
        for token in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "'3.10'",
            "'3.11'",
            "'3.12'",
            "'3.13'",
            "python tests/run_tests.py",
            "git diff --check",
        ):
            self.assertIn(token, text, f"CI workflow missing {token}")


if __name__ == "__main__":
    unittest.main()
