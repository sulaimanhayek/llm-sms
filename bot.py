"""The brain of the SMS bot: onboarding, SMS length rules, and asking Claude.

Run this file directly to chat with the bot in your terminal (no SMS needed):
    python bot.py
"""

import json
import os
from datetime import date

import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(timeout=90)

MODEL = "claude-opus-5-5"
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
PROFILE_FIELDS = ["first_name", "last_name", "city", "country"]
DAILY_LIMIT = 20  # messages per phone number per day
HISTORY_LENGTH = 6  # last 3 questions + 3 answers are sent to Claude

# --- SMS length rules ------------------------------------------------------
# An SMS is 160 characters if every character is in the GSM alphabet below.
# One character outside it (Arabic, emoji, curly quotes) switches the whole
# message to Unicode, and the limit drops to 70.
# Longer messages are split into parts of 153 (GSM) or 67 (Unicode).
# We allow 2 parts per reply:
GSM_LIMIT = 306  # 2 x 153
UNICODE_LIMIT = 134  # 2 x 67

GSM_CHARS = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM_EXTRA_CHARS = "^{}\\[~]|€"  # allowed, but each one counts as 2

# Common characters that would force Unicode, and plain replacements for them.
REPLACEMENTS = {
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "•": "-", "…": "...", "→": "->", "°": "",
    "\u00a0": " ", "**": "", "##": "",
}


def clean(text):
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.strip()


def is_gsm(text):
    return all(ch in GSM_CHARS or ch in GSM_EXTRA_CHARS for ch in text)


def is_arabic(text):
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def sms_length(text):
    if is_gsm(text):
        return len(text) + sum(1 for ch in text if ch in GSM_EXTRA_CHARS)
    return len(text.encode("utf-16-le")) // 2  # Unicode SMS counts UTF-16 units


def sms_limit(text):
    return GSM_LIMIT if is_gsm(text) else UNICODE_LIMIT


def shorten(text):
    """Drop words from the end until the text fits in the SMS limit."""
    limit = sms_limit(text)
    if sms_length(text) <= limit:
        return text
    words = text.split(" ")
    while len(words) > 1 and sms_length(" ".join(words) + "...") > limit:
        words.pop()
    return (" ".join(words) + "...")[:limit]


# --- Fixed replies (no Claude needed) -----------------------------------------
MESSAGES = {
    "welcome": {
        "en": "Welcome! Reply with: first name, last name, city, country. Example: Ali, Hassan, Basra, Iraq",
        "ar": "أهلاً! أرسل: الاسم الأول، اسم العائلة، المدينة، البلد. مثال: علي، حسن، البصرة، العراق",
    },
    "retry": {
        "en": "Please send 4 parts separated by commas. Example: Ali, Hassan, Basra, Iraq",
        "ar": "أرسل ٤ أجزاء مفصولة بفواصل. مثال: علي، حسن، البصرة، العراق",
    },
    "thanks": {
        "en": "Thanks {name}! Ask me anything. Send NEW to start a fresh conversation.",
        "ar": "شكراً {name}! اسألني أي سؤال. أرسل جديد لبدء محادثة جديدة.",
    },
    "cleared": {
        "en": "Done. Ask your next question.",
        "ar": "تم. اسأل سؤالك التالي.",
    },
    "limit": {
        "en": "Daily limit reached. Try again tomorrow.",
        "ar": "وصلت للحد اليومي. حاول غداً.",
    },
    "error": {
        "en": "Sorry, I couldn't answer that. Try again or ask differently.",
        "ar": "عذراً، لم أستطع الإجابة. حاول مرة أخرى أو اسأل بطريقة أخرى.",
    },
}

# --- Users (saved to users.json so a restart doesn't forget anyone) ------------


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_users():
    # Write to a temp file first, so a crash mid-write can't corrupt users.json.
    temp_file = USERS_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, USERS_FILE)


users = load_users()

# --- Claude ---------------------------------------------------------------------
SYSTEM_PROMPT = """You answer questions by SMS for people who have little or no internet.

The user is {first_name} {last_name}, from {city}, {country}. They may be somewhere else if they say so.

Rules:
- Your whole reply must be under {max_chars} characters. This is a hard limit.
- Reply in the language the user writes in.
- Plain text only: no markdown, no lists with symbols, no emoji, no links (they can't open them).
- Lead with the answer. No greetings, no filler, no follow-up offers.
- Give one solid answer, not a list of options, unless they ask for options.
- For directions, use landmarks and main roads. Say so if you are not sure.
- If you don't know, say so briefly. Never invent places, phone numbers or facts.
- Use web search for anything current or local: places, opening hours, prices, news, weather."""


