from bot import UNICODE_LIMIT, GSM_LIMIT, clean, is_gsm, shorten, sms_length, sms_limit


def test_plain_english_is_gsm():
    assert is_gsm("Take bus 7 from Saad Square, 2,000 IQD.")
    assert sms_limit("hello") == GSM_LIMIT


def test_arabic_is_unicode():
    assert not is_gsm("مرحبا")
    assert sms_limit("مرحبا") == UNICODE_LIMIT


def test_one_arabic_letter_makes_the_whole_message_unicode():
    assert sms_limit("hello " * 20 + "ب") == UNICODE_LIMIT


def test_gsm_extension_characters_count_twice():
    assert sms_length("a{b}") == 6
    assert sms_length("5€") == 3


def test_emoji_counts_as_two_unicode_units():
    assert sms_length("😀") == 2


def test_clean_swaps_characters_that_would_force_unicode():
    assert clean("It’s “open” – 25°C… → left") == "It's \"open\" - 25C... -> left"
    assert is_gsm(clean("It’s “open” – 25°C… → left"))


def test_clean_removes_markdown_bold():
    assert clean("**Masgouf** is grilled carp") == "Masgouf is grilled carp"


def test_shorten_leaves_short_text_alone():
    assert shorten("Turn left at the mosque.") == "Turn left at the mosque."


def test_shorten_cuts_long_english_at_a_word():
    text = shorten("word " * 200)
    assert sms_length(text) <= GSM_LIMIT
    assert text.endswith("word...")


def test_shorten_cuts_long_arabic_to_the_unicode_limit():
    text = shorten("كلمة " * 100)
    assert sms_length(text) <= UNICODE_LIMIT
    assert text.endswith("...")


def test_shorten_handles_one_huge_word():
    assert sms_length(shorten("a" * 1000)) <= GSM_LIMIT
