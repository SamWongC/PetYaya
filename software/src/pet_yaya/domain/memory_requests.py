"""Handle explicit save requests independently of model suggestions."""

import re

from pet_yaya.domain.models import DialogueResult, MemoryCandidate


def explicit_memory_request(text: str) -> DialogueResult | None:
    if re.match(r"^(?:请)?(?:不要|别|先别|不用)(?:记|保存)", text):
        return DialogueResult(speech="好的，这句话不会新增长期记忆。如果要删除已有记忆，请先查看 /memory。")
    match = re.match(r"^(?:请\s*)?(?:帮我\s*)?(?:记住(?:一下)?|记下来|记下|保存一下|以后别忘了|别忘了|下次聊天你要记得)[\s，,:：]*(.*)$", text, re.S)
    if match is None:
        return None
    content = match.group(1).strip().strip("，,。；;！! ")
    if content in {"这个", "这件事", "刚才说的", "我的这个爱好", "这一点"}:
        return None  # Resolve references against user history, not the assistant's guesses.
    if not content:
        return DialogueResult(speech="请告诉我具体想记住什么，例如：请记住，我喜欢恐龙。")
    if len(content) > 200:
        return DialogueResult(speech="这条记忆太长了，请缩短到200字以内再告诉我。")
    # A conservative guard for explicit requests, not a general privacy classifier.
    if re.search(
        r"密码|口令|密钥|令牌|身份证|银行卡|电话|手机号|邮箱|住址|地址|病历|诊断|过敏|疾病|"
        r"password|api[_ -]?key|secret|token|@|\d{7,}",
        content,
        re.I,
    ):
        return DialogueResult(speech="这段内容可能包含敏感信息，请去掉敏感部分后再提出记忆请求。")
    category = "user_taught"
    if content.startswith(("我的名字是", "我叫", "我的昵称是")):
        category = "profile"
    elif content.startswith(("我喜欢", "我最喜欢")):
        category = "preference"
    return DialogueResult(
        speech=f"你希望保存的内容是：『{content}』。",
        memory_candidate=MemoryCandidate(
            category=category, content=content, source="explicit_user_request"
        ),
    )

