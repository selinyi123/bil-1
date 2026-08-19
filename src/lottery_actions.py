from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from typing import Callable, Literal

from src.bilibili_auth import get_login_uid, require_login
from src.bilibili_client import BilibiliClient, api_code
from src.lottery_api import fetch_dynamic_detail, fetch_notice_for_interact, fetch_opus_detail_item
from src.sources.common import opus_link

ActionName = Literal["like", "follow", "favorite", "repost", "comment", "reserve"]

DEFAULT_PARTICIPATE_TEXT = "好运连连！"

LIKE_URL = "https://api.bilibili.com/x/dynamic/feed/dyn/thumb"
FOLLOW_URL = "https://api.bilibili.com/x/relation/modify"
RELATION_URL = "https://api.bilibili.com/x/relation"
FAV_LIST_URL = "https://api.bilibili.com/x/v3/fav/folder/created/list-all"
FAV_RESOURCE_LIST_URL = "https://api.bilibili.com/x/v3/fav/resource/list"
FAV_DEAL_URL = "https://api.bilibili.com/x/v3/fav/resource/deal"
COSMO_SIMPLE_ACTION_URL = "https://api.bilibili.com/x/community/cosmo/interface/simple_action"
REPOST_URL = "https://api.vc.bilibili.com/dynamic_repost/v1/dynamic_repost/repost"
COMMENT_URL = "https://api.bilibili.com/x/v2/reply/add"
REPLY_MAIN_URL = "https://api.bilibili.com/x/v2/reply/main"

FAV_CONTENT_TYPE = 24
FOLLOWING_ATTRIBUTES = {2, 6}
SPACE_FEED_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
SPACE_FEED_PAGE_SIZE = 20
SPACE_FEED_MAX_PAGES = 3
ACTION_INTERVAL_SEC = 1.5
ACTION_LABELS: dict[ActionName, str] = {
    "like": "点赞",
    "follow": "关注",
    "favorite": "收藏",
    "repost": "转发",
    "comment": "评论",
    "reserve": "预约",
}
PARTICIPATION_STEPS: tuple[ActionName, ...] = ("like", "follow", "favorite", "repost", "comment")

# 评论验证码 OCR（可选）：评论接口返回 12015（需要验证码）且 data.url 为验证码图片时，
# 若配置了本地 OCR 服务（BINGGO_CAPTCHA_OCR_URL），识别后带 code 重发；未配置则按失败跳过。
CAPTCHA_REQUIRED_CODE = 12015
CAPTCHA_WRONG_CODE = 12073
CAPTCHA_OCR_URL_ENV = "BINGGO_CAPTCHA_OCR_URL"
DEFAULT_CAPTCHA_OCR_URL = "http://127.0.0.1:9898/ocr/url/text"
CAPTCHA_MAX_ATTEMPTS = 3


def _ocr_recognize(captcha_url: str) -> str | None:
    """调用本地 OCR 服务识别验证码图片，返回验证码文本；未配置/失败返回 None。"""
    endpoint = os.environ.get(CAPTCHA_OCR_URL_ENV, "").strip() or DEFAULT_CAPTCHA_OCR_URL
    try:
        import httpx

        response = httpx.post(endpoint, json={"url": captcha_url}, timeout=10.0)
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except Exception:
            data = None
        text = ""
        if isinstance(data, dict):
            text = str(data.get("text") or data.get("code") or "")
        elif isinstance(data, str):
            text = data
        else:
            text = response.text or ""
        text = text.strip()
        return text or None
    except Exception:
        return None


@dataclass
class ActionResult:
    action: ActionName
    ok: bool
    detail: str = ""
    extra: dict | None = None  # 附加结构化信息（如 repost 创建出的动态 id）


@dataclass
class DynamicContext:
    dynamic_id: str
    sender_uid: int
    referer: str
    comment_rid: str
    comment_type: int
    liked: bool
    favorited: bool
    favorite_available: bool
    followed: bool
    reposted: bool
    commented: bool


def _api_code(payload: dict) -> int:
    code = payload.get("code")
    if code is None:
        return -1
    try:
        return int(code)
    except (TypeError, ValueError):
        return -1


def _api_message(payload: dict) -> str:
    return str(payload.get("message") or payload.get("msg") or "").strip()


