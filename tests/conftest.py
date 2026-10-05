"""Shared test setup. No test talks to the real Claude API or to Twilio."""

import json
import os

import anthropic
import httpx2
import pytest

# app.py reads these when it is imported. Fake values: Twilio is never called.
os.environ["TWILIO_ACCOUNT_SID"] = "AC" + "0" * 32
os.environ["TWILIO_AUTH_TOKEN"] = "test-token"
os.environ["TWILIO_NUMBER"] = "+15550001111"
os.environ["PUBLIC_URL"] = "https://example.ngrok.app"

import bot  # noqa: E402  (must come after the environment is set)


class FakeClaude:
    """Stands in for the Claude API.

    Add what the API should return to `replies`, one per request:
      ("some text", "end_turn")   a normal answer (or another stop_reason)
      529                         an HTTP error status
      httpx2.ConnectError("x")    a network failure
    Every request body is saved in `requests`, its headers in `headers`.
    """

    def __init__(self):
        self.replies = []
        self.requests = []
        self.headers = []

    def handle(self, request):
        self.requests.append(json.loads(request.content))
        self.headers.append(request.headers)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            error = {"type": "error", "error": {"type": "api_error", "message": "test error"}}
            return httpx2.Response(reply, json=error)
        text, stop_reason = reply
        message = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": bot.MODEL,
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        return httpx2.Response(200, json=message)


@pytest.fixture(autouse=True)
def fresh_users(tmp_path, monkeypatch):
    """Every test starts with no users, saved to a temp file."""
    monkeypatch.setattr(bot, "USERS_FILE", str(tmp_path / "users.json"))
    bot.users.clear()
    yield
    bot.users.clear()


@pytest.fixture
def claude(monkeypatch):
    """Swap bot.client for a real SDK client wired to FakeClaude.

    The real SDK still builds the request, so tests check the actual JSON
    that would be sent to the API.
    """
    fake = FakeClaude()
    http_client = httpx2.Client(transport=httpx2.MockTransport(fake.handle))
    client = anthropic.Anthropic(api_key="test-key", max_retries=0, http_client=http_client)
    monkeypatch.setattr(bot, "client", client)
    yield fake
    assert fake.replies == [], "a test queued replies that were never requested"


@pytest.fixture
def ali():
    """A phone number that has finished onboarding."""
    bot.handle_message("+9647700000001", "hi")
    bot.handle_message("+9647700000001", "Ali, Hassan, Basra, Iraq")
    return "+9647700000001"
