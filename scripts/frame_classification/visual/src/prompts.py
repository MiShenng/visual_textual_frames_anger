from __future__ import annotations


def normalize_label(value: object, allowed: list[str], aliases: dict[str, str] | None = None) -> str:
    text = str(value or "").strip().replace(" ", "").replace("　", "")
    if aliases:
        text = aliases.get(text, text)
    if text not in allowed:
        raise ValueError(f"模型返回类目不在允许范围内: {text} | allowed={allowed}")
    return text


def build_visual_batch_prompt(
    items: list[dict],
    visual_labels: list[str],
    arousal_labels: list[str],
    confidence_labels: list[str],
) -> str:
    visual_label_text = "/".join(visual_labels)
    arousal_label_text = "/".join(arousal_labels)
    confidence_label_text = "/".join(confidence_labels)

    lines = [
        "请对下面这些视频切片逐一做视觉编码。",
        "请严格按输入顺序返回 JSON 数组，不要返回 markdown 代码块。",
        "数组中每个对象必须包含：slice_id、visual_label、visual_confidence、visual_reason、arousal_label、arousal_confidence、arousal_reason、visual_cues、image_text。",
        "",
        "类目约束：",
        f"- visual_label 只能是：{visual_label_text}",
        f"- arousal_label 只能是：{arousal_label_text}",
        f"- visual_confidence 只能是：{confidence_label_text}",
        f"- arousal_confidence 只能是：{confidence_label_text}",
        "- visual_cues 必须是数组，最多 3 条；无内容时返回 []。",
        '- image_text 无内容时返回空字符串 ""。',
        "",
        "输出格式：",
        "[",
        '  {"slice_id":"...","visual_label":"...","visual_confidence":"...","visual_reason":"...","arousal_label":"...","arousal_confidence":"...","arousal_reason":"...","visual_cues":["..."],"image_text":"..."}',
        "]",
        "",
        f"本批次共 {len(items)} 张图。",
        "每张图的 slice_id 会紧跟在对应图片前提供。",
        "请仅输出结果 JSON，不要解释。",
        "",
    ]
    lines.append("请只返回 JSON 数组。")
    return "\n".join(lines).strip()