def _default_fav_folder_id(client: BilibiliClient, *, uid: int, referer: str) -> str:
    payload = client.get_json(FAV_LIST_URL, params={"up_mid": uid}, referer=referer)
    folders = (payload.get("data") or {}).get("list") or []
    if not folders:
        raise RuntimeError("未找到可用收藏夹")
    folder = folders[0]
    folder_id = folder.get("id") or folder.get("fid")
    if not folder_id:
        raise RuntimeError("收藏夹 ID 解析失败")
    return str(folder_id)


def resolve_sender_uid(item: dict) -> int:
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    for key in ("mid", "uid", "up_mid"):
        value = author.get(key)
        if value:
            return int(value)
    raise RuntimeError("无法从动态详情解析 UP 主 UID")


def _extract_module_stat(item: dict) -> dict:
    modules = item.get("modules") or {}
    if isinstance(modules, dict):
        stat = modules.get("module_stat") or {}
        return stat if isinstance(stat, dict) else {}
    if isinstance(modules, list):
        for module in modules:
            if not isinstance(module, dict):
                continue
            if module.get("module_type") != "MODULE_TYPE_STAT" and not module.get("module_stat"):
                continue
            stat = module.get("module_stat") or {}
            if isinstance(stat, dict):
                return stat
    return {}


def _module_stat_confirms_no_favorite(stat: dict) -> bool:
    """同时有转发与评论统计但无 favorite，对应 B 站页面上无收藏按钮的动态。"""
    if not stat or "favorite" in stat:
        return False
    has_forward = any(key in stat for key in ("forward", "repost", "share"))
    has_comment = "comment" in stat
    return has_forward and has_comment


def favorite_supported(
    item: dict,
    *,
    client: BilibiliClient | None = None,
    dynamic_id: str | None = None,
) -> bool:
    """动态是否支持收藏。不确定时默认尝试收藏，避免 dynamic/detail 缺字段导致误判。"""
    stat = _extract_module_stat(item)
    if stat and "favorite" in stat:
        return True
    if stat and _module_stat_confirms_no_favorite(stat):
        if client is not None and dynamic_id:
            opus_item = fetch_opus_detail_item(client, dynamic_id)
            if opus_item:
                opus_stat = _extract_module_stat(opus_item)
                if opus_stat and "favorite" in opus_stat:
                    return True
        return False
    return True


def build_dynamic_context(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    action_text: str,
    sender_uid: int | None = None,
) -> DynamicContext:
    item = fetch_dynamic_detail(client, dynamic_id)
    if not item:
        raise RuntimeError("无法获取动态详情")

    referer = opus_link(dynamic_id)
    basic = item.get("basic") or {}
    comment_rid = str(basic.get("comment_id_str") or dynamic_id)
    comment_type = int(basic.get("comment_type") or 17)
    uid = sender_uid or resolve_sender_uid(item)

    modules = item.get("modules") or {}
    stat = modules.get("module_stat") or {}
    like_obj = stat.get("like") or {}
    liked = bool(like_obj.get("status"))

    followed = is_following(client, uid=uid, referer=referer)
    favorite_available = favorite_supported(item, client=client, dynamic_id=dynamic_id)
    favorited = (
        is_favorited(client, dynamic_id=dynamic_id, referer=referer)
        if favorite_available
        else False
    )
    reposted = is_reposted(client, dynamic_id=dynamic_id, referer=referer)
    commented = has_comment(
        client,
        rid=comment_rid,
        comment_type=comment_type,
        action_text=action_text,
        referer=referer,
    )

    return DynamicContext(
        dynamic_id=dynamic_id,
        sender_uid=uid,
        referer=referer,
        comment_rid=comment_rid,
        comment_type=comment_type,
        liked=liked,
        favorited=favorited,
        favorite_available=favorite_available,
        followed=followed,
        reposted=reposted,
        commented=commented,
    )


def is_following(client: BilibiliClient, *, uid: int, referer: str) -> bool:
    try:
        payload = client.request_json(RELATION_URL, params={"fid": uid}, referer=referer)
    except RuntimeError:
        return False
    if api_code(payload) != 0:
        return False
    attribute = int((payload.get("data") or {}).get("attribute") or 0)
    return attribute in FOLLOWING_ATTRIBUTES


def _opus_favorite_status(client: BilibiliClient, *, dynamic_id: str, referer: str) -> bool | None:
    try:
        payload = client.get_json(
            "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail",
            params={
                "id": dynamic_id,
                "features": "htmlNewStyle,ugcDelete,editable,opusPrivateVisible",
            },
            referer=referer,
        )
    except RuntimeError:
        return None
    if _api_code(payload) != 0:
        return None
    item = (payload.get("data") or {}).get("item") or {}
    for module in item.get("modules") or []:
        if module.get("module_type") != "MODULE_TYPE_STAT":
            continue
        favorite = (module.get("module_stat") or {}).get("favorite") or {}
        return bool(favorite.get("status"))
    return None


