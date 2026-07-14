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
from src.merge_links import merge_activity_links, save_merged
from src.lottery_classifier import PARTICIPATABLE_TYPES
from src.lottery_actions import ActionResult
from src.participation import participate_activity
from src.participation_log import participation_succeeded
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
from web.activity_service import (
    build_triple_progress_plan,
    invalidate_activity_cache,
    lookup_lottery_type,
    pick_triple_participate_targets,
    participate_step_budget,
    resolve_participate_lottery_type,
)
from src.participation_store import set_participation
from web.user_messages import format_participation_log, friendly_error, sanitize_log

logger = get_logger("job")

HEAT_BACKFILL_WORKERS = 6
PARTICIPATE_TRIPLE_WORKERS = 1


def _deserialize_payload_actions(payload: dict[str, Any]) -> list[ActionResult]:
    actions: list[ActionResult] = []
    for item in payload.get("actions") or []:
        if not isinstance(item, dict):
            continue
        action_name = str(item.get("action") or "").strip()
        if not action_name:
            continue
        actions.append(
            ActionResult(
                action=action_name,  # type: ignore[arg-type]
                ok=bool(item.get("ok")),
                detail=str(item.get("detail") or ""),
            )
        )
    return actions


def _payload_joined_success(payload: dict[str, Any]) -> bool:
    if str(payload.get("status") or "") != "joined":
        return False
    lottery_type = str(payload.get("lottery_type") or "")
    actions = _deserialize_payload_actions(payload)
    if not actions:
        return False
    if lottery_type in ("互动抽奖", "转发抽奖", "预约抽奖"):
        return participation_succeeded(actions, lottery_type=lottery_type)
    return all(item.ok for item in actions)


def _normalize_participate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    dynamic_id = str(normalized.get("dynamic_id") or "")
    if normalized.get("status") == "joined" and not _payload_joined_success(normalized):
        normalized["status"] = "failed"
        normalized["message"] = str(normalized.get("message") or "参与未完成")
        if dynamic_id:
            set_participation(dynamic_id, "未参加")
    return normalized


def _participate_dynamic_payload(
    dynamic_id: str,
    on_step: Callable[[int, int, str, str], None],
    *,
    lottery_type_hint: str | None = None,
) -> dict[str, Any]:
    resolved_type = resolve_participate_lottery_type(dynamic_id, hint=lottery_type_hint)
    payload, _detail = _capture_output(
        _execute_participate,
        dynamic_id,
        on_step,
        lottery_type=resolved_type,
    )
    return _normalize_participate_payload(payload)


def _list_filter_params(params: dict[str, Any]) -> dict[str, str | None]:
    return {
        "status": str(params.get("status") or "").strip() or None,
        "lottery_type": str(params.get("lottery_type") or params.get("type") or "").strip() or None,
        "draw": str(params.get("draw") or "").strip() or None,
        "draw_window": str(params.get("draw_window") or "").strip() or None,
        "q": str(params.get("q") or "").strip() or None,
        "sort": str(params.get("sort") or "").strip() or None,
        "order": str(params.get("order") or "").strip() or None,
    }


