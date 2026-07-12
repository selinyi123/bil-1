from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable

from src.bilibili_client import BilibiliClient
from src.bilibili_login import login_with_qrcode
from src.classify_links import classify_merged_links, save_classified
from src.fetch_activity_info import fetch_activity_info, save_enriched
from src.lottery_actions import ACTION_LABELS, DEFAULT_PARTICIPATE_TEXT
from src.merge_links import merge_activity_links, save_merged
from src.participation import participate_activity
from src.sources import ds1_xiaozhuli, ds2_fanqiao, ds3_gongjuren, ds4_junming, ds5_hudong

from web.activity_service import lookup_lottery_type

DS_HANDLERS: list[tuple[str, Callable[..., Any], Callable[[Any], Any]]] = [
    ("DS-1", ds1_xiaozhuli.check_update, ds1_xiaozhuli.save_result),
    ("DS-2", ds2_fanqiao.check_update, ds2_fanqiao.save_result),
    ("DS-3", ds3_gongjuren.check_update, ds3_gongjuren.save_result),
    ("DS-4", ds4_junming.check_update, ds4_junming.save_result),
    ("DS-5", ds5_hudong.check_update, ds5_hudong.save_result),
]

REFRESH_ALL_TOTAL = len(DS_HANDLERS) + 3
ProgressCallback = Callable[..., None]


def _noop_progress(**_kwargs: Any) -> None:
    return None


def _format_participation_log(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for item in payload.get("actions") or []:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "")
        label = ACTION_LABELS.get(action, action)
        mark = "✓" if item.get("ok") else "✗"
        detail = str(item.get("detail") or "").strip()
        lines.append(f"{mark} {label}{f' · {detail}' if detail else ''}")
    message = str(payload.get("message") or "").strip()
    if message:
        lines.append(message)
    return "\n".join(lines).strip()


