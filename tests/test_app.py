import pytest

import app
import bot
from bot import MESSAGES


class FakeTwilio:
    """Records texts instead of sending them."""

    def __init__(self):
        self.sent = []
        self.messages = self

    def create(self, to, from_, body):
        self.sent.append({"to": to, "from": from_, "body": body})


@pytest.fixture
def twilio(monkeypatch):
    fake = FakeTwilio()
    monkeypatch.setattr(app, "twilio", fake)
    return fake


def post_sms(phone, body, signature=None):
    """Send a request to /sms the way Twilio would, signed unless told otherwise."""
    form = {"From": phone, "To": app.TWILIO_NUMBER, "Body": body}
    if signature is None:
        signature = app.validator.compute_signature(app.PUBLIC_URL + "/sms", form)
    response = app.app.test_client().post("/sms", data=form, headers={"X-Twilio-Signature": signature})
    app.inbox.join()  # wait for the worker to finish
    return response


def test_unsigned_request_is_rejected(twilio):
    response = post_sms("+1", "hi", signature="forged")
    assert response.status_code == 403
    assert twilio.sent == []
    assert bot.users == {}


def test_twilio_gets_an_empty_answer_and_the_reply_is_texted(twilio):
    response = post_sms("+1", "hi")
    assert response.status_code == 200
    assert response.mimetype == "text/xml"
    assert response.data == b"<Response></Response>"
    assert twilio.sent == [{"to": "+1", "from": app.TWILIO_NUMBER, "body": MESSAGES["welcome"]["en"]}]


def test_stop_is_left_to_twilio(twilio):
    post_sms("+1", " Stop ")
    assert twilio.sent == []
    assert bot.users == {}


def test_no_text_is_sent_when_the_bot_stays_silent(twilio):
    post_sms("+1", "   ")
    assert twilio.sent == []


def test_worker_keeps_going_after_an_error(twilio, monkeypatch):
    def broken(phone, text):
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "handle_message", broken)
    post_sms("+1", "hi")
    assert twilio.sent == []

    monkeypatch.setattr(app, "handle_message", bot.handle_message)
    post_sms("+2", "hi")
    assert twilio.sent[-1]["to"] == "+2"
