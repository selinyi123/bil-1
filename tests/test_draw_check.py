"""中奖深检（draw_check）测试。"""
from __future__ import annotations

from src.draw_check import DEFAULT_KEYWORDS, check_prize_draw, judge_keywords
from src.message_types import MessageEntry, MessageType


def test_judge_keywords_blacklist_overrides() -> None:
    patterns = ["~预约成功|预约主题", "中奖|恭喜|获得|幸运"]
    assert judge_keywords("恭喜你中奖了", patterns) is True
    assert judge_keywords("预约主题已开启", patterns) is False
    assert judge_keywords("普通消息", patterns) is False
    # 黑名单优先级更高（后写的规则覆盖）
    patterns2 = ["中奖", "~中了但取消"]
    assert judge_keywords("中奖了", patterns2) is True
    assert judge_keywords("中了但取消", patterns2) is False


def test_judge_keywords_empty() -> None:
    assert judge_keywords("", DEFAULT_KEYWORDS) is False
    assert judge_keywords("随便什么", []) is False


def _entry(talker_id: int, text: str, title: str = "") -> MessageEntry:
    return MessageEntry(
        msg_type=MessageType.REPLY,
        id=f"{talker_id}-{text}",
        talker_id=talker_id,
        talker_name=f"用户{talker_id}",
        timestamp=1,
        title=title,
        text=text,
        unread_count=0,
        raw={},
    )


def test_check_prize_draw_hits_and_pushes(monkeypatch) -> None:
    from src import draw_check
    from src.message_types import DmSession

    fake_at = [_entry(1, "恭喜中奖，请填写地址"), _entry(2, "无关消息")]
    fake_reply = [_entry(3, "抽中了奖品！")]
    fake_dm = [
        DmSession(talker_id=9, talker_name="官方", unread_count=2, timestamp=1, last_text="", is_follow=True, system_msg_type=0, raw={"last_msg_seqno": 5}),
        DmSession(talker_id=10, talker_name="路人", unread_count=1, timestamp=1, last_text="", is_follow=True, system_msg_type=0, raw={}),
    ]
    dm_messages = {
        9: [_entry(9, "您好，您中奖了，请填写收货信息"), _entry(9, "另一个消息")],
        10: [_entry(10, "你好")],
    }
    marked: list[int] = []
    sent_payloads: list[tuple[str, str]] = []

    monkeypatch.setattr(draw_check, "list_feed", lambda client, msg_type: (fake_at if msg_type == MessageType.AT else fake_reply, {}))
    monkeypatch.setattr(draw_check, "list_dm_sessions", lambda client, size: fake_dm)
    monkeypatch.setattr(
        draw_check,
        "fetch_dm_messages",
        lambda client, talker_id, session_type=1, size=20: dm_messages.get(talker_id, []),
    )
    monkeypatch.setattr(
        draw_check,
        "mark_dm_read",
        lambda client, talker_id, session_type=1, seqno=0: marked.append(talker_id) or True,
    )
    monkeypatch.setattr(
        draw_check,
        "send_notify",
        lambda title, desp="": sent_payloads.append((title, desp)) or {"sent": ["sct"], "skipped": []},
    )

    result = check_prize_draw(None)

    assert result["total"] == 3  # 1 @ + 1 回复 + 1 私信
    assert len(result["dm"]) == 1
    assert result["dm"][0]["talker_id"] == 9
    assert result["pushed"] is True
    assert len(sent_payloads) == 1
    assert "中奖" in sent_payloads[0][0]
    assert marked == [9]  # 仅命中关键词的会话标记已读（10 未命中不标）


