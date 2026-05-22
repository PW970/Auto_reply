"""风格画像 — 结构化 personality + per-contact 覆写 + 改写样本 few-shot

设计哲学:不直接 fine-tune,通过显式风格字段 + 真实改写样本注入 prompt。
- 结构化字段让 Agent 拿到的是"风格说明书"而不是模糊的"直爽干脆"
- 改写样本是用户真实编辑过的回复,信息量比静态描述高得多
"""
from typing import Optional

import drafts


# 默认全局画像 — 老用户的旧 personality 字符串会被映射到 tone
DEFAULT_PROFILE = {
    "tone": "",                # 整体语气描述
    "sentence_length": "",     # short / medium / long / mixed
    "punctuation": "",         # casual(常省略) / standard / strict
    "emoji": "",               # never / rarely / often
    "catchphrases": [],        # 口头禅
    "avoid": [],               # 禁用词/句式
    "examples": [],            # 典型说话样本(自由文本)
}


def _merge(base: dict, override: dict) -> dict:
    """override 中非空字段覆盖 base"""
    out = dict(base)
    for k, v in override.items():
        if v in (None, "", [], {}):
            continue
        out[k] = v
    return out


def resolve_profile(cfg: dict, contact: str) -> dict:
    """组合最终画像:DEFAULT < cfg.style_profile < cfg.contact_styles[contact]"""
    profile = dict(DEFAULT_PROFILE)

    # 向后兼容:旧 personality 字符串塞进 tone
    legacy = cfg.get("personality", "")
    if legacy and not cfg.get("style_profile"):
        profile["tone"] = legacy

    profile = _merge(profile, cfg.get("style_profile", {}))

    contact_styles = cfg.get("contact_styles", {}) or {}
    if contact in contact_styles:
        profile = _merge(profile, contact_styles[contact])

    return profile


def render_profile(profile: dict) -> str:
    """把 profile dict 渲染成给 Agent 的 markdown 块"""
    lines = ["[你的说话风格 — 请严格模仿]"]
    if profile.get("tone"):
        lines.append(f"  语气: {profile['tone']}")
    if profile.get("sentence_length"):
        labels = {"short": "短句为主", "medium": "中等长度",
                  "long": "偏长", "mixed": "长短交错"}
        lines.append(f"  句长: {labels.get(profile['sentence_length'], profile['sentence_length'])}")
    if profile.get("punctuation"):
        labels = {"casual": "口语化,常省略句号", "standard": "标准标点",
                  "strict": "严格标点"}
        lines.append(f"  标点: {labels.get(profile['punctuation'], profile['punctuation'])}")
    if profile.get("emoji"):
        labels = {"never": "不用", "rarely": "偶尔用", "often": "常用"}
        lines.append(f"  Emoji: {labels.get(profile['emoji'], profile['emoji'])}")
    if profile.get("catchphrases"):
        lines.append(f"  口头禅: {', '.join(profile['catchphrases'])}")
    if profile.get("avoid"):
        lines.append(f"  避免: {', '.join(profile['avoid'])}")
    if profile.get("examples"):
        lines.append("  典型句式:")
        for ex in profile["examples"][:5]:
            lines.append(f"    - {ex}")
    return "\n".join(lines) if len(lines) > 1 else ""


def render_feedback_fewshot(contact: str, limit: int = 3) -> str:
    """从草稿表里拉该联系人的改写样本(用户编辑过的真实样本)作为 few-shot"""
    samples = drafts.feedback_samples(contact=contact, limit=limit)
    if not samples:
        return ""
    lines = ["[历史改写样本 — 这些是 AI 生成 vs 你最终发出的对照,语气向'你的版本'靠拢]"]
    for s in samples:
        lines.append(f"  对方说: {s['original_msg']}")
        lines.append(f"    AI 草稿: {s['draft_reply']}")
        lines.append(f"    你改成: {s['final_reply']}")
    return "\n".join(lines)


def build_style_block(cfg: dict, contact: str) -> str:
    """给 prompt 拼接的完整风格块"""
    parts = []
    profile_md = render_profile(resolve_profile(cfg, contact))
    if profile_md:
        parts.append(profile_md)
    fewshot = render_feedback_fewshot(contact)
    if fewshot:
        parts.append(fewshot)
    return "\n\n".join(parts)
