"""The SMS gateway: Twilio sends incoming texts here, we text the reply back.

Run:  python app.py   (then expose port 8000 with ngrok, see README)
"""

import os
import queue
import threading

from dotenv import load_dotenv
from flask import Flask, Response, request
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from bot import handle_message

load_dotenv()
TWILIO_NUMBER = os.environ["TWILIO_NUMBER"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")  # e.g. https://abc123.ngrok.app

twilio = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
inbox = queue.Queue()
app = Flask(__name__)

# Twilio answers these itself (and blocks texts to anyone who sent STOP),
# so don't spend a Claude call on them.
TWILIO_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "OPTOUT", "REVOKE"}


@app.post("/sms")
def incoming_sms():
    # Only accept requests that really come from Twilio (signed with our token).
    signature = request.headers.get("X-Twilio-Signature", "")
    if not validator.validate(PUBLIC_URL + "/sms", request.form, signature):
        return "Forbidden", 403

    # Twilio gives up after 15 seconds, and Claude can take longer than that.
    # So: put the message in the inbox, tell Twilio "got it" straight away
    # (an empty <Response> sends no SMS), and the worker replies later.
    body = request.form.get("Body", "")
    if body.strip().upper() not in TWILIO_KEYWORDS:
        inbox.put((request.form["From"], body))
    return Response("<Response></Response>", mimetype="text/xml")


def worker():
    # One message at a time, so two messages never change users.json at once.
    while True:
        phone, text = inbox.get()
        try:
            reply = handle_message(phone, text)
            if reply:
                twilio.messages.create(to=phone, from_=TWILIO_NUMBER, body=reply)
        except Exception as e:  # never let one bad message stop the worker
            print(f"Failed to handle message from {phone}: {e!r}")
        inbox.task_done()


threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    app.run(port=8000)  # not 5000: macOS uses that port for AirPlay
