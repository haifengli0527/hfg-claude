# 貢獻指南

## 本地驗證

在 repo 任意目錄執行：

```bash
python3 tests/run_tests.py
python3 -m unittest discover -s tests -v
git diff --check
```

本 repo 的品質檢查只使用 Python 標準函式庫，不要加入第三方依賴或 `requirements.txt`。

修改 Markdown 或 frontmatter 後，提交 PR 前必須重新執行上述測試，確認連結、必要章節與 frontmatter 契約仍然成立。

## PR checklist

- [ ] 已執行 `python3 tests/run_tests.py`
- [ ] 已執行 `python3 -m unittest discover -s tests -v`
- [ ] 已執行 `git diff --check`
- [ ] 沒有加入第三方依賴
- [ ] Markdown/frontmatter 修改已由測試驗證
- [ ] PR 說明列出文件、測試或 CI 的影響