def is_favorited(client: BilibiliClient, *, dynamic_id: str, referer: str) -> bool:
    status = _opus_favorite_status(client, dynamic_id=dynamic_id, referer=referer)
    return bool(status)


def is_reposted(client: BilibiliClient, *, dynamic_id: str, referer: str) -> bool:
    notice = fetch_notice_for_interact(client, dynamic_id)
    if notice:
        return bool(notice[0].get("reposted"))
    return has_reposted_in_space_feed(client, dynamic_id=dynamic_id)


def has_reposted_in_space_feed(client: BilibiliClient, *, dynamic_id: str) -> bool:
    uid = get_login_uid()
    if not uid:
        return False
    referer = f"https://space.bilibili.com/{uid}/dynamic"
    offset = ""
    target = str(dynamic_id)
    for _ in range(SPACE_FEED_MAX_PAGES):
        try:
            payload = client.request_json(
                SPACE_FEED_URL,
                params={"host_mid": uid, "offset": offset, "type": "all"},
                referer=referer,
            )
        except RuntimeError:
            return False
        if api_code(payload) != 0:
            return False
        data = payload.get("data") or {}
        items = data.get("items") or []
        for item in items:
            if item.get("type") != "DYNAMIC_TYPE_FORWARD":
                continue
            orig = item.get("orig") or {}
            if str(orig.get("id_str") or "") == target:
                return True
        offset = str(data.get("offset") or "")
        if not offset or len(items) < SPACE_FEED_PAGE_SIZE:
            break
    return False


def has_comment(
    client: BilibiliClient,
    *,
    rid: str,
    comment_type: int,
    action_text: str,
    referer: str,
) -> bool:
    uid = get_login_uid()
    if not uid:
        return False
    try:
        payload = client.request_json(
            REPLY_MAIN_URL,
            params={"oid": rid, "type": comment_type, "mode": 3, "next": 0, "ps": 20},
            referer=referer,
        )
    except RuntimeError:
        return False
    if api_code(payload) != 0:
        return False
    replies = (payload.get("data") or {}).get("replies") or []
    target = action_text.strip()
    for reply in replies:
        member = reply.get("member") or {}
        if str(member.get("mid")) != str(uid):
            continue
        content = reply.get("content") or {}
        message = str(content.get("message") or "")
        if target and target in message:
            return True
    return False


