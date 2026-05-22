"""DeepSeek 消息预分析层 — 在调主 Agent 之前理解对方在说什么"""
import json
from datetime import datetime
from typing import Optional

import httpx

from config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    DEEPSEEK_ENABLED,
)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


SYSTEM_PROMPT = """你是微信消息分析助手。给定对方发来的消息和近期上下文,输出一个 JSON 对象,包含:

- intent: 意图,从 [闲聊, 咨询, 请求, 约定, 工作安排, 情感倾诉, 敏感话题, 其他] 中选一个
- emotion: 情绪,从 [中性, 开心, 不满, 焦虑, 急切, 难过] 中选一个
- risk: 回复风险等级,从 [low, medium, high] 中选一个
  * low: 普通闲聊、表情、寒暄
  * medium: 涉及具体事项、约定、需要承诺、可能影响关系
  * high: 涉及金钱、隐私、敏感关系、需要明确表态、误回会出问题
- summary: 一句话概括对方在表达什么(20 字以内)
- reply_hint: 给回复生成层的建议,提示该回什么核心要点(30 字以内)

只输出 JSON,不要任何其它文字。"""


_FALLBACK = {
    "intent": "其他",
    "emotion": "中性",
    "risk": "medium",
    "summary": "(分析未启用或失败)",
    "reply_hint": "按一般闲聊风格回复",
    "_source": "fallback",
}


async def analyze_message(
    chat: str,
    sender: str,
    content: str,
    context: Optional[str] = None,
    timeout: float = 15.0,
) -> dict:
    """调 DeepSeek 对一条新消息做预分析,返回结构化 dict。
    失败/未启用时返回兜底结构,主流程不应中断。
    """
    if not DEEPSEEK_ENABLED:
        return dict(_FALLBACK)

    user_payload = (
        f"联系人: {chat}\n"
        f"发送者: {sender}\n"
        f"近期上下文:\n{context or '(无)'}\n\n"
        f"对方刚发的消息: {content}"
    )

    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{DEEPSEEK_API_BASE.rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            parsed = json.loads(text)
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
        print(f"{_ts()} [DEEPSEEK] 分析失败: {e}", flush=True)
        out = dict(_FALLBACK)
        out["summary"] = f"(分析失败: {type(e).__name__})"
        return out

    out = {
        "intent": parsed.get("intent", "其他"),
        "emotion": parsed.get("emotion", "中性"),
        "risk": parsed.get("risk", "medium"),
        "summary": parsed.get("summary", ""),
        "reply_hint": parsed.get("reply_hint", ""),
        "_source": "deepseek",
    }
    print(
        f"{_ts()} [DEEPSEEK] {chat} → intent={out['intent']} "
        f"emotion={out['emotion']} risk={out['risk']} | {out['summary']}",
        flush=True,
    )
    return out


def format_brief(analysis: dict) -> str:
    """把分析结果格式化成给 Agent 看的简报"""
    return (
        f"[DeepSeek 预分析]\n"
        f"  意图: {analysis.get('intent', '?')}\n"
        f"  情绪: {analysis.get('emotion', '?')}\n"
        f"  风险: {analysis.get('risk', '?')}\n"
        f"  概要: {analysis.get('summary', '')}\n"
        f"  回复建议: {analysis.get('reply_hint', '')}"
    )
