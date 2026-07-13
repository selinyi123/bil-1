from __future__ import annotations

import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable

from src.bilibili_client import BilibiliClient
from src.bilibili_login import login_with_qrcode
from src.classify_links import classify_merged_links, save_classified
from src.fetch_activity_info import (
    backfill_repost_counts,
    count_pending_enrich,
    count_pending_heat_backfill,
    fetch_activity_info,
    load_cached_enrich_result,
    save_enriched,
)
from src.app_logging import get_logger
from src.user_settings import get_participate_text
from src.merge_links import merge_activity_links, save_merged
from src.participation import participate_activity
from src.status_refresh import refresh_activity_statuses
from src.sources import (
    ds1_xiaozhuli,
    ds2_fanqiao,
    ds3_gongjuren,
    ds4_junming,
    ds5_hudong,
    ds6_nuomi,
)

from src.sources.common import is_valid_dynamic_id
from web.activity_service import invalidate_activity_cache, lookup_lottery_type
from web.user_messages import format_participation_log, sanitize_log

logger = get_logger("job")

HEAT_BACKFILL_WORKERS = 6


def _append_log_detail(log_lines: list[str], detail: str) -> None:
    cleaned = sanitize_log(detail.strip())
    if cleaned:
        log_lines.append(cleaned)

DS_HANDLERS: list[tuple[str, Callable[..., Any], Callable[[Any], Any]]] = [
    ("DS-1", ds1_xiaozhuli.check_update, ds1_xiaozhuli.save_result),
    ("DS-2", ds2_fanqiao.check_update, ds2_fanqiao.save_result),
    ("DS-3", ds3_gongjuren.check_update, ds3_gongjuren.save_result),
    ("DS-4", ds4_junming.check_update, ds4_junming.save_result),
    ("DS-5", ds5_hudong.check_update, ds5_hudong.save_result),
    ("DS-6", ds6_nuomi.check_update, ds6_nuomi.save_result),
]

REFRESH_ALL_TOTAL = len(DS_HANDLERS) + 5
ProgressCallback = Callable[..., None]


def _noop_progress(**_kwargs: Any) -> None:
    return None