def like_dynamic(client: BilibiliClient, *, dynamic_id: str, csrf: str, referer: str) -> ActionResult:
    payload = client.post_json(
        LIKE_URL,
        {
            "dyn_id_str": dynamic_id,
            "up": 1,
            "spmid": "333.1369.0.0",
            "from_spmid": "333.999.0.0",
        },
        params={"csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        return ActionResult("like", True, "")
    if code == 65006:
        return ActionResult("like", True, "已赞过")
    return ActionResult("like", False, f"code={code} {_api_message(payload)}".strip())


def follow_user(client: BilibiliClient, *, uid: int, csrf: str, referer: str) -> ActionResult:
    payload = client.post_form(
        FOLLOW_URL,
        {"fid": uid, "act": 1, "re_src": 11, "csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        return ActionResult("follow", True, f"uid={uid}")
    if code == 22014:
        return ActionResult("follow", True, f"uid={uid} 已关注")
    return ActionResult("follow", False, f"code={code} {_api_message(payload)}".strip())


def favorite_dynamic(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    csrf: str,
    referer: str,
) -> ActionResult:
    if is_favorited(client, dynamic_id=dynamic_id, referer=referer):
        return ActionResult("favorite", True, "已收藏，跳过")

    payload = client.post_json(
        COSMO_SIMPLE_ACTION_URL,
        {
            "meta": {
                "spmid": "444.42.0.0",
                "from_spmid": "333.1365.0.0",
                "from": "unknown",
            },
            "entity": {
                "object_id_str": dynamic_id,
                "type": {"biz": 2},
            },
            "action": 3,
        },
        params={"csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    message = _api_message(payload)
    if code == 0:
        for attempt in range(4):
            if is_favorited(client, dynamic_id=dynamic_id, referer=referer):
                return ActionResult("favorite", True, "")
            if attempt < 3:
                time.sleep(0.6 + attempt * 0.4)
        return ActionResult("favorite", False, message or "收藏状态未更新")
    if code in (65006, 75008):
        return ActionResult("favorite", True, message or "已收藏")
    return ActionResult("favorite", False, f"code={code} {message}".strip())


def assemble_repost_content(
    base_text: str,
    *,
    at_users: list[dict] | None = None,
    topic: str = "",
    max_len: int = 233,
) -> tuple[str, str]:
    """组装转发内容 + @ctrl（B 站 ctrl 定位 JSON）。

    返回 (content, ctrl_json)：内容为 base_text + 可选话题 + 可选 @好友；
    ctrl 记录每个 @ 在截断后 content 中的定位（type=1 表示 @ 用户）。
    """
    parts = [base_text]
    if topic:
        parts.append(str(topic).strip())
    content = " ".join(part.strip() for part in parts if str(part).strip())
    # 先对 base_text + topic 截断，再逐条追加 @（避免 233 截断出残缺 @）
    if len(content) > max_len:
        content = content[:max_len]

    ctrl: list[dict] = []
    cursor = len(content)
    for user in at_users or []:
        name = str(user.get("name") or "").strip()
        uid = user.get("uid")
        if not name or uid is None:
            continue
        candidate = f" @{name}"
        if cursor + len(candidate) > max_len:
            break  # 剩余空间不足：跳过后续 @，绝不写残缺 @
        content += candidate
        ctrl.append({"location": cursor + 1, "length": len(name) + 1, "type": 1, "data": str(uid)})
        cursor += len(candidate)
    return content, json.dumps(ctrl, ensure_ascii=False, separators=(",", ":"))


def repost_dynamic(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    my_uid: int,
    csrf: str,
    referer: str,
    content: str,
    ctrl: str = "[]",
) -> ActionResult:
    payload = client.post_form(
        REPOST_URL,
        {
            "uid": str(my_uid),
            "dynamic_id": dynamic_id,
            "content": content[:233],
            "ctrl": ctrl,
            "csrf": csrf,
        },
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        # 记录本次真实创建出的转发动态 id（exact ownership：cleanup 只删它，
        # 而不是通过源动态 id 推断——B 站 repost 成功响应 data 含新动态 id）
        extra: dict | None = None
        data = payload.get("data")
        if isinstance(data, dict):
            created_id = str(
                data.get("dynamic_id_str") or data.get("dynamic_id") or ""
            ).strip()
            if created_id:
                extra = {"created_dynamic_id": created_id}
        return ActionResult("repost", True, content[:80], extra=extra)
    message = _api_message(payload)
    if "已" in message or "重复" in message:
        return ActionResult("repost", True, "已转发")
    return ActionResult("repost", False, f"code={code} {message}".strip())


def comment_dynamic(
    client: BilibiliClient,
    *,
    rid: str,
    comment_type: int,
    message: str,
    csrf: str,
    referer: str,
) -> ActionResult:
    def _post(extra: dict[str, object] | None = None) -> tuple[int, dict]:
        payload = client.post_form(
            COMMENT_URL,
            {"oid": rid, "type": comment_type, "message": message, "csrf": csrf, **(extra or {})},
            referer=referer,
            raise_on_code=False,
        )
        return _api_code(payload), payload

    code, payload = _post()
    if code == 0:
        return ActionResult("comment", True, message[:80])
    if code == 12051:
        return ActionResult("comment", True, "已有相同评论")

    # 需要验证码：若配置 OCR 服务则识别后带 code 重发
    if code == CAPTCHA_REQUIRED_CODE:
        captcha_url = str((payload.get("data") or {}).get("url") or "").strip()
        if captcha_url:
            for _ in range(CAPTCHA_MAX_ATTEMPTS):
                code_text = _ocr_recognize(captcha_url)
                if not code_text:
                    return ActionResult("comment", False, "评论需要验证码，OCR 未识别")
                code2, _ = _post({"code": code_text})
                if code2 == 0:
                    return ActionResult("comment", True, message[:80])
                if code2 == 12051:
                    return ActionResult("comment", True, "已有相同评论")
                if code2 != CAPTCHA_WRONG_CODE:
                    break
            return ActionResult("comment", False, "评论验证码重试失败")

    return ActionResult("comment", False, f"code={code} {_api_message(payload)}".strip())


def _ensure_participate_partition(client: BilibiliClient, name: str) -> int | None:
    """查找或创建指定关注分区，返回 tagid；失败返回 None。"""
    for tag in client.get_relation_tags() or []:
        if not isinstance(tag, dict):
            continue
        if str(tag.get("name")) == name:
            try:
                return int(tag.get("tagid"))
            except (TypeError, ValueError):
                continue
    return client.create_relation_tag(name)


def execute_full_participation(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    sender_uid: int | None = None,
    action_text: str = DEFAULT_PARTICIPATE_TEXT,
    on_step: Callable[[int, int, str, ActionName], None] | None = None,
) -> tuple[list[ActionResult], DynamicContext]:
    text = (action_text or DEFAULT_PARTICIPATE_TEXT).strip() or DEFAULT_PARTICIPATE_TEXT
    context = build_dynamic_context(
        client,
        dynamic_id=dynamic_id,
        action_text=text,
        sender_uid=sender_uid,
    )

    total_steps = len(PARTICIPATION_STEPS)

    def report_step(step_index: int, action_name: ActionName, detail: str = "") -> None:
        if not on_step:
            return
        label = ACTION_LABELS.get(action_name, action_name)
        message = f"正在{label}（{step_index}/{total_steps}）"
        if detail:
            message = f"{message} · {detail}"
        on_step(step_index, total_steps, message, action_name)

    csrf, my_uid = require_login()
    actions: list[ActionResult] = []

    # 参与增强配置（抄热评由 participate_text 层处理；这里管 @好友/话题/随机间隔）
    from src.participate_enhance import load_participate_enhance

    enhance = load_participate_enhance()
    interval_cfg = enhance.get("action_interval_sec") or {}
    try:
        _interval_min = float(interval_cfg.get("min") or ACTION_INTERVAL_SEC * 0.5)
        _interval_max = float(interval_cfg.get("max") or ACTION_INTERVAL_SEC * 1.5)
    except (TypeError, ValueError):
        _interval_min, _interval_max = ACTION_INTERVAL_SEC * 0.5, ACTION_INTERVAL_SEC * 1.5

    def _action_sleep() -> None:
        low, high = min(_interval_min, _interval_max), max(_interval_min, _interval_max)
        time.sleep(max(0.0, random.uniform(low, high)))

    report_step(1, "like")
    if context.liked:
        actions.append(ActionResult("like", True, "已点赞，跳过"))
    else:
        actions.append(like_dynamic(client, dynamic_id=dynamic_id, csrf=csrf, referer=context.referer))
    _action_sleep()

    report_step(2, "follow")
    if context.followed:
        actions.append(ActionResult("follow", True, f"uid={context.sender_uid} 已关注，跳过"))
    else:
        follow_result = follow_user(client, uid=context.sender_uid, csrf=csrf, referer=context.referer)
        actions.append(follow_result)
        # 仅关注成功后才移入"抽奖临时关注"分区；关注失败不产生额外副作用
        # （修复：此前不看 follow_result.ok，失败也会创建/移动分区）
        if follow_result.ok:
            partition_cfg = enhance.get("partition") or {}
            if partition_cfg.get("enabled", False) and context.sender_uid:
                try:
                    tagid = _ensure_participate_partition(
                        client, str(partition_cfg.get("name") or "抽奖临时关注")
                    )
                    if tagid:
                        client.move_to_relation_tag(context.sender_uid, tagid)
                except RuntimeError:
                    pass
    _action_sleep()

    report_step(3, "favorite")
    if not context.favorite_available:
        actions.append(ActionResult("favorite", True, "无收藏入口，跳过"))
    elif context.favorited:
        actions.append(ActionResult("favorite", True, "已收藏，跳过"))
    else:
        actions.append(
            favorite_dynamic(client, dynamic_id=dynamic_id, csrf=csrf, referer=context.referer)
        )
    _action_sleep()

    report_step(4, "repost")
    if context.reposted:
        actions.append(ActionResult("repost", True, "已转发，跳过"))
    else:
        repost_content, repost_ctrl = assemble_repost_content(
            text,
            at_users=enhance.get("at_users") or [],
            topic=enhance.get("topic") or "",
        )
        actions.append(
            repost_dynamic(
                client,
                dynamic_id=dynamic_id,
                my_uid=my_uid,
                csrf=csrf,
                referer=context.referer,
                content=repost_content,
                ctrl=repost_ctrl,
            )
        )
    _action_sleep()

    report_step(5, "comment")
    if context.commented:
        actions.append(ActionResult("comment", True, "已评论，跳过"))
    else:
        actions.append(
            comment_dynamic(
                client,
                rid=context.comment_rid,
                comment_type=context.comment_type,
                message=text,
                csrf=csrf,
                referer=context.referer,
            )
        )

    return actions, context