def _capture_output(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


def run_action(
    action: str,
    params: dict[str, Any] | None = None,
    *,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    params = params or {}
    progress = on_progress or _noop_progress
    log_lines: list[str] = []

    if action == "login":
        progress(step=1, total=1, message="等待扫码登录…")
        _, log = _capture_output(login_with_qrcode)
        return {
            "ok": True,
            "message": "登录成功，Cookie 已保存到 config/cookies.txt",
            "log": log,
        }

    if action == "refresh_all":
        ds_results: list[dict[str, Any]] = []
        sources_updated = 0

        for index, (source_id, check_update, save_result) in enumerate(DS_HANDLERS, start=1):
            progress(
                step=index,
                total=REFRESH_ALL_TOTAL,
                message=f"正在检查 {source_id} 是否有新专栏（{index}/{REFRESH_ALL_TOTAL}）…",
            )
            result, detail = _capture_output(check_update, force=False)
            out_path = save_result(result)
            if result.updated:
                sources_updated += 1
            ds_results.append(
                {
                    "source_id": source_id,
                    "updated": result.updated,
                    "link_count": len(result.activity_links),
                    "saved": bool(out_path),
                }
            )
            status_text = "发现新专栏" if result.updated else "无新专栏，使用缓存"
            log_line = (
                f"=== {source_id} 检查 ===\n"
                f"{status_text}，链接 {len(result.activity_links)} 条，"
                f"{'已写入' if out_path else '保留缓存'}"
            )
            log_lines.append(log_line)
            if detail.strip():
                log_lines.append(detail.strip())
            progress(
                step=index,
                total=REFRESH_ALL_TOTAL,
                message=f"{source_id}：{status_text}",
                log_append=log_line,
            )

        merge_step = len(DS_HANDLERS) + 1
        progress(step=merge_step, total=REFRESH_ALL_TOTAL, message="正在合并并去重链接…")
        merge_result, merge_log = _capture_output(merge_activity_links)
        merge_path = save_merged(merge_result)
        merge_line = (
            f"=== 合并去重 ===\n"
            f"合计 {merge_result.total_count} 条，新增 {merge_result.new_count} 条，"
            f"重复 {merge_result.duplicate_count} 条 → {merge_path}"
        )
        log_lines.append(merge_line)
        if merge_log.strip():
            log_lines.append(merge_log.strip())
        progress(
            step=merge_step,
            total=REFRESH_ALL_TOTAL,
            message=f"合并完成，新增 {merge_result.new_count} 条链接",
            log_append=merge_line,
        )

        classify_step = len(DS_HANDLERS) + 2
        if merge_result.new_count > 0:
            classify_message = f"正在分类 {merge_result.new_count} 条新链接…"
        else:
            classify_message = "无新链接，跳过分类（仅保留已有结果）…"
        progress(step=classify_step, total=REFRESH_ALL_TOTAL, message=classify_message)
        classify_result, classify_log = _capture_output(
            classify_merged_links,
            use_cache=True,
            force=False,
        )
        classify_path = save_classified(classify_result)
        classify_line = (
            f"=== 活动分类 ===\n"
            f"共 {classify_result.total_count} 条，本次新分类 {classify_result.new_count} 条 → {classify_path}"
        )
        log_lines.append(classify_line)
        if classify_log.strip():
            log_lines.append(classify_log.strip())
        progress(
            step=classify_step,
            total=REFRESH_ALL_TOTAL,
            message=f"分类完成，本次新增 {classify_result.new_count} 条",
            log_append=classify_line,
        )

        enrich_step = len(DS_HANDLERS) + 3
        if classify_result.new_count > 0:
            enrich_message = f"正在拉取 {classify_result.new_count} 条新活动详情…"
        else:
            enrich_message = "无新活动，跳过详情拉取…"
        progress(step=enrich_step, total=REFRESH_ALL_TOTAL, message=enrich_message)
        enrich_result, enrich_log = _capture_output(
            fetch_activity_info,
            use_cache=True,
            force=False,
        )
        if enrich_log.strip():
            log_lines.append(enrich_log.strip())

        save_step = REFRESH_ALL_TOTAL
        progress(step=save_step, total=REFRESH_ALL_TOTAL, message="正在保存活动数据…")
        enrich_path = save_enriched(enrich_result)
        enrich_line = (
            f"=== 保存活动数据 ===\n"
            f"共 {enrich_result.total_count} 条活动（含历史记录） → {enrich_path}"
        )
        log_lines.append(enrich_line)

        summary_parts = [
            f"检查 {len(DS_HANDLERS)} 个数据源，{sources_updated} 个有新专栏",
            f"新增链接 {merge_result.new_count} 条",
            f"新分类 {classify_result.new_count} 条",
            f"新拉取详情 {enrich_result.new_count} 条",
            f"当前共 {enrich_result.total_count} 条活动记录",
        ]

        return {
            "ok": True,
            "message": "一键更新完成：" + "，".join(summary_parts),
            "result": {
                "sources": ds_results,
                "sources_updated": sources_updated,
                "merged_total": merge_result.total_count,
                "merged_new": merge_result.new_count,
                "classified_new": classify_result.new_count,
                "enriched_new": enrich_result.new_count,
                "active_total": enrich_result.counts.get("active", 0),
                "total_count": enrich_result.total_count,
            },
            "log": "\n".join(log_lines).strip(),
        }

    if action == "participate":
        dynamic_id = str(params.get("dynamic_id") or "").strip()
        if not dynamic_id:
            raise ValueError("缺少 dynamic_id")
        lottery_type = lookup_lottery_type(dynamic_id)
        total_steps = 1 if lottery_type == "预约抽奖" else 5
        progress(step=0, total=total_steps, message="准备参与活动…")

        def on_step(step: int, total: int, message: str, _action_name: str) -> None:
            progress(step=step, total=total, message=message, log_append=message)

        def _participate() -> dict:
            with BilibiliClient() as client:
                result = participate_activity(
                    client,
                    dynamic_id=dynamic_id,
                    lottery_type=lottery_type,
                    action_text=DEFAULT_PARTICIPATE_TEXT,
                    dry_run=False,
                    persist=True,
                    on_step=on_step,
                )
                return result.to_dict()

        payload, _ = _capture_output(_participate)
        ok = payload.get("status") == "joined"
        action_log = _format_participation_log(payload)
        return {
            "ok": ok,
            "message": payload.get("message") or ("参与成功" if ok else "参与失败"),
            "result": payload,
            "log": action_log,
        }

    raise ValueError(f"未知操作: {action}")