def ask_claude(user, question):
    # Leave a margin under the real limit: models can't count characters exactly.
    max_chars = sms_limit(clean(question)) - 30
    system = SYSTEM_PROMPT.format(
        first_name=user["first_name"],
        last_name=user["last_name"],
        city=user["city"],
        country=user["country"],
        max_chars=max_chars,
    )
    messages = user["history"] + [{"role": "user", "content": question}]
    web_search = {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 3,
        "user_location": {"type": "approximate", "city": user["city"]},
    }

    # A long web search can pause mid-answer ("pause_turn"). Sending the paused
    # answer back makes the API carry on from where it stopped.
    for attempt in range(3):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=system,
            messages=messages,
            tools=[web_search],
            output_config={"effort": "low"},  # low = faster, shorter thinking
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # if Claude declines, retry on a fallback model
        )
        if response.stop_reason != "pause_turn":
            break
        messages = messages + [{"role": "assistant", "content": response.content}]

    if response.stop_reason == "refusal":
        return ""
    return "".join(block.text for block in response.content if block.type == "text")


# --- The one function the SMS gateway calls ----------------------------------------


def handle_message(phone, text):
    """Take an incoming SMS, return the reply text (or None to send nothing)."""
    text = text.strip()
    if not text:
        return None
    lang = "ar" if is_arabic(text) else "en"

    # 1. New number: create their record and ask for their details.
    if phone not in users:
        users[phone] = {"step": "profile", "day": "", "count": 0, "history": []}
        save_users()
        return MESSAGES["welcome"][lang]

    user = users[phone]

    # 2. Daily limit. Tell them once, then stay silent (every SMS costs money).
    today = date.today().isoformat()
    if user["day"] != today:
        user["day"] = today
        user["count"] = 0
    user["count"] += 1
    save_users()
    if user["count"] == DAILY_LIMIT + 1:
        return MESSAGES["limit"][lang]
    if user["count"] > DAILY_LIMIT + 1:
        return None

    # 3. Onboarding: expect "first name, last name, city, country".
    if user["step"] == "profile":
        parts = text.replace("،", ",").replace("\n", ",").split(",")
        parts = [part.strip() for part in parts if part.strip()]
        if len(parts) != len(PROFILE_FIELDS):
            return MESSAGES["retry"][lang]
        for field, value in zip(PROFILE_FIELDS, parts):
            user[field] = value[:40]  # cap length: this text goes into the prompt
        user["step"] = "ready"
        save_users()
        return MESSAGES["thanks"][lang].format(name=user["first_name"])

    # 4. Commands.
    if text.upper() in ("NEW", "جديد"):
        user["history"] = []
        save_users()
        return MESSAGES["cleared"][lang]

    # 5. A real question: ask Claude.
    try:
        answer = ask_claude(user, text)
    except anthropic.APIConnectionError:
        print("Could not reach Claude (network or timeout)")
        return MESSAGES["error"][lang]
    except anthropic.APIStatusError as e:
        print(f"Claude API error {e.status_code}: {e.message}")
        return MESSAGES["error"][lang]

    answer = shorten(clean(answer))
    if not answer:
        return MESSAGES["error"][lang]

    user["history"] = user["history"] + [
        {"role": "user", "content": text},
        {"role": "assistant", "content": answer},
    ]
    user["history"] = user["history"][-HISTORY_LENGTH:]
    save_users()
    return answer


# --- Terminal simulator --------------------------------------------------------------

if __name__ == "__main__":
    print("SMS simulator. Type  <phone>: <message>   e.g.  07701234567: hi")
    print("Ctrl+C to quit.\n")
    while True:
        line = input("> ")
        if ": " not in line:
            print("Format:  <phone>: <message>")
            continue
        phone, text = line.split(": ", 1)
        reply = handle_message(phone.strip(), text)
        if reply is None:
            print("(no reply sent)\n")
        else:
            print(f"[to {phone}] {reply}")
            print(f"({sms_length(reply)} chars, limit {sms_limit(reply)})\n")
