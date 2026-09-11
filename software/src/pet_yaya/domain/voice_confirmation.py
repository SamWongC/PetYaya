"""Only explicit, whole-utterance consent may approve a pending memory."""
import re


def parse_memory_confirmation(text: str) -> bool | None:
    normalized = re.sub(r"[\s，,。.!！]", "", text).lower()
    if normalized in {"确认", "確認", "确认保存", "確認保存", "记住吧", "記住吧",
                       "请记住", "請記住", "保存吧", "可以记住", "可以記住", "同意保存",
                       "可以", "可以啊", "可以呀", "可以的", "好", "好的", "好啊", "好呀",
                       "没问题", "沒問題", "没问题啊", "行", "行啊", "同意", "嗯记下来吧"}:
        return True
    if normalized in {"不要", "算了", "不保存", "不要保存", "不要记住", "不要記住",
                       "取消", "拒绝", "拒絕", "先别记", "先別記", "不要了", "先别保存", "不行"}:
        return False
    return None

