import contextlib
import importlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills/hfg/scripts"
EXAMPLE = ROOT / "examples/HFG_example-env-guards.md"

sys.path.insert(0, str(SCRIPT_DIR))
pf = importlib.import_module("hfg_preflight")


FIXTURE_FILE = (
    b"function a() {\n"
    b"    return 1;\n"
    b"}\n"
    b"function b() {\n"
    b"    return 2;\n"
    b"}\n"
    b"const BUILD = 'BUILD 0901A';\n"
    b"const X = 1;\n"
    b"const X = 1;\n"
)

# 步驟 1：fence 縮 2 格、內容也縮 2 格——照原樣貼會失敗，扣掉 fence 縮排才成立 → INDENT
# 步驟 2：依賴步驟 1 套用後的內容 → OK（證明是「依序模擬」不是對原檔各自比）
# 步驟 3：內容縮排跟檔案差 2 格 → MISSING，且要指出是縮排差
# 步驟 4：old_string 出現 2 次 → DUPLICATE
# 步驟 5／6：Write 新檔，再 Edit 那個新檔 → 兩個都 OK
# 步驟 7：描述級 old_string → SKIP
# 步驟 8：驗證步驟，沒有工具 → 不列入
# 步驟 9：inline 反引號寫法 → OK
FIXTURE_PLAN = """# 施工規劃書：fixture

## 6. 逐步操作

### 步驟 1：改 a
- **工具**：Edit `src/app.js`
- **old_string**：
  ```
  function a() {
      return 1;
  }
  ```
- **new_string**：
  ```
  function a() {
      return 10; // step1
  }
  ```

### 步驟 2：依賴步驟 1 的結果
- **工具**：Edit `src/app.js`
- **old_string**：
```
    return 10; // step1
```
- **new_string**：
```
    return 11; // step2
```

### 步驟 3：縮排錯
- **工具**：Edit `src/app.js`
- **old_string**：
```
function b() {
  return 2;
}
```
- **new_string**：
```
function b() {
  return 20;
}
```

### 步驟 4：不唯一
- **工具**：Edit `src/app.js`
- **old_string**：
```
const X = 1;
```
- **new_string**：
```
const X = 2;
```

### 步驟 5：新建檔案
- **工具**：Write `src/new.js`
- **內容**：
```js
export const y = 1;
```

### 步驟 6：改剛新建的檔案
- **工具**：Edit `src/new.js`
- **old_string**：`export const y = 1;`
- **new_string**：`export const y = 2;`

### 步驟 7：描述級（違規）
- **工具**：Edit `src/app.js`
- **old_string**：把 grep 到的那一行貼進來
- **new_string**：
```
whatever
```

### 步驟 8：驗證
- **指令**：`node src/app.js`
- **預期結果**：無輸出

### 步驟 9：更新 BUILD
- **工具**：Edit `src/app.js`
- **old_string**：`BUILD 0901A`
- **new_string**：`BUILD 0901B`

## 7. 完成後自我檢查清單
"""

CLEAN_PLAN = """### 步驟 1：改 a
- **工具**：Edit `src/app.js`
- **old_string**：
```
function a() {
    return 1;
}
```
- **new_string**：
```
function a() {
    return 10;
}
```
"""


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = pf.main(argv)
    return code, buf.getvalue()


STATUS_RE = re.compile(r"^步驟 (\S+)\s+(?:Edit|Write)\s+\S+(?: #\d+)?\s+([A-Z?]+)")


def status_of(output, step):
    for line in output.splitlines():
        m = STATUS_RE.match(line)
        if m and m.group(1) == step:
            return m.group(2)
    return None


class PreflightTests(unittest.TestCase):
    def make_project(self, plan_text):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "src").mkdir()
        (tmp / "src/app.js").write_bytes(FIXTURE_FILE)
        (tmp / "plan.md").write_bytes(plan_text.encode("utf-8"))
        return tmp

    def test_parses_example_plan(self):
        text, _ = pf.read_text(EXAMPLE)
        steps = pf.parse_plan(text)
        edits = [s for s in steps if s.tool in ("Edit", "Write")]
        self.assertGreaterEqual(len(edits), 3)
        self.assertTrue({s.path for s in edits} <= {"app.html", "tests/run_tests.js"}, {s.path for s in edits})
        first = next(s for s in steps if s.number == "1")
        self.assertEqual(len(first.pairs), 1)
        self.assertIsNotNone(first.pairs[0].old)
        self.assertIsNotNone(first.pairs[0].new)
        self.assertIn("function genRecordId()", first.pairs[0].old.raw)

    def test_check_mode_reports_every_status(self):
        tmp = self.make_project(FIXTURE_PLAN)
        out_dir = tmp / "dry"
        code, out = run([str(tmp / "plan.md"), "--root", str(tmp), "--out", str(out_dir)])
        self.assertEqual(code, 1, out)
        expected = {"1": "INDENT", "2": "OK", "3": "MISSING", "4": "DUPLICATE", "5": "OK", "6": "OK", "7": "SKIP", "9": "OK"}
        for step, status in expected.items():
            self.assertEqual(status_of(out, step), status, f"步驟 {step}\n{out}")
        self.assertIsNone(status_of(out, "8"), "驗證步驟不該被列入")
        self.assertIn("內容相同但縮排不同", out)
        self.assertIn("出現 2 次", out)
        simulated = (out_dir / "src/app.js").read_bytes().decode("utf-8")
        self.assertIn("return 11; // step2", simulated)
        self.assertIn("BUILD 0901B", simulated)
        self.assertIn("const X = 1;\nconst X = 1;", simulated, "DUPLICATE 不該被套用")
        self.assertEqual((out_dir / "src/new.js").read_bytes().decode("utf-8"), "export const y = 2;")

    def test_clean_plan_exits_zero(self):
        tmp = self.make_project(CLEAN_PLAN)
        code, out = run([str(tmp / "plan.md"), "--root", str(tmp)])
        self.assertEqual(code, 0, out)
        self.assertIn("全部 OK", out)

    def test_applied_mode_checks_new_string_first(self):
        tmp = self.make_project(CLEAN_PLAN)
        code, out = run([str(tmp / "plan.md"), "--root", str(tmp), "--applied"])
        self.assertEqual(code, 0)
        self.assertIn("PENDING", out)
        (tmp / "src/app.js").write_bytes(FIXTURE_FILE.replace(b"return 1;", b"return 10;"))
        code, out = run([str(tmp / "plan.md"), "--root", str(tmp), "--applied"])
        self.assertIn("APPLIED", out)
        self.assertNotIn("PENDING", out)

    def test_crlf_file_is_compared_normalised(self):
        tmp = self.make_project(CLEAN_PLAN)
        (tmp / "src/app.js").write_bytes(FIXTURE_FILE.replace(b"\n", b"\r\n"))
        code, out = run([str(tmp / "plan.md"), "--root", str(tmp), "--out", str(tmp / "dry")])
        self.assertEqual(code, 0, out)
        self.assertIn("CRLF", out)
        self.assertIn(b"\r\n", (tmp / "dry/src/app.js").read_bytes())


if __name__ == "__main__":
    unittest.main()
