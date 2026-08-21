"""SPEC 8 的不变量表必须自洽：它声称的守卫测试文件都得真实存在。

这一节的全部价值在于「每条不变量都能指向一个会变红的测试」。如果表里写了
一个不存在的测试文件名，这一节就退化成上一版那种抽象原则——而上一版恰恰
是在写下之后仍被违反了两次。所以这个自洽性本身也需要被守。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "SPEC.md"
TESTS = ROOT / "tests"

_SECTION_RE = re.compile(r"^## 8\. 设计不变量$.*?^## 9\.", re.M | re.S)
_TEST_FILE_RE = re.compile(r"`(test_[a-z0-9_]+\.py)`")


def _invariants_section() -> str:
    match = _SECTION_RE.search(SPEC.read_text(encoding="utf-8"))
    assert match, "SPEC 第 8 节缺失或标题被改动"
    return match.group(0)


def test_every_referenced_guard_test_exists() -> None:
    section = _invariants_section()
    referenced = sorted(set(_TEST_FILE_RE.findall(section)))
    assert referenced, "第 8 节没有引用任何守卫测试——不变量退化为无落点的原则"

    missing = [name for name in referenced if not (TESTS / name).is_file()]
    assert not missing, f"SPEC 8 引用了不存在的守卫测试：{missing}"


def test_every_invariant_row_names_a_guard() -> None:
    """表格中的每一行不变量都必须给出守卫测试，不允许留空。"""
    section = _invariants_section()
    rows = [
        line
        for line in section.splitlines()
        if line.startswith("| ") and re.match(r"^\|\s*\d+\s*\|", line)
    ]
    assert rows, "未解析到不变量表格行"

    unguarded = []
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        number, guard = cells[0], cells[3]
        if not _TEST_FILE_RE.search(guard):
            unguarded.append(number)
    assert not unguarded, f"以下不变量没有守卫测试：{unguarded}"
