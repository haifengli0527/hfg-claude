#!/usr/bin/env python3
"""hfg 規劃書交付前機械預檢（4b 的 A0）。

讀 plans/HFG_*.md 第 6 節的每個 Edit／Write 步驟，把 old_string／new_string
依序「模擬套用」到記憶體裡的檔案副本上，逐步回報定位是否成立：

  OK         old_string 在「執行者做到這一步時的檔案狀態」裡剛好出現 1 次
  INDENT     只有把 fence 的縮排扣掉才找得到——執行者照原樣貼會失敗；把 fence 移到第 0 欄
  MISSING    0 次——並印出首行命中處與縮排差，這是 9 月最常見的規劃錯誤
  DUPLICATE  2 次以上——通常代表要改的地方不只一處，不是單純技術障礙
  SKIP       old_string 是描述級（沒有 fenced 內容），無法機械檢查——本身就違反逐字級要求

模式：
  python hfg_preflight.py PLAN.md                 交付前預檢（預設），任何非 OK 都 exit 1
  python hfg_preflight.py PLAN.md --out DIR       另把模擬套用後的檔案寫到 DIR，供 A2 dry-run 跑驗收指令
  python hfg_preflight.py PLAN.md --applied       續作模式：對「磁碟現況」判斷每步做了沒
                                                  （先看 new_string 在不在，再看 old_string——很多 new 包含 old）
  --root DIR   專案根目錄（規劃書裡的相對路徑以此為準；預設是目前目錄）
  --step N     只檢查某一步

縮排規則：fenced block 裡的每一行就是要貼進檔案的原文，**fence 本身放第 0 欄**。
fence 縮進 bullet 底下時，「照原樣」與「扣掉 fence 縮排」會得出兩個不同的 old_string，
執行者是照原樣貼的，所以只有原樣成立才算 OK。

只用標準函式庫。檔案一律以 UTF-8 讀寫，CRLF 會先正規化成 LF 再比對並警告。
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

STEP_RE = re.compile(r"^###\s*步驟\s*([0-9]+[A-Za-z]?)\s*[：:]?\s*(.*)$")
SECTION_RE = re.compile(r"^##\s")
TOOL_RE = re.compile(r"^\s*-\s*\*\*工具\*\*\s*[：:]\s*(Edit|Write|Bash|PowerShell|Read)?\s*(.*)$")
LABEL_RE = re.compile(
    r"^\s*-\s*\*\*(old_string|new_string|內容|完整內容|完整檔案內容|檔案路徑|路徑)\*\*(?:（[^）]*）)?\s*[：:]\s*(.*)$"
)
FENCE_OPEN_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*(\S*)\s*$")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
PATHLIKE_RE = re.compile(r"^[\w./\\-]+\.[A-Za-z0-9]+$")


@dataclass
class Block:
    raw: str  # fence 裡的每一行照原樣
    rel: str  # 扣掉 fence 自身縮排之後
    indent: int  # fence 的縮排格數


@dataclass
class EditPair:
    old: Block | None  # None = 描述級
    new: Block | None
    old_line: int  # 規劃書行號（1-based）


@dataclass
class Step:
    number: str
    title: str
    line: int
    tool: str | None = None
    path: str | None = None
    pairs: list[EditPair] = field(default_factory=list)
    write_content: Block | None = None


# ---------------------------------------------------------------- 解析

def read_text(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes().decode("utf-8")
    had_crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), had_crlf


def strip_indent(line: str, n: int) -> str:
    k = 0
    while k < n and k < len(line) and line[k] == " ":
        k += 1
    return line[k:]


def parse_fence(lines: list[str], start: int) -> tuple[Block, int] | None:
    """從 lines[start] 往下找第一個 fenced block，回 (Block, 結尾行 index)。找不到回 None。"""
    i = start
    while i < len(lines):
        line = lines[i]
        if LABEL_RE.match(line) or STEP_RE.match(line) or SECTION_RE.match(line):
            return None
        m = FENCE_OPEN_RE.match(line)
        if m:
            indent, fence = m.group(1), m.group(2)
            body: list[str] = []
            j = i + 1
            while j < len(lines):
                stripped = lines[j].strip()
                if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                    break
                body.append(lines[j])
                j += 1
            raw = "\n".join(body)
            rel = "\n".join(strip_indent(b, len(indent)) for b in body)
            return Block(raw=raw, rel=rel, indent=len(indent)), j
        if line.strip():
            return None
        i += 1
    return None


def inline_code(remainder: str) -> Block | None:
    m = re.fullmatch(r"`([^`]+)`", remainder.strip())
    return Block(raw=m.group(1), rel=m.group(1), indent=0) if m else None


def first_pathlike(text: str) -> str | None:
    for tok in BACKTICK_RE.findall(text):
        tok = tok.strip()
        if PATHLIKE_RE.match(tok):
            return tok
    return None


def parse_plan(text: str) -> list[Step]:
    lines = text.split("\n")
    steps: list[Step] = []
    i = 0
    while i < len(lines):
        m = STEP_RE.match(lines[i])
        if not m:
            i += 1
            continue
        step = Step(number=m.group(1), title=m.group(2).strip(), line=i + 1)
        j = i + 1
        pending: EditPair | None = None
        while j < len(lines) and not STEP_RE.match(lines[j]) and not SECTION_RE.match(lines[j]):
            line = lines[j]
            tm = TOOL_RE.match(line)
            if tm and step.tool is None:
                step.tool = tm.group(1) or "?"
                step.path = first_pathlike(tm.group(2)) or first_pathlike(step.title)
                j += 1
                continue
            lm = LABEL_RE.match(line)
            if lm:
                label, remainder = lm.group(1), lm.group(2)
                if label in ("檔案路徑", "路徑"):
                    step.path = step.path or first_pathlike(remainder)
                    j += 1
                    continue
                block = inline_code(remainder)
                end = j
                if block is None:
                    parsed = parse_fence(lines, j + 1)
                    if parsed:
                        block, end = parsed
                if label == "old_string":
                    pending = EditPair(old=block, new=None, old_line=j + 1)
                    step.pairs.append(pending)
                elif label == "new_string":
                    if pending is None or pending.new is not None:
                        pending = EditPair(old=None, new=None, old_line=j + 1)
                        step.pairs.append(pending)
                    pending.new = block
                elif step.write_content is None:
                    step.write_content = block
                j = end + 1
                continue
            j += 1
        if step.tool == "Write" and step.write_content is None:
            # 沒有標籤、直接接 fence 的 Write（實際規劃書有這種寫法）
            k = i + 1
            while k < j:
                if FENCE_OPEN_RE.match(lines[k]):
                    parsed = parse_fence(lines, k)
                    if parsed:
                        step.write_content = parsed[0]
                    break
                k += 1
        if step.tool == "Write" and step.path is None:
            step.path = first_pathlike("\n".join(lines[i:j]))
        steps.append(step)
        i = j
    return steps


# ---------------------------------------------------------------- 診斷

def leading_ws(s: str) -> str:
    return s[: len(s) - len(s.lstrip(" \t"))]


def describe_ws(ws: str) -> str:
    return f"{ws.count(' ')} 空格" + (f"+{ws.count(chr(9))} tab" if "\t" in ws else "")


def diagnose_missing(content: str, old: str) -> list[str]:
    """old_string 找不到時，說明最可能的原因。"""
    out: list[str] = []
    file_lines = content.split("\n")
    old_lines = old.split("\n")

    def norm(s: str) -> str:
        return "\n".join(l.strip() for l in s.split("\n"))

    if norm(old) in norm(content):
        out.append("整段內容（忽略每行前後空白後）存在於檔案 → 只有縮排或尾端空白不同")
    first = next((l for l in old_lines if l.strip()), "")
    if not first:
        return out or ["old_string 是空的"]
    hits = [n for n, l in enumerate(file_lines) if l.strip() == first.strip()]
    if not hits:
        out.append(f"首行內容在檔案中找不到：{first.strip()[:80]!r}")
        return out
    for n in hits[:3]:
        block = file_lines[n : n + len(old_lines)]
        for k, (exp, act) in enumerate(zip(old_lines, block)):
            if exp == act:
                continue
            if exp.strip() == act.strip():
                out.append(
                    f"檔案第 {n + 1 + k} 行：內容相同但縮排不同——規劃書 {describe_ws(leading_ws(exp))}，檔案 {describe_ws(leading_ws(act))}"
                )
            else:
                out.append(
                    f"檔案第 {n + 1 + k} 行起內容不同：規劃書 {exp.strip()[:60]!r} vs 檔案 {act.strip()[:60]!r}"
                )
            break
        else:
            if len(block) < len(old_lines):
                out.append(f"檔案第 {n + 1} 行命中首行，但檔案在段落結束前就結束了")
    return out


# ---------------------------------------------------------------- 主流程

class Sim:
    def __init__(self, root: Path):
        self.root = root
        self.files: dict[str, str] = {}
        self.crlf: set[str] = set()
        self.warnings: list[str] = []

    def load(self, rel: str) -> str | None:
        if rel in self.files:
            return self.files[rel]
        p = self.root / rel
        if not p.is_file():
            return None
        text, crlf = read_text(p)
        if crlf:
            self.crlf.add(rel)
            self.warnings.append(f"{rel}: 檔案含 CRLF，已正規化成 LF 比對（Edit 工具要求逐字一致，請確認專案的換行慣例）")
        self.files[rel] = text
        return text


def run_check(steps: list[Step], root: Path, only: str | None, out_dir: Path | None) -> int:
    sim = Sim(root)
    bad = 0
    for step in steps:
        if only and step.number != only:
            continue
        if step.tool not in ("Edit", "Write"):
            continue
        tag = f"步驟 {step.number:<4} {step.tool:<5} {step.path or '<路徑不明>'}"
        if step.path is None:
            print(f"{tag}  SKIP   找不到檔案路徑（工具行或標題裡沒有 `path` 樣式的字串）")
            bad += 1
            continue
        if step.tool == "Write":
            if step.write_content is None:
                print(f"{tag}  SKIP   Write 沒有 fenced 內容——等於把設計丟回給執行者")
                bad += 1
                continue
            existed = (root / step.path).exists()
            body = step.write_content.rel
            sim.files[step.path] = body
            note = "⚠ 會覆蓋既有檔案（4b 的 C 不可逆稽核）" if existed else "新檔"
            extra = f"；fence 縮了 {step.write_content.indent} 格，已扣掉" if step.write_content.indent else ""
            print(f"{tag}  OK     {note}，{body.count(chr(10)) + 1} 行{extra}")
            continue
        content = sim.load(step.path)
        if content is None:
            print(f"{tag}  MISSING 檔案不存在：{root / step.path}")
            bad += 1
            continue
        if not step.pairs:
            print(f"{tag}  SKIP   沒有 old_string／new_string")
            bad += 1
            continue
        for idx, pair in enumerate(step.pairs, 1):
            sub = tag + (f" #{idx}" if len(step.pairs) > 1 else "")
            if pair.old is None:
                print(f"{sub}  SKIP   old_string 是描述級（規劃書第 {pair.old_line} 行）——逐字級才能機械檢查")
                bad += 1
                continue
            if pair.new is None:
                print(f"{sub}  SKIP   有 old_string 但沒有 new_string（規劃書第 {pair.old_line} 行）")
                bad += 1
                continue
            n = content.count(pair.old.raw)
            if n == 1:
                content = content.replace(pair.old.raw, pair.new.raw, 1)
                sim.files[step.path] = content
                warn = ""
                if pair.old.indent and pair.old.raw != pair.old.rel:
                    warn = f"   ⚠ fence 縮了 {pair.old.indent} 格，內容以原樣成立；把 fence 移到第 0 欄可消除歧義"
                print(f"{sub}  OK{warn}")
            elif n == 0:
                bad += 1
                if pair.old.rel != pair.old.raw and content.count(pair.old.rel) == 1:
                    print(
                        f"{sub}  INDENT（規劃書第 {pair.old_line} 行）——只有扣掉 fence 的 {pair.old.indent} 格縮排才找得到；"
                        f"執行者照原樣貼會失敗。把 fence 移到第 0 欄、內容用檔案裡的絕對縮排"
                    )
                    content = content.replace(pair.old.rel, pair.new.rel, 1)  # 讓後續步驟還能繼續檢查
                    sim.files[step.path] = content
                    continue
                print(f"{sub}  MISSING（規劃書第 {pair.old_line} 行）")
                for reason in diagnose_missing(content, pair.old.raw):
                    print(f"           ↳ {reason}")
            else:
                bad += 1
                print(f"{sub}  DUPLICATE 出現 {n} 次（規劃書第 {pair.old_line} 行）——加上下文，或確認是不是要改的地方不只一處")
    for w in sim.warnings:
        print(f"⚠ {w}")
    if out_dir is not None:
        for rel, text in sim.files.items():
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if rel in sim.crlf:
                text = text.replace("\n", "\r\n")
            dst.write_bytes(text.encode("utf-8"))
        print(f"模擬套用後的 {len(sim.files)} 個檔案已寫到 {out_dir}（供 A2 dry-run 跑驗收指令）")
    print(f"\n{'全部 OK，可以交付' if bad == 0 else f'{bad} 項不是 OK——交付前必須歸零'}")
    return 0 if bad == 0 else 1


def run_applied(steps: list[Step], root: Path, only: str | None) -> int:
    for step in steps:
        if only and step.number != only:
            continue
        if step.tool not in ("Edit", "Write") or step.path is None:
            continue
        tag = f"步驟 {step.number:<4} {step.tool:<5} {step.path}"
        p = root / step.path
        if step.tool == "Write":
            print(f"{tag}  {'APPLIED 檔案存在' if p.is_file() else 'PENDING 檔案不存在'}")
            continue
        if not p.is_file():
            print(f"{tag}  ?      檔案不存在")
            continue
        content, _ = read_text(p)
        for idx, pair in enumerate(step.pairs, 1):
            sub = tag + (f" #{idx}" if len(step.pairs) > 1 else "")
            if pair.old is None or pair.new is None:
                print(f"{sub}  ?      描述級，無法判斷")
                continue
            has_new = pair.new.raw in content or pair.new.rel in content
            has_old = pair.old.raw in content or pair.old.rel in content
            if has_new:
                print(f"{sub}  APPLIED（new_string 已存在{'；old_string 也在，因為 new 包含 old' if has_old else ''}）")
            elif has_old:
                print(f"{sub}  PENDING（old_string 還在、new_string 不在）")
            else:
                print(f"{sub}  ?      old／new 都不在——檔案可能已被後面的步驟改過，或規劃書寫錯")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--root", default=".")
    ap.add_argument("--applied", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--step")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    plan_path = Path(args.plan)
    text, _ = read_text(plan_path)
    steps = parse_plan(text)
    edit_like = [s for s in steps if s.tool in ("Edit", "Write")]
    print(f"規劃書 {plan_path.name}：{len(steps)} 個步驟，其中 {len(edit_like)} 個 Edit／Write；專案根目錄 {Path(args.root).resolve()}\n")
    if not edit_like:
        print("沒有任何 Edit／Write 步驟——確認第 6 節的寫法是 `- **工具**：Edit `path``")
        return 1
    if args.applied:
        return run_applied(steps, Path(args.root), args.step)
    return run_check(steps, Path(args.root), args.step, Path(args.out) if args.out else None)


if __name__ == "__main__":
    sys.exit(main())