def _capture_output(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


def _run_ds_check(
    index: int,
    source_id: str,
    check_update: Callable[..., Any],
    save_result: Callable[[Any], Any],
) -> tuple[int, dict[str, Any], str]:
    result, detail = _capture_output(check_update, force=False)
    out_path = save_result(result)
    status_text = "发现新专栏" if result.updated else "无新专栏，使用缓存"
    log_line = (
        f"=== {source_id} 检查 ===\n"
        f"{status_text}，链接 {len(result.activity_links)} 条，"
        f"{'已写入' if out_path else '保留缓存'}"
    )
    payload = {
        "source_id": source_id,
        "updated": result.updated,
        "link_count": len(result.activity_links),
        "saved": bool(out_path),
        "log_line": log_line,
        "detail": detail.strip(),
        "status_text": status_text,
    }
    return index, payload, log_line


def run_action(
    action: str,
    params: dict[str, Any] | None = None,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    params = params or {}
    progress = on_progress or _noop_progress
    log_lines: list[str] = []

    if action == "login":
        qrcode_refresh_count = 0

        def on_qrcode_ready() -> None:
            nonlocal qrcode_refresh_count
            qrcode_refresh_count += 1
            if qrcode_refresh_count == 1:
                progress(step=1, total=1, message="请使用哔哩哔哩 App 扫码登录", log_append="已生成登录二维码")
            else:
                progress(
                    step=1,
                    total=1,
                    message="二维码已刷新，请重新扫码",
                    log_append="二维码已自动刷新",
                    qrcode_refreshed_at=int(time.time()),
                )

        progress(step=1, total=1, message="正在生成登录二维码…")
        _, log = _capture_output(
            login_with_qrcode,
            open_image=False,
            auto_refresh_on_expire=True,
            cancel_event=cancel_event,
            on_qrcode_ready=on_qrcode_ready,
        )
        return {
            "ok": True,
            "message": "登录成功，账号已就绪",
            "log": sanitize_log(log) or "登录成功",
        }

    if action == "refresh_all":
        ds_results: list[dict[str, Any]] = []
        sources_updated = 0
        progress(
            step=0,
            total=REFRESH_ALL_TOTAL,
            message=f"正在并行检查 {len(DS_HANDLERS)} 个数据源…",
        )

        ds_payloads: list[tuple[int, dict[str, Any], str]] = []
        with ThreadPoolExecutor(max_workers=len(DS_HANDLERS)) as executor:
            futures = {
                executor.submit(_run_ds_check, index, source_id, check_update, save_result): source_id
                for index, (source_id, check_update, save_result) in enumerate(DS_HANDLERS, start=1)
            }
            for future in as_completed(futures):
                source_id = futures[future]
                try:
                    ds_payloads.append(future.result())
                except Exception as exc:
                    log_lines.append(f"=== {source_id} 检查失败 ===\n{exc}")
                    progress(
                        step=len(ds_payloads),
                        total=REFRESH_ALL_TOTAL,
                        message=f"{source_id} 检查失败，已跳过",
                        log_append=f"{source_id} 检查失败：{exc}",
                    )

        ds_payloads.sort(key=lambda item: item[0])
        for index, payload, log_line in ds_payloads:
            if payload.get("updated"):
                sources_updated += 1
            ds_results.append(
                {
                    "source_id": payload["source_id"],
                    "updated": payload["updated"],
                    "link_count": payload["link_count"],
                    "saved": payload["saved"],
                }
            )
            log_lines.append(log_line)
            if payload.get("detail"):
                _append_log_detail(log_lines, payload["detail"])
            progress(
                step=index,
                total=REFRESH_ALL_TOTAL,
                message=f"{payload['source_id']}：{payload['status_text']}",
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
            _append_log_detail(log_lines, merge_log)
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
            _append_log_detail(log_lines, classify_log)
        progress(
            step=classify_step,
            total=REFRESH_ALL_TOTAL,
            message=f"分类完成，本次新增 {classify_result.new_count} 条",
            log_append=classify_line,
        )

        enrich_step = len(DS_HANDLERS) + 3
        pending_enrich = count_pending_enrich()
        if classify_result.new_count > 0 or pending_enrich > 0:
            enrich_message = f"正在拉取 {pending_enrich} 条新活动详情…" if pending_enrich > 0 else "正在拉取新活动详情…"
            progress(step=enrich_step, total=REFRESH_ALL_TOTAL, message=enrich_message)

            def on_enrich_progress(done: int, total: int, phase: str) -> None:
                if total > 0:
                    message = f"{phase} ({done}/{total})"
                else:
                    message = phase
                progress(step=enrich_step, total=REFRESH_ALL_TOTAL, message=message)

            enrich_result, enrich_log = _capture_output(
                fetch_activity_info,
                use_cache=True,
                force=False,
                backfill_heat=False,
                on_progress=on_enrich_progress,
            )
            if enrich_log.strip():
                _append_log_detail(log_lines, enrich_log)
            enrich_path = save_enriched(enrich_result)
            invalidate_activity_cache()
            failed_enrich = max(0, pending_enrich - enrich_result.new_count)
            enrich_line = (
                f"=== 保存活动数据 ===\n"
                f"新拉取 {enrich_result.new_count} 条，"
                f"共 {enrich_result.total_count} 条（含历史记录） → {enrich_path}"
            )
            if failed_enrich > 0:
                enrich_line += f"\n另有 {failed_enrich} 条拉取失败，将在下次更新重试"
            log_lines.append(enrich_line)
            progress(
                step=enrich_step,
                total=REFRESH_ALL_TOTAL,
                message=(
                    f"详情拉取完成：成功 {enrich_result.new_count} 条"
                    + (f"，失败 {failed_enrich} 条" if failed_enrich > 0 else "")
                ),
            )
        else:
            progress(
                step=enrich_step,
                total=REFRESH_ALL_TOTAL,
                message="使用本地活动缓存，跳过详情拉取…",
            )
            enrich_result = load_cached_enrich_result()
            enrich_line = (
                f"=== 活动缓存 ===\n"
                f"无新链接，直接读取本地 {enrich_result.total_count} 条活动记录"
            )
            log_lines.append(enrich_line)

        heat_step = len(DS_HANDLERS) + 4
        pending_heat = count_pending_heat_backfill()
        heat_backfilled = 0
        heat_failed = 0
        if pending_heat > 0:
            logger.info("开始补全活动热度：待处理 %s 条", pending_heat)
            progress(
                step=heat_step,
                total=REFRESH_ALL_TOTAL,
                message=f"正在检查并补全 {pending_heat} 条缺失热度的活动…",
            )

            def on_heat_progress(done: int, total: int, phase: str) -> None:
                if total > 0:
                    message = f"{phase} ({done}/{total})"
                else:
                    message = phase
                progress(step=heat_step, total=REFRESH_ALL_TOTAL, message=message)

            heat_result, heat_log = _capture_output(
                backfill_repost_counts,
                workers=HEAT_BACKFILL_WORKERS,
                on_progress=on_heat_progress,
            )
            if heat_log.strip():
                _append_log_detail(log_lines, heat_log)
            heat_backfilled = int(heat_result.get("updated") or 0)
            heat_failed = int(heat_result.get("failed") or 0)
            remaining_heat = count_pending_heat_backfill()
            heat_line = (
                f"=== 热度补全 ===\n"
                f"待补全 {pending_heat} 条，成功 {heat_backfilled} 条"
                + (f"，失败 {heat_failed} 条" if heat_failed > 0 else "")
                + (f"，仍缺失 {remaining_heat} 条" if remaining_heat > 0 else "")
            )
            log_lines.append(heat_line)
            invalidate_activity_cache()
            enrich_result = load_cached_enrich_result()
            progress(
                step=heat_step,
                total=REFRESH_ALL_TOTAL,
                message=(
                    f"热度补全完成：更新 {heat_backfilled} 条"
                    + (f"，仍缺失 {remaining_heat} 条" if remaining_heat > 0 else "")
                ),
                log_append=heat_line,
            )
        else:
            progress(
                step=heat_step,
                total=REFRESH_ALL_TOTAL,
                message="活动热度数据已完整，跳过补全…",
            )

        status_step = len(DS_HANDLERS) + 5
        progress(step=status_step, total=REFRESH_ALL_TOTAL, message="正在刷新活动状态…")
        status_result = refresh_activity_statuses()
        invalidate_activity_cache()
        status_line = (
            f"=== 刷新活动状态 ===\n"
            f"共 {status_result['total']} 条，标记结束 {status_result['ended_marked']} 条，"
            f"修正开奖时间 {status_result.get('migrated_times', 0)} 条，"
            f"排除充电抽奖 {status_result.get('migrated_charging', 0)} 条，"
            f"列表可展示 {sum(status_result['listable_counts'].values())} 条"
        )
        log_lines.append(status_line)
        progress(
            step=status_step,
            total=REFRESH_ALL_TOTAL,
            message=f"状态刷新完成，标记结束 {status_result['ended_marked']} 条",
            log_append=status_line,
        )

        summary_parts = [
            f"检查 {len(DS_HANDLERS)} 个数据源，{sources_updated} 个有新专栏",
            f"新增链接 {merge_result.new_count} 条",
            f"新分类 {classify_result.new_count} 条",
            f"新拉取详情 {enrich_result.new_count} 条",
            f"补全热度 {heat_backfilled} 条",
            f"当前共 {enrich_result.total_count} 条活动记录",
            f"标记结束 {status_result['ended_marked']} 条",
        ]

        logger.info(
            "一键更新完成：新链接 %s，新详情 %s，热度补全 %s",
            merge_result.new_count,
            enrich_result.new_count,
            heat_backfilled,
        )

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
                "status_refresh": status_result,
            },
            "log": sanitize_log("\n".join(log_lines).strip()),
        }

    if action == "refresh_status":
        try:
            progress(step=1, total=1, message="正在刷新活动状态…")
            status_result = refresh_activity_statuses()
            invalidate_activity_cache()
        except OSError as exc:
            raise RuntimeError(f"刷新活动状态失败：{exc}") from exc
        counts = status_result.get("status_counts") or {}
        listable = status_result.get("listable_counts") or {}
        message = (
            f"状态刷新完成：标记结束 {status_result.get('ended_marked', 0)} 条，"
            f"列表展示 已参加 {listable.get('已参加', 0)} / 未参加 {listable.get('未参加', 0)} / "
            f"已结束 {listable.get('已结束', 0)}"
        )
        log = (
            f"=== 刷新活动状态 ===\n"
            f"共 {status_result.get('total', 0)} 条活动（历史记录全部保留）\n"
            f"标记结束 {status_result.get('ended_marked', 0)} 条\n"
            f"修正开奖时间 {status_result.get('migrated_times', 0)} 条\n"
            f"排除充电抽奖 {status_result.get('migrated_charging', 0)} 条\n"
            f"当前统计：已结束 {counts.get('已结束', 0)} / 已参加 {counts.get('已参加', 0)} / "
            f"未参加 {counts.get('未参加', 0)}"
        )
        return {
            "ok": True,
            "message": message,
            "result": status_result,
            "log": sanitize_log(log),
        }

    if action == "participate":
        dynamic_id = str(params.get("dynamic_id") or "").strip()
        if not is_valid_dynamic_id(dynamic_id):
            raise ValueError("活动 ID 无效")
        try:
            lottery_type = lookup_lottery_type(dynamic_id)
        except RuntimeError as exc:
            logger.warning("参与失败：未找到活动类型 %s — %s", dynamic_id, exc)
            raise ValueError(f"未找到活动 {dynamic_id} 的类型信息，请先一键更新") from exc
        total_steps = 1 if lottery_type == "预约抽奖" else 5
        progress(step=0, total=total_steps, message="准备参与活动…")
        logger.info("开始参与活动 %s (%s)", dynamic_id, lottery_type)

        def on_step(step: int, total: int, message: str, _action_name: str) -> None:
            progress(step=step, total=total, message=message, log_append=message)

        def _participate() -> dict:
            with BilibiliClient() as client:
                result = participate_activity(
                    client,
                    dynamic_id=dynamic_id,
                    lottery_type=lottery_type,
                    action_text=get_participate_text(),
                    dry_run=False,
                    persist=True,
                    on_step=on_step,
                )
                return result.to_dict()

        try:
            payload, _ = _capture_output(_participate)
        except Exception as exc:
            logger.exception("参与活动异常 %s", dynamic_id)
            raise
        ok = payload.get("status") == "joined"
        logger.info(
            "参与活动结束 %s status=%s message=%s",
            dynamic_id,
            payload.get("status"),
            payload.get("message"),
        )
        action_log = format_participation_log(payload)
        return {
            "ok": ok,
            "message": payload.get("message") or ("参与成功" if ok else "参与未完成，请查看步骤结果"),
            "result": payload,
            "log": action_log,
        }

    raise ValueError(f"未知操作: {action}")
