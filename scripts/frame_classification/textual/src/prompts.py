from __future__ import annotations


def normalize_label(value: object, allowed: list[str], aliases: dict[str, str] | None = None) -> str:
    text = str(value or "").strip().replace(" ", "").replace("　", "")
    if aliases:
        text = aliases.get(text, text)
    if text not in allowed:
        raise ValueError(f"模型返回类目不在允许范围内: {text} | allowed={allowed}")
    return text


def build_text_prompt(item: dict[str, object]) -> str:
    return f"""
请根据以下短视频文本材料包进行双层编码。

video_id: {item.get("video_id", "")}

文本材料包：
{item.get("text_material", "")}

请只返回 JSON。
""".strip()

