# 施工規劃書：兩支函式加上執行環境防護（讓 parser 邏輯能被單元測試涵蓋）

> 這份文件是你這次任務的**唯一指令來源**。不要另外推測需求，不要做這裡沒寫的事。
> 遇到與本文件描述不符的現況 → 直接跳到最後一節「卡住時怎麼辦」。
>
> **這份很小**：兩個函式各改一行，加測試。估 15–25 分鐘。

---

## 0. 前置條件

- [ ] `app.html` 的 `BUILD` 標記是 `BUILD 0810B`
- [ ] `node tests/run_tests.js` → **142 通過 / 0 失敗**
- [ ] 檔案是 LF
- [ ] 找得到 `function genRecordId` 與 `function loadUserAliasMap`

---

## 1. 目標與驗收標準

**為什麼要做這個**：`genRecordId` 讀 `window.crypto`、`loadUserAliasMap` 讀 `localStorage`。
這兩個是瀏覽器內建全域，在 Node 裡不存在。它們被匯入流程的 CSV parser 間接依賴，
導致 parser 邏輯沒辦法被單元測試直接呼叫（偵察時用 `grep -n "window\.\|localStorage" app.html`
確認全專案只有這兩處）。

**解法**：不改行為、不改簽名，各加一行執行環境防護。
瀏覽器裡逐字等價，Node 裡自然降級。

**怎麼確認做對了**：

| 檢查 | 指令 | 預期輸出 |
|---|---|---|
| 測試 | `node tests/run_tests.js` | 0 失敗，項數 ≥ 144 |
| 瀏覽器行為不變 | 步驟 5 | `genRecordId()` 仍回 UUID 格式字串 |
| Node 可執行 | 步驟 4 | 不再需要 `sandbox.window` 也能跑 parser 相關測試 |
| 版本碼 | 搜尋 `BUILD 0810` | 已變成 `BUILD 0810C` |
| 回歸 | 人工確認 | 只有 `app.html` 與 `tests/run_tests.js` 有變動 |

---

## 2. 範圍邊界：明確不要做的事

- **不要改這兩支函式的簽名。** 不加參數、不改回傳型別。呼叫端一個都不要動。
- **不要改任何 parser。**
- 不要用 Python 改 `app.html`（會把 LF 轉成 CRLF，炸掉既有的擷取正則）。
- 不要新增 npm 套件。
- **不要在回報裡提醒使用者部署或同步**——那是使用者自己的事，這份規劃書不涵蓋。

---

## 3. 相關檔案清單

| 檔案 | 讀/改 | 相關位置 | 為什麼相關 |
|---|---|---|---|
| `app.html` | 改（兩處） | `genRecordId`／`loadUserAliasMap` | 本次要加防護的函式本體 |
| `tests/run_tests.js` | 改 | 檔尾測試區塊 | 移除多餘 stub、加兩項新測試 |

**不在這張表上的檔案都不要開、不要改。**

---

## 4. 本次相關的已知陷阱

- **`globalThis.crypto.randomUUID` 只在 secure context（https 或 localhost）可用。**
  使用者常用 `file://` 直接開這個 HTML——`file://` 下 `crypto.randomUUID` 可能是
  `undefined`。所以**一定要保留原本的 fallback 分支**，不可以簡化成只回 `randomUUID()`。
  改動只是把 `window.` 換成 `globalThis.`，讓 Node 也走得通，**不是**改用 UUID。
- **`typeof localStorage === "undefined"` 要用 `typeof`**，不可以寫成
  `if (!localStorage)`——後者在 Node 裡會直接 `ReferenceError`，防護等於沒加。
- **不要用 Python 改檔**（CRLF 會讓既有的區塊擷取正則失效，因為 `.` 不匹配 `\r`）。
- **BUILD 日期碼每次改動都要更新。**

---

## 5. 已做掉的決策（不要重新評估）

| 分岔點 | 決定 | 理由 |
|---|---|---|
| 改行為還是加防護 | **加防護** | 瀏覽器裡必須逐字等價。這兩支函式的行為是使用者每天在用的 |
| 改簽名（把 aliasMap 當參數傳入）還是加 typeof 防護 | **加防護** | 改簽名要動呼叫端、要重測匯入流程，風險遠大於一行 typeof |
| `window` → `globalThis` | 是 | 兩者在瀏覽器裡指向同一個東西；Node 也有 `globalThis` |
| `loadUserAliasMap` 在 Node 裡回什麼 | **回 `{}`** | 讓呼叫端落到內建的預設對照表，這正是套件化後要的行為 |

現場狀況與某條決策矛盾時 → 停下回報，不要自行改採另一案。

---

## 6. 逐步操作

### 步驟 1：`genRecordId` 改用 `globalThis`

- **工具**：Edit `app.html`
- **old_string**：
  ```
        function genRecordId() {
          return window.crypto && crypto.randomUUID
            ? crypto.randomUUID()
            : "rec-" + Date.now() + "-" + Math.random().toString(16).slice(2);
        }
  ```
- **new_string**：
  ```
        // `window.crypto` 改成 `globalThis.crypto`。兩者在瀏覽器裡是同一個東西，
        // 但 Node 沒有 `window`——這支函式被多個 parser 共用，不改的話 parser
        // 沒辦法在瀏覽器以外的環境跑（單元測試要塞 window stub、也抽不進獨立套件）。
        // ⚠ fallback 分支不可以拿掉：`crypto.randomUUID` 只在 secure context 可用，
        // 而這個檔案常常是用 file:// 直接開的，那時 randomUUID 是 undefined。
        function genRecordId() {
          return globalThis.crypto && globalThis.crypto.randomUUID
            ? globalThis.crypto.randomUUID()
            : "rec-" + Date.now() + "-" + Math.random().toString(16).slice(2);
        }
  ```
