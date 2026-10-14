"""Alert delivery. Telegram when configured, otherwise a log-only fallback."""
import html
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# httpx logs every request URL at INFO, and Telegram's URL contains the bot token.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

TELEGRAM_LIMIT = 4000  # API hard limit is 4096 characters


class LogNotifier:
    """Used when Telegram is not configured, so the pipeline still runs end to end."""

    async def send(self, text: str) -> bool:
        logger.info("ALERT (not delivered, Telegram not configured):\n%s", text)
        return False


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, client: httpx.AsyncClient | None = None):
        self.token = token
        self.chat_id = chat_id
        self._client = client

    async def send(self, text: str) -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": text[:TELEGRAM_LIMIT],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            if self._client is not None:
                resp = await self._client.post(url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                # Never log the URL: it contains the bot token.
                logger.error("Telegram send failed with status %s", resp.status_code)
                return False
            return True
        except httpx.HTTPError as exc:
            logger.error("Telegram send failed: %s", type(exc).__name__)
            return False


def get_notifier():
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return TelegramNotifier(token, chat_id)
    return LogNotifier()


def _e(value) -> str:
    return html.escape(str(value), quote=False)


def format_verified_alert(*, ticker: str, name: str | None, brief: dict, signal_line: str) -> str:
    title = f"{ticker} - {name}" if name else ticker
    lines = [f"<b>{_e(title)}</b>", _e(brief["headline"]), "", _e(brief["summary"])]
    if brief.get("key_points"):
        lines.append("")
        lines += [f"• {_e(p)}" for p in brief["key_points"]]
    if brief.get("risks"):
        lines.append("")
        lines.append("<b>Risks</b>")
        lines += [f"• {_e(r)}" for r in brief["risks"]]
    lines += [
        "",
        f"Stance: <b>{_e(brief['stance'])}</b> ({_e(brief['confidence'])} confidence) - checked against data",
        f"<i>{_e(signal_line)}</i>",
        "Not investment advice.",
    ]
    return "\n".join(lines)


def format_unverified_alert(*, ticker: str, name: str | None, signal_line: str, reason: str) -> str:
    """Signals only. Nothing the model wrote is included because it did not pass the critic."""
    title = f"{ticker} - {name}" if name else ticker
    return "\n".join([
        f"<b>{_e(title)}</b>",
        f"<i>{_e(signal_line)}</i>",
        "",
        f"Automated analysis could not be verified ({_e(reason)}), so it was withheld. "
        "Check the figures yourself before acting.",
    ])
