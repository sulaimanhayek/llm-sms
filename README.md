# llm-sms

Ask Claude anything by plain SMS. The phone needs no internet.

Built for places where mobile data is bad or expensive, starting with Iraq: directions, school questions, everyday questions. Answers are short, solid, and fit in two text messages.

```
phone --SMS--> Twilio number --webhook--> app.py --> bot.py --> Claude (+ web search)
phone <--SMS-- Twilio number <---API----- app.py <-----------------'
```

## What the person texting sees

1. **First text from a new number:** the bot asks for first name, last name, city, country, e.g. `Ali, Hassan, Basra, Iraq`. Arabic works too: `علي، حسن، البصرة، العراق`.
2. **After that, every text is a question.** Claude answers in the same language and uses the profile for local context. It searches the web for anything current or local (places, prices, hours, weather).
3. **`NEW`** (or `جديد`) starts a fresh conversation. Otherwise the bot remembers the last 3 questions and answers.
4. **20 messages per number per day.** Then one "daily limit" text, then silence until tomorrow.

### Why replies are so short

One SMS holds 160 English characters but only 70 Arabic ones (any non-Latin character switches the whole message to Unicode). Replies are capped at 2 messages:

| Reply language | Limit |
|---|---|
| English / Latin | 306 characters |
| Arabic | 134 characters |

Claude is told the limit, and `bot.py` cuts anything still too long. It also swaps characters that would silently force Unicode (curly quotes, long dashes, `°`) for plain ones.

## Run it in your terminal (no SMS, no Twilio)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then add your ANTHROPIC_API_KEY
python bot.py
```

Type `<phone>: <message>`, for example `07701234567: hi`. Each reply shows its SMS length.

## Connect a real phone number (Twilio)

1. Create a Twilio account and buy a UK or US number with SMS.
2. Fill in the Twilio values in `.env`.
3. Open a tunnel so Twilio can reach your machine: `ngrok http 8000`. Put the `https://...` address in `PUBLIC_URL`.
4. Start the server: `python app.py`
5. In the Twilio console: Phone Numbers → your number → Messaging → "A message comes in" → Webhook → `https://<your-ngrok-address>/sms`, HTTP POST.
6. Text the number.

On a Twilio trial account you can only text numbers you have verified, and every reply starts with "Sent from your Twilio trial account", which uses up part of the length.

## Known issue: Iraq

Twilio has no Iraqi numbers and no two-way SMS in Iraq. With a UK/US number, people in Iraq pay international SMS rates to text it, and Iraqi carriers may not deliver the replies (Asiacell blocks unregistered international senders).

The planned fix is an Android phone with a local Iraqi SIM acting as the gateway (for example [android-sms-gateway](https://github.com/capcom6/android-sms-gateway)). Only `app.py` changes for that; `bot.py` stays the same.

## Files

- `bot.py` handles the conversation: onboarding, SMS length rules, the daily limit and the Claude call. Run it directly for the terminal simulator.
- `app.py` is the Twilio webhook. It receives texts and sends replies from a background worker (Twilio times out after 15 seconds, and Claude with web search can take longer).
- `users.json` is created at runtime. It holds phone numbers, names and recent messages, so it is private and stays out of git.

## Claude settings

- Model `claude-opus-5-5` with `effort: low` for fast, short answers.
- Web search on, up to 3 searches per question, located at the user's city.
- `fallbacks="default"`: if Claude declines a question, the API retries it on a fallback model instead of returning nothing.
