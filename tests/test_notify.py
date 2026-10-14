import asyncio
import json

import httpx

from monitor import notify


def telegram(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return notify.TelegramNotifier("SECRET-TOKEN", "42", client=client)


def test_telegram_payload():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    assert asyncio.run(telegram(handler).send("hello")) is True
    assert seen["url"] == "https://api.telegram.org/botSECRET-TOKEN/sendMessage"
    assert seen["body"]["chat_id"] == "42" and seen["body"]["parse_mode"] == "HTML"


def test_long_messages_are_truncated():
    seen = {}

    def handler(request):
        seen["text"] = json.loads(request.content)["text"]
        return httpx.Response(200)

    asyncio.run(telegram(handler).send("x" * 9000))
    assert len(seen["text"]) <= notify.TELEGRAM_LIMIT


def test_http_error_returns_false_and_never_logs_the_token(caplog):
    caplog.set_level("DEBUG")
    assert asyncio.run(telegram(lambda r: httpx.Response(400)).send("hi")) is False

    def broken(request):
        raise httpx.ConnectError("no route", request=request)

    assert asyncio.run(telegram(broken).send("hi")) is False
    assert "SECRET-TOKEN" not in caplog.text


def test_notifier_selection(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert isinstance(notify.get_notifier(), notify.LogNotifier)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    assert isinstance(notify.get_notifier(), notify.TelegramNotifier)
    assert asyncio.run(notify.LogNotifier().send("x")) is False


def test_model_text_is_html_escaped():
    brief = {"headline": "<b>bold</b> & more", "summary": "a < b", "stance": "bullish",
             "confidence": "high", "key_points": ["<script>"], "risks": []}
    text = notify.format_verified_alert(ticker="X", name="X <Corp>", brief=brief, signal_line="s")
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert "&lt;b&gt;bold&lt;/b&gt;" in text and "X &lt;Corp&gt;" in text
