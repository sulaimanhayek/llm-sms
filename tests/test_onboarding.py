import json

import bot
from bot import MESSAGES, handle_message


def test_first_text_gets_the_welcome():
    assert handle_message("+1", "hi") == MESSAGES["welcome"]["en"]


def test_first_text_in_arabic_gets_the_arabic_welcome():
    assert handle_message("+1", "مرحبا") == MESSAGES["welcome"]["ar"]


def test_empty_text_gets_no_reply():
    assert handle_message("+1", "   ") is None
    assert "+1" not in bot.users


def test_profile_needs_four_parts():
    handle_message("+1", "hi")
    assert handle_message("+1", "Ali Hassan Basra") == MESSAGES["retry"]["en"]
    assert bot.users["+1"]["step"] == "profile"


def test_profile_is_saved():
    handle_message("+1", "hi")
    reply = handle_message("+1", " Ali , Hassan, Basra ,Iraq ")
    assert reply == "Thanks Ali! Ask me anything. Send NEW to start a fresh conversation."
    user = bot.users["+1"]
    assert [user["first_name"], user["last_name"], user["city"], user["country"]] == ["Ali", "Hassan", "Basra", "Iraq"]
    assert user["step"] == "ready"


def test_profile_with_arabic_commas():
    handle_message("+1", "مرحبا")
    reply = handle_message("+1", "علي، حسن، البصرة، العراق")
    assert reply == "شكراً علي! اسألني أي سؤال. أرسل جديد لبدء محادثة جديدة."
    assert bot.users["+1"]["city"] == "البصرة"


def test_profile_on_separate_lines():
    handle_message("+1", "hi")
    handle_message("+1", "Ali\nHassan\nBasra\nIraq")
    assert bot.users["+1"]["country"] == "Iraq"


def test_long_profile_values_are_capped():
    handle_message("+1", "hi")
    handle_message("+1", "A" * 500 + ", Hassan, Basra, Iraq")
    assert len(bot.users["+1"]["first_name"]) == 40


def test_users_are_saved_to_file():
    handle_message("+1", "hi")
    handle_message("+1", "علي، حسن، البصرة، العراق")
    with open(bot.USERS_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["+1"]["first_name"] == "علي"


def test_users_file_is_read_back():
    handle_message("+1", "hi")
    assert bot.load_users() == bot.users