def _execute_participate(
    dynamic_id: str,
    on_step: Callable[[int, int, str, str], None],
    *,
    lottery_type: str | None = None,
) -> dict[str, Any]:
    dynamic_id = str(dynamic_id or "").strip()
    if not is_valid_dynamic_id(dynamic_id):
        raise ValueError(f"活动 ID 无效: {dynamic_id}")
    resolved_type = str(lottery_type or "").strip()
    if resolved_type not in PARTICIPATABLE_TYPES:
        resolved_type = resolve_participate_lottery_type(dynamic_id)
    with BilibiliClient() as client:
        result = participate_activity(
            client,
            dynamic_id=dynamic_id,
            lottery_type=resolved_type,
            dry_run=False,
            persist=True,
            on_step=on_step,
        )
        payload = result.to_dict()
        payload["lottery_type"] = resolved_type
        return payload


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
            refreshed_at = int(time.time())
            if qrcode_refresh_count == 1:
                progress(
                    step=1,
                    total=1,
                    message="请使用哔哩哔哩 App 扫码登录",
                    log_append="已生成登录二维码",
                    login_phase="waiting",
                    qrcode_refreshed_at=refreshed_at,
                )
            else:
                progress(
                    step=1,
                    total=1,
                    message="二维码已刷新，请重新扫码",
                    log_append="二维码已自动刷新",
                    login_phase="waiting",
                    qrcode_refreshed_at=refreshed_at,
                )

        def on_login_status(phase: str, message: str) -> None:
            log_append = {
                "scanned": "已在手机扫码，等待确认",
                "confirming": "用户已确认，正在写入登录信息",
                "refreshing": "二维码已过期，请重新扫码",
            }.get(phase)
            progress(
                step=1,
                total=1,
                message=message,
                log_append=log_append,
                login_phase=phase,
            )

        progress(step=1, total=1, message="正在生成登录二维码…", login_phase="waiting")
        _, log = _capture_output(
            login_with_qrcode,
            open_image=False,
            auto_refresh_on_expire=False,
            cancel_event=cancel_event,
            on_qrcode_ready=on_qrcode_ready,
            on_status_change=on_login_status,
        )
        progress(step=1, total=1, message="登录成功，账号已就绪", login_phase="success")
        return {
            "ok": True,
            "message": "登录成功，账号已就绪",
            "log": sanitize_log(log) or "登录成功",
            "result": {"login_phase": "success"},
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
        total_steps = participate_step_budget(lottery_type, dynamic_id=dynamic_id)
        progress(step=0, total=total_steps, message="准备参与活动…")
        logger.info("开始参与活动 %s (%s)", dynamic_id, lottery_type)

        def on_step(step: int, total: int, message: str, _action_name: str) -> None:
            progress(step=step, total=total, message=message, log_append=message)

        try:
            payload = _participate_dynamic_payload(dynamic_id, on_step, lottery_type_hint=lottery_type)
        except Exception as exc:
            logger.exception("参与活动异常 %s", dynamic_id)
            raise
        ok = _payload_joined_success(payload)
        logger.info(
            "参与活动结束 %s status=%s message=%s",
            dynamic_id,
            payload.get("status"),
            payload.get("message"),
        )
        action_log = format_participation_log(payload)
        invalidate_activity_cache()
        return {
            "ok": ok,
            "message": payload.get("message") or ("参与成功" if ok else "参与未完成，请查看步骤结果"),
            "result": payload,
            "log": action_log,
        }

    if action == "participate_triple":
        if cancel_event and cancel_event.is_set():
            raise ValueError("任务已取消")

        filters = _list_filter_params(params)
        targets = pick_triple_participate_targets(**filters)
        if not targets:
            raise ValueError("当前列表没有可参与的未参加活动")

        target_ids = [str(item.get("dynamic_id") or "") for item in targets]
        total_steps, progress_plan = build_triple_progress_plan(targets)
        if total_steps <= 0:
            raise ValueError("当前列表没有可参与的未参加活动")

        logger.info("三连参与开始：%s", ", ".join(target_ids))
        progress(
            step=0,
            total=total_steps,
            message=f"准备三连参与 {len(targets)} 个活动…",
            log_append=f"目标活动：{', '.join(target_ids)}",
        )

        progress_lock = threading.Lock()
        task_states: dict[str, str] = {dynamic_id: "排队中…" for dynamic_id in target_ids}
        task_step_progress: dict[str, int] = {dynamic_id: 0 for dynamic_id in target_ids}

        def _overall_progress_step() -> int:
            total_done = 0
            for dynamic_id in target_ids:
                plan_entry = progress_plan.get(dynamic_id)
                if not plan_entry:
                    continue
                _, budget = plan_entry
                total_done += min(task_step_progress.get(dynamic_id, 0), budget)
            return min(total_done, total_steps)

        def _emit_triple_progress(*, log_append: str | None = None) -> None:
            progress(
                step=_overall_progress_step(),
                total=total_steps,
                message=_progress_snapshot(),
                log_append=log_append,
            )

        def _progress_snapshot() -> str:
            return " | ".join(f"{dynamic_id[-6:]}: {task_states[dynamic_id]}" for dynamic_id in target_ids)

        def _report_task_progress(dynamic_id: str, step: int, _total: int, message: str) -> None:
            if cancel_event and cancel_event.is_set():
                return
            if dynamic_id not in progress_plan:
                return
            with progress_lock:
                task_states[dynamic_id] = message
                task_step_progress[dynamic_id] = max(task_step_progress.get(dynamic_id, 0), step)
            _emit_triple_progress(log_append=f"{dynamic_id}: {message}")

        def _mark_task_done(dynamic_id: str, message: str) -> None:
            plan_entry = progress_plan.get(dynamic_id)
            if not plan_entry:
                return
            _, budget = plan_entry
            with progress_lock:
                task_states[dynamic_id] = message
                task_step_progress[dynamic_id] = budget
            _emit_triple_progress()

        def _run_one(target: dict[str, Any]) -> dict[str, Any]:
            dynamic_id = str(target.get("dynamic_id") or "")
            title = str(target.get("activity_title") or dynamic_id)

            if cancel_event and cancel_event.is_set():
                return {
                    "dynamic_id": dynamic_id,
                    "activity_title": title,
                    "lottery_type": str(target.get("lottery_type") or ""),
                    "payload": {
                        "dynamic_id": dynamic_id,
                        "lottery_type": str(target.get("lottery_type") or ""),
                        "status": "failed",
                        "message": "已取消",
                        "actions": [],
                    },
                    "detail": "",
                }

            target_lottery_type = str(target.get("lottery_type") or "").strip() or None

            def on_step(step: int, total: int, message: str, _action_name: str) -> None:
                _report_task_progress(dynamic_id, step, total, message)

            try:
                payload = _participate_dynamic_payload(
                    dynamic_id,
                    on_step,
                    lottery_type_hint=target_lottery_type,
                )
                detail = ""
            except Exception as exc:
                logger.exception("三连参与异常 %s", dynamic_id)
                payload = {
                    "dynamic_id": dynamic_id,
                    "lottery_type": target_lottery_type or "",
                    "status": "failed",
                    "message": friendly_error(exc),
                    "actions": [],
                }
                detail = ""
            with progress_lock:
                task_states[dynamic_id] = str(payload.get("message") or "完成")
            _mark_task_done(dynamic_id, str(payload.get("message") or "完成"))
            return {
                "dynamic_id": dynamic_id,
                "activity_title": title,
                "lottery_type": str(payload.get("lottery_type") or target.get("lottery_type") or ""),
                "payload": payload,
                "detail": detail,
            }

        results: list[dict[str, Any]] = []
        for target in targets:
            if cancel_event and cancel_event.is_set():
                break
            results.append(_run_one(target))

        results.sort(key=lambda item: target_ids.index(item["dynamic_id"]))
        joined_count = sum(1 for item in results if _payload_joined_success(item["payload"]))
        skipped_count = sum(
            1 for item in results if str(item["payload"].get("status") or "") == "skipped"
        )
        failed_count = len(results) - joined_count - skipped_count
        log_blocks = [format_participation_log(item["payload"]) for item in results]
        for item in results:
            if item.get("detail"):
                _append_log_detail(log_blocks, item["detail"])

        invalidate_activity_cache()
        cancelled = bool(cancel_event and cancel_event.is_set())
        if cancelled:
            message = "三连参与已取消"
            ok = False
        elif joined_count == len(results):
            message = f"三连参与完成：{joined_count} 个活动全部成功"
            ok = True
        elif joined_count > 0:
            message = (
                f"三连参与结束：成功 {joined_count} 个"
                + (f"，失败 {failed_count} 个" if failed_count else "")
                + (f"，跳过 {skipped_count} 个" if skipped_count else "")
            )
            ok = False
        else:
            message = "三连参与未完成，请查看各活动步骤结果"
            ok = False

        progress(step=total_steps, total=total_steps, message=message)
        logger.info(
            "三连参与结束 joined=%s failed=%s skipped=%s cancelled=%s ids=%s",
            joined_count,
            failed_count,
            skipped_count,
            cancelled,
            target_ids,
        )
        return {
            "ok": ok,
            "message": message,
            "result": {
                "targets": [
                    {
                        "dynamic_id": item["dynamic_id"],
                        "activity_title": item["activity_title"],
                        "lottery_type": item["lottery_type"],
                    }
                    for item in results
                ],
                "items": [item["payload"] for item in results],
                "joined": joined_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "cancelled": cancelled,
            },
            "log": sanitize_log("\n\n".join(log_blocks).strip()),
        }

    raise ValueError(f"未知操作: {action}")
