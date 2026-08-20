# hfg — 強模型規劃、弱模型施工的交接規劃書產生器

`hfg`（**H**and**f**or-**g**o，暫定名）是一個 [Claude Code](https://docs.claude.com/claude-code) skill，
搭配一個叫 `builder` 的 subagent 使用。

**這是 Claude Code 專用的工具**：規劃書模板與「弱模型行為契約」這套方法論是通用的、
換到任何 LLM 交接情境都能用；但實際觸發方式（`/hfg` slash command）、派工機制（Agent tool、
`subagent_type`、`SendMessage` 續傳）都是 Claude Code 特定的功能。拿到別的環境要自己接。

> **誠實聲明**：這是一次實戰的歸納——在單一專案上跑過約 15 個工作項、多次施工中斷，
> 不是通用最佳實踐。已知限制見下方「已知限制」一節。

---

## 解決什麼問題

用強模型（例如 Opus）規劃、弱一點或另一個 session 的模型（例如 Sonnet）施工，
是省 token、省時間的常見做法。但這個分工有一個常被忽略的失敗模式：

**執行端看不到規劃端的對話。** 規劃時腦中想清楚的取捨、沒說出口的假設、
「這裡先這樣做就好」的默契，執行端一概不知道。如果規劃書寫得不夠死，
執行端會用自己的判斷補完空隙——而它的判斷不是你要的那個。

`hfg` 的做法是把「想清楚」這件事，在規劃階段用強模型一次做完、寫成一份
**逐字級、可獨立使用的施工規劃書**：不留 TBD、不留「視情況而定」、每個技術取捨當場拍板。
執行端不需要猜，只需要照做；猜不出來的地方，規劃書會明寫「卡住時怎麼辦」。

## 為什麼需要行為契約

規劃書寫得再仔細，也擋不住執行端「好心」自己補完。實測過的失敗模式是：

- 驗收指令失敗 → 執行端自己放寬判準，讓它過
- `old_string` 找不到 → 執行端自己找了個相似的位置改下去
- 規劃書某處看起來像寫錯了 → 執行端自行改用「看起來更合理」的做法

這些行為單獨看都是「熱心幫忙」，合起來的結果是：**你收到一份「全部完成」的報告，
但實際做的東西跟規劃書不一樣，而你不知道哪裡不一樣。**

`builder`（見 [`agents/builder.md`](agents/builder.md)）存在的理由就是堵死這條路：
明確禁止自行修判準、禁止自行找替代方案、禁止跳過失敗的步驟。
卡住就照固定格式回報「卡在第 N 步／預期 X／實際 Y／已完成到第 M 步」然後停下，
把判斷權交還給派工者。**一個做到一半但誠實的狀態，遠勝於一個自己補完的版本。**

## 三個真實中斷案例

以下是同一輪施工（一次 UI 改動，含清理未使用的 CSS class）裡真實發生的三次中斷，
**全部落在「驗收判準寫錯」，沒有一次落在「不知道該做什麼」**——這也是為什麼
`hfg` 花最多篇幅在「交付前機械稽核」而不是規劃書格式本身：

1. **判準用了沒查證的估計值。** 規劃書寫「應該有 ≥15 處符合」，實測只有 13 處，
   而程式碼其實是對的——問題出在判準本身：它數的是字串出現次數，
   跟「樣式有沒有正確套用」根本無關。執行端沒有硬湊到 15，而是停下回報「數字對不上」。
2. **把「grep 到的次數」當成「還在使用」。** 一個 CSS class 可能同時有基礎規則和
   `@media` 覆寫兩條定義，總次數是 2，但 HTML 裡完全沒有任何元素在用它。
   照原判準會誤判成「還在使用、不能刪」，跟同一份規劃書「這些 class 要歸零」的目標互相矛盾。
3. **驗證腳本自己的依賴漏列。** 把渲染函式抽到獨立環境測試時，判準腳本漏列了兩個
   它依賴的 helper 函式，導致 `ReferenceError`——正式程式碼沒問題，破的是驗證腳本本身。

三次都是執行端正確停下、沒有自行補完；事後查證也證實判準確實寫錯，不是執行端偷懶。
**這是行為契約有效的證據，但也暴露了規劃階段的弱點永遠在「事實查證」，不在「設計判斷」**——
所以規劃書模板裡有專門的「交付前機械稽核」一步，要求規劃者在交付前重跑每一條要寫進判準的指令，
而不是憑印象或估計值下判準。

## 安裝

```bash
mkdir -p ~/.claude/skills/hfg ~/.claude/agents
cp skills/hfg/SKILL.md ~/.claude/skills/hfg/SKILL.md
cp agents/builder.md ~/.claude/agents/builder.md
```

## 驗證

本 repo 不需要 package manager 或第三方依賴。在 repo 根目錄執行：

```bash
python3 tests/run_tests.py
```

若目前不在 repo 根目錄，改用測試入口的絕對路徑：

```bash
python3 /path/to/hfg-claude/tests/run_tests.py
```

GitHub Actions 會在 Python 3.10、3.11、3.12 與 3.13 上執行相同測試，並檢查
`git diff --check`。本地開發規範與 PR checklist 見 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 使用方式

```
/hfg <你要交接出去的任務描述>
```

`hfg` 只做偵察與規劃，**不會動你的程式碼**。它會：

1. 讀相關檔案、確認函式名與現況、跑一次既有測試
2. 列出所有需要拍板的分岔點，屬於「使用者意圖／偏好」的用 `AskUserQuestion` 一次問完
3. 產出 `plans/HFG_<任務slug>_<日期>.md`
4. 交付前自我稽核（見 [`skills/hfg/SKILL.md`](skills/hfg/SKILL.md) 的「交付前的機械稽核」一節）
5. 若專案裝了 `builder` agent，直接用 Agent tool 派工；沒有的話印出一段開場句，
   讓你自己複製貼到另一個 session

規劃書長什麼樣子，見 [`examples/HFG_example-env-guards.md`](examples/HFG_example-env-guards.md)——
一份完整的範例（改了兩個函式讓它們能在 Node 環境安全執行、加測試），
展示十個區塊（0–8 加 7b）模板實際填出來的樣子。

## 已知限制

- **驗證樣本窄**：目前只在一個專案上實戰過，而且那個專案條件偏特殊
  （有完整自動化測試、有完整文件體系）。以下情境**還沒被驗證過**：
  - 沒有自動測試的專案——「驗收不准退化成『確認功能正常』」這條規則在這種專案上
    是否寫得出可執行的判準，還不確定
  - Git repo 專案——「不准 commit／開分支」這組禁令有沒有真的擋得住，未實測
  - 需要開瀏覽器才能驗收的前端專案——「執行端驗不了的部分歸使用者」這個切法
    在更複雜的 UI 上是否還適用，未實測
- **沒有「執行端沒停下、自己補完」的反例**。目前記錄到的中斷全部是執行端正確停下，
  這證明行為契約在測過的情境下有效，但無法說明它在什麼條件下會失效。
- **語言**：規劃書模板與說明文字目前全部是繁體中文。方法論本身語言中立，
  但要在英文環境用，模板需要自己翻譯。

歡迎回報你在其他專案上使用的結果——尤其是上面列的「還沒驗證過」的情境。

## 跟 obra/superpowers 的關係

**先講清楚，省得你自己發現時覺得被誤導**：[`obra/superpowers`](https://github.com/obra/superpowers)
（27 萬星以上，持續更新中）底下的 `writing-plans` / `executing-plans` 兩個 skill，
做的事跟 `hfg` / `builder` 高度相似——強模型寫規劃書、存成文件、派 subagent 逐項執行、
卡住就停不要瞎猜。**這是目前這個生態圈裡最成熟、採用度最高的同類方案**，整合了
TDD、git worktree、code review dispatch 等一整套方法論，比 `hfg` 完整得多。

`hfg` 不是要取代它。差異在於它假設的專案條件：`superpowers` 的流程預設你在用 git worktree、
走 TDD 紅綠燈、每個小步驟都 commit。`hfg` 是在一個**不是 git repo、沒有標準測試框架的
單檔案舊專案**上磨出來的，所以它明確處理「沒有 git 安全網怎麼辦」「專案沒有自動測試時
驗收判準要怎麼寫」這類 `superpowers` 的前提不成立時的情境，而且多了一步「交付前機械稽核」——
規劃書裡每個具體事實都要求規劃者重新真的跑一次指令查證，不能用印象或估計值。

如果你的專案是 git repo、有 TDD 習慣，**直接用 `superpowers` 大概率比較好**——它更成熟、
社群更大、涵蓋的情境更完整。`hfg` 適合的是它的前提不成立的那種舊專案。

## Acknowledgements

這套方法論是實戰歸納的產物。開發過程中沒有參考過 `obra/superpowers` 的原始碼
（上面那段比較是事後才做的），但社群裡流傳的概念確實有給過方向上的啟發，特此註明：
Matt Pocock 的 `/handoff`（解決 context 耗盡的交接文件）。

## License

MIT，見 [`LICENSE`](LICENSE)。

## 檔案清單

- [`skills/hfg/SKILL.md`](skills/hfg/SKILL.md)：hfg 規劃 skill
- [`agents/builder.md`](agents/builder.md)：builder subagent 行為契約
- [`examples/HFG_example-env-guards.md`](examples/HFG_example-env-guards.md)：完整規劃書範例
- [`tests/test_repo.py`](tests/test_repo.py)：repo 品質契約測試，並驗證 Markdown anchor、規劃書 section 與可執行驗收表一致性
- [`tests/run_tests.py`](tests/run_tests.py)：本地測試入口
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml)：GitHub Actions CI
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：貢獻與驗證規範
- [`CHANGELOG.md`](CHANGELOG.md)：變更紀錄
- [`.gitignore`](.gitignore)：本地產物與規劃檔忽略規則