- **預期結果**：Edit 成功，檔案裡不再出現 `window.crypto &&` 這個樣式
- **依賴**：無

---

### 步驟 2：`loadUserAliasMap` 加 typeof 防護

- **工具**：Edit `app.html`
- **old_string**：
  ```
        function loadUserAliasMap() {
          return safeParseJSON(localStorage.getItem(ALIAS_MAP_KEY), {});
        }
  ```
- **new_string**：
  ```
        // 加執行環境防護。這支會被匯入流程的多個 parser 間接呼叫，
        // 所以整條「CSV 匯入 → 別名對照」的解析鏈都綁著 localStorage。
        // Node 裡沒有這個全域，不防護就 ReferenceError。
        // ⚠ 一定要用 `typeof`：寫成 `if (!localStorage)` 在 Node 裡會直接
        // ReferenceError，防護等於沒加。
        // 在 Node 回 {} 的語意＝「沒有使用者手動校正過的對照」，
        // 呼叫端會落到內建的預設對照表，這是正確的降級。
        function loadUserAliasMap() {
          if (typeof localStorage === "undefined") return {};
          return safeParseJSON(localStorage.getItem(ALIAS_MAP_KEY), {});
        }
  ```
- **預期結果**：Edit 成功
- **依賴**：無

---

### 步驟 3：移除 `tests/run_tests.js` 裡不再需要的 `window` stub

- **工具**：Edit `tests/run_tests.js`
- 找到 `sandbox.window = {};` 這一行，**刪掉它**，並把上方那段註解裡提到 `window` 的
  句子改成說明「`genRecordId` 已改用 `globalThis`，不再需要 window stub；
  `localStorage` stub 仍保留，用來測試使用者校正層存在時的路徑」。
- **`localStorage` stub 保留不動**——步驟 4 要用它測兩條路徑。
- **預期結果**：Edit 成功
- **依賴**：無

---

### 步驟 4：新增測試

- **工具**：Edit `tests/run_tests.js`，加在最後那組測試之後、印出總結那行之前。

至少兩項：

| 測項 | 期望 |
|---|---|
| `genRecordId()` 在沒有 `window` 的 sandbox 裡不拋錯 | 回傳非空字串 |
| `loadUserAliasMap()` 在 `localStorage` 沒值時落到內建預設表 | 清掉 stub 後回傳 `{}` |

- **指令**：`node tests/run_tests.js`
- **預期結果**：0 失敗，項數 ≥ 144
- **依賴**：必須先完成步驟 3（stub 移除後才能測到「沒有 window」這條路徑）

---

### 步驟 5：瀏覽器驗證

開 `app.html`，Console 執行：

```javascript
(() => {
  const ids = [genRecordId(), genRecordId(), genRecordId()];
  return {
    build: document.body.innerText.match(/BUILD \w+/)[0],
    ids,
    allStrings: ids.every(i => typeof i === 'string' && i.length > 0),
    allUnique: new Set(ids).size === 3,
  };
})()
```

- **預期結果**：`allStrings === true`、`allUnique === true`、`build === "BUILD 0810C"`
- **不符怎麼辦**：停下回報，不要繼續下一步

---

### 步驟 6：更新 BUILD

- **工具**：Edit `app.html`
- **old_string**：`BUILD 0810B`
- **new_string**：`BUILD 0810C`
- **預期結果**：Edit 成功
- **依賴**：必須是最後一步（前面任何步驟若導致本次改動需要重來，BUILD 碼不該提早改）

---

## 7. 完成後自我檢查清單

- [ ] `node tests/run_tests.js` → 0 失敗，項數 ≥ 144
- [ ] 步驟 5 的瀏覽器驗證三個預期值全部符合（貼出實際輸出）
- [ ] `grep -c "window.crypto &&" app.html` → **0**（掃程式碼樣式，不是掃字串——註解裡提到
      `window.crypto` 是正常的，只要不再有這個判斷式的樣式）
- [ ] `genRecordId` 的 fallback 分支**還在**（沒有被簡化掉）
- [ ] `loadUserAliasMap` 用的是 `typeof localStorage === "undefined"`
- [ ] 兩支函式的**簽名沒變**、呼叫端一個都沒動
- [ ] 檔案仍是 LF；BUILD 已改為 `BUILD 0810C`
- [ ] 只改了 `app.html` 與 `tests/run_tests.js`
- [ ] 回報裡沒有提醒使用者部署或同步
- [ ] 有任何一步偏離規劃書 → 在回報裡明寫哪一步、為什麼

## 7b. 完工後要更新的文件（由派工者做，不是執行者）

- 本次改動若牽涉專案的開發日誌／CHANGELOG，補一筆
- 若本次踩到規劃書沒預期到的坑，回頭把陷阱補進本次任務相關的 skill 或 CLAUDE.md

## 8. 卡住時怎麼辦（行為契約）

出現以下任一情況，**立刻停下**，輸出「卡在第 N 步 ／ 預期 X ／ 實際 Y ／ 已完成到第 M 步」，然後等指示：

- 某步的預期結果沒出現
- `old_string` 找不到或不唯一
- 需要改清單外的檔案
- 測試出現任何失敗
- 步驟 5 在瀏覽器裡 `genRecordId()` 拋錯
- 覺得規劃書某處是錯的

**明確禁止**：嘗試規劃書沒寫的替代方案、擴大搜索或改動範圍、為了讓驗收通過而改測試或改判準、
跳過失敗的步驟往下做、改函式簽名、拿掉 `genRecordId` 的 fallback 分支。
**回報一個做到一半但誠實的狀態，遠勝於一個自己補完的版本。**