def test_check_prize_draw_no_hits_no_push(monkeypatch) -> None:
    from src import draw_check

    sent: list = []

    monkeypatch.setattr(draw_check, "list_feed", lambda client, msg_type: ([], {}))
    monkeypatch.setattr(draw_check, "list_dm_sessions", lambda client, size: [])
    monkeypatch.setattr(draw_check, "send_notify", lambda title, desp="": sent.append(title) or {"sent": [], "skipped": []})

    result = check_prize_draw(None)
    assert result["total"] == 0
    assert result["pushed"] is False
    assert result["delivered"] is False
    assert result["acknowledged"] is False
    assert sent == []


def _make_dm_harness(monkeypatch, *, send_result, mark_side_effect=None):
    """构造中奖深检测试环境：1 个命中私信会话。返回 (marked, sent)。"""
    from src import draw_check
    from src.message_types import DmSession

    marked: list[int] = []
    sent: list[tuple[str, str]] = []

    monkeypatch.setattr(draw_check, "list_feed", lambda client, msg_type: ([], {}))
    monkeypatch.setattr(
        draw_check,
        "list_dm_sessions",
        lambda client, size: [
            DmSession(
                talker_id=9,
                talker_name="官方",
                unread_count=1,
                timestamp=1,
                last_text="",
                is_follow=True,
                system_msg_type=0,
                raw={"last_msg_seqno": 5},
            )
        ],
    )
    monkeypatch.setattr(
        draw_check,
        "fetch_dm_messages",
        lambda client, talker_id, session_type=1, size=20: [_entry(9, "您好，您中奖了")],
    )
    monkeypatch.setattr(
        draw_check,
        "mark_dm_read",
        mark_side_effect
        or (lambda client, talker_id, session_type=1, seqno=0: marked.append(talker_id) or True),
    )
    monkeypatch.setattr(
        draw_check,
        "send_notify",
        lambda title, desp="": sent.append((title, desp)) or send_result,
    )
    return marked, sent


def test_check_prize_draw_push_false_never_marks_read(monkeypatch) -> None:
    """push=False 时即使命中私信也绝不标记已读（保留未读供下次提醒）。"""
    from src import draw_check

    marked, sent = _make_dm_harness(monkeypatch, send_result={"sent": ["sct"], "skipped": []})
    result = check_prize_draw(None, push=False)
    assert result["total"] == 1
    assert result["delivered"] is False
    assert result["acknowledged"] is False
    assert marked == []  # 核心：未推送不吞私信
    assert sent == []


def test_check_prize_draw_delivery_failed_never_marks_read(monkeypatch) -> None:
    """全部通知渠道失败（sent=[]）时不得标记已读（避免中奖提醒被吞）。"""
    from src import draw_check

    marked, sent = _make_dm_harness(monkeypatch, send_result={"sent": [], "skipped": ["telegram"]})
    result = check_prize_draw(None)
    assert result["total"] == 1
    assert result["delivered"] is False
    assert result["acknowledged"] is False
    assert marked == []  # 核心：送达失败不 mark read
    assert len(sent) == 1  # 通知确实尝试过


def test_check_prize_draw_delivered_then_marks_read(monkeypatch) -> None:
    """至少一个渠道确认送达后才标记私信已读。"""
    from src import draw_check

    marked, _sent = _make_dm_harness(monkeypatch, send_result={"sent": ["sct"], "skipped": []})
    result = check_prize_draw(None)
    assert result["total"] == 1
    assert result["delivered"] is True
    assert result["acknowledged"] is True
    assert marked == [9]


def test_check_prize_draw_mark_read_failure_keeps_acknowledged_false(monkeypatch) -> None:
    """送达成功但 mark read 抛错 → delivered=True、acknowledged=False（下次可能重复提醒）。"""
    from src import draw_check

    def _fail_mark(client, talker_id, session_type=1, seqno=0):
        raise RuntimeError("mark read 网络失败")

    marked, _sent = _make_dm_harness(monkeypatch, send_result={"sent": ["sct"], "skipped": []}, mark_side_effect=_fail_mark)
    result = check_prize_draw(None)
    assert result["total"] == 1
    assert result["delivered"] is True
    assert result["acknowledged"] is False
