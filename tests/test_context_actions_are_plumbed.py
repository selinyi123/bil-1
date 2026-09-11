"""登记为 `context` 的 action，必须有一条证明它把上下文传到了客户端的测试。

`JOB_IDENTITY_POLICY` 声明身份策略，`run_action` 实现它，两者之间没有编译期联系。
`check_prize` 就是这样漏的：策略表写着 `context`，分支里却是裸 `BilibiliClient()`，
于是轮转时它按**当前活跃 cookie** 去读并标记别人的私信（2026-09-10 修复）。

单独给每个 action 写测试挡不住下一个——漏写测试的人正是漏写接线的人。
所以这里守的是**表与测试的对应关系**：往策略表里加一个 `context` action，
在补上对应的接线测试之前，这条会红。

它不替代那些测试，它只保证那些测试存在。
"""

from __future__ import annotations

import ast
from pathlib import Path

from web.job_runner import IDENTITY_CONTEXT, JOB_IDENTITY_POLICY

TESTS = Path(__file__).resolve().parent

# action → 证明「该 action 的客户端拿到了 account_context」的测试
PLUMBING_TESTS: dict[str, tuple[str, str]] = {
    "check_prize": ("test_account_rotation.py", "test_check_prize_uses_the_bound_context_client"),
    "participate": ("test_account_rotation.py", "test_participate_uses_bound_context_client"),
    "participate_triple": (
        "test_participate_triple.py",
        "test_run_action_participate_triple_concurrent",
    ),
}


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def test_every_context_action_names_a_plumbing_test() -> None:
    declared = {
        action
        for action, policy in JOB_IDENTITY_POLICY.items()
        if policy == IDENTITY_CONTEXT
    }
    missing = sorted(declared - set(PLUMBING_TESTS))
    assert not missing, (
        f"这些 action 声明了冻结身份，却没有登记接线测试：{missing}。"
        "补一条断言其客户端拿到 account_context 的测试，再把它填进 PLUMBING_TESTS。"
    )

    stale = sorted(set(PLUMBING_TESTS) - declared)
    assert not stale, f"PLUMBING_TESTS 里的 action 已不再是 context 策略：{stale}"


def test_registered_plumbing_tests_exist() -> None:
    """登记的测试必须真实存在——指向不存在的名字等于没有守卫。"""
    missing = [
        f"{file}::{name}"
        for file, name in PLUMBING_TESTS.values()
        if not (TESTS / file).is_file() or name not in _function_names(TESTS / file)
    ]
    assert not missing, f"PLUMBING_TESTS 指向了不存在的测试：{missing}"
