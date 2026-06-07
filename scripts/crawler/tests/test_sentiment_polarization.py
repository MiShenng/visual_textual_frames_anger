from app.workers.sentiment_polarization import analyze_comment, normalize_for_analysis


def test_normalize_for_analysis_masks_url_and_mention():
    text = "看这个链接 https://example.com @张三 #封存讨论#"
    result = normalize_for_analysis(text)
    assert "<URL>" in result
    assert "<MENTION>" in result
    assert "<TOPIC:封存讨论>" in result


def test_analyze_comment_support_stance_and_positive_sentiment():
    result = analyze_comment("我支持前科封存，应该给改过自新的人一次机会！")
    assert result.sentiment_label == "positive"
    assert result.stance_label == "support"
    assert result.has_policy_target is True


def test_analyze_comment_oppose_stance_and_negative_sentiment():
    result = analyze_comment("反对封存，这就是纵容，必须严惩，零容忍。")
    assert result.sentiment_label == "negative"
    assert result.stance_label == "oppose"
    assert result.has_policy_target is True


def test_analyze_comment_neutral_when_no_policy_target():
    result = analyze_comment("今天天气不错，晚饭吃什么？")
    assert result.stance_label == "neutral"
    assert result.has_policy_target is False
