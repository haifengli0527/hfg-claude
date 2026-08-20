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
                target = target.split("#", 1)[0].strip()
                if not target or re.match(r"(?:[a-z][a-z0-9+.-]*:|//)", target, re.I):
                    continue
                self.assertTrue((path.parent / target).resolve().is_file(), f"{label}: broken link {target}")

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
