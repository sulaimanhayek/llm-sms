import httpx2

import bot
from bot import DAILY_LIMIT, GSM_LIMIT, MESSAGES, handle_message


def test_question_is_sent_to_claude_with_the_right_settings(claude, ali):
    claude.replies.append(("Abu Al-Khaseeb fish market, Corniche St.", "end_turn"))
    handle_message(ali, "where can I eat fish?")

    request = claude.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"] == {"effort": "low"}
    assert request["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in claude.headers[0]["anthropic-beta"]
    assert request["tools"][0]["type"] == "web_search_20260209"
    assert request["tools"][0]["user_location"]["city"] == "Basra"
    assert request["messages"] == [{"role": "user", "content": "where can I eat fish?"}]


def test_system_prompt_has_the_profile_and_the_limit(claude, ali):
    claude.replies.append(("ok", "end_turn"))
    handle_message(ali, "hello")
    system = claude.requests[0]["system"]
    assert "Ali Hassan, from Basra, Iraq" in system
    assert f"under {GSM_LIMIT - 30} characters" in system


def test_arabic_question_gets_the_arabic_limit(claude, ali):
    claude.replies.append(("نعم", "end_turn"))
    handle_message(ali, "هل المكتبة مفتوحة؟")
    assert "under 104 characters" in claude.requests[0]["system"]


def test_answer_is_cleaned(claude, ali):
    claude.replies.append(("**Masgouf** – grilled carp, about 15,000 IQD.", "end_turn"))
    assert handle_message(ali, "what is masgouf?") == "Masgouf - grilled carp, about 15,000 IQD."


def test_long_answer_is_shortened(claude, ali):
    claude.replies.append(("word " * 200, "end_turn"))
    answer = handle_message(ali, "tell me everything")
    assert bot.sms_length(answer) <= GSM_LIMIT


def test_history_is_sent_with_the_next_question(claude, ali):
    claude.replies += [("Bab Al-Zubair market.", "end_turn"), ("Bus 7 from Saad Square.", "end_turn")]
    handle_message(ali, "where can I buy dates?")
    handle_message(ali, "how do I get there?")
    assert claude.requests[1]["messages"] == [
        {"role": "user", "content": "where can I buy dates?"},
        {"role": "assistant", "content": "Bab Al-Zubair market."},
        {"role": "user", "content": "how do I get there?"},
    ]


def test_history_keeps_only_the_last_three_exchanges(claude, ali):
    for i in range(5):
        claude.replies.append((f"answer {i}", "end_turn"))
        handle_message(ali, f"question {i}")
    history = bot.users[ali]["history"]
    assert len(history) == 6
    assert history[0] == {"role": "user", "content": "question 2"}


def test_new_clears_history(claude, ali):
    claude.replies.append(("ok", "end_turn"))
    handle_message(ali, "hello")
    assert handle_message(ali, "New") == MESSAGES["cleared"]["en"]
    assert bot.users[ali]["history"] == []
    assert handle_message(ali, "جديد") == MESSAGES["cleared"]["ar"]


def test_paused_search_is_continued(claude, ali):
    claude.replies += [("", "pause_turn"), ("Open until 10pm.", "end_turn")]
    assert handle_message(ali, "is the mall open?") == "Open until 10pm."
    second = claude.requests[1]["messages"]
    assert second[-1]["role"] == "assistant"  # the paused turn is sent back


def test_refusal_sends_the_error_message(claude, ali):
    claude.replies.append(("", "refusal"))
    assert handle_message(ali, "something") == MESSAGES["error"]["en"]
    assert bot.users[ali]["history"] == []


def test_api_error_sends_the_error_message(claude, ali):
    claude.replies.append(529)
    assert handle_message(ali, "سؤال") == MESSAGES["error"]["ar"]


def test_network_error_sends_the_error_message(claude, ali):
    claude.replies.append(httpx2.ConnectError("no route"))
    assert handle_message(ali, "question") == MESSAGES["error"]["en"]


def test_daily_limit(claude, ali):
    bot.users[ali]["count"] = DAILY_LIMIT - 1
    claude.replies.append(("last answer", "end_turn"))
    assert handle_message(ali, "question 20") == "last answer"
    assert handle_message(ali, "question 21") == MESSAGES["limit"]["en"]
    assert handle_message(ali, "question 22") is None


def test_daily_limit_resets_the_next_day(claude, ali):
    bot.users[ali]["count"] = DAILY_LIMIT + 5
    bot.users[ali]["day"] = "2000-01-01"
    claude.replies.append(("fresh day", "end_turn"))
    assert handle_message(ali, "hello again") == "fresh day"
