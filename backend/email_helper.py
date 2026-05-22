"""Email sending helper.

Provider-agnostic: defaults to plain SMTP (Gmail / Porkbun / etc) when
SMTP_HOST + SMTP_USER + SMTP_PASS are configured. Falls back to a
no-op "logged but not sent" mode if no credentials are set, so dev
environments don't crash.

Env vars:
  SMTP_HOST       e.g. smtp.gmail.com
  SMTP_PORT       e.g. 587 (STARTTLS) or 465 (SSL)
  SMTP_USER       full SMTP username (often the Gmail address)
  SMTP_PASS       Gmail "app password" (NOT your normal password)
  FROM_EMAIL      Display From, e.g. "LocalDrift <hello@localdrift.app>"
                  If sending via Gmail SMTP, set up "Send mail as" in
                  Gmail settings so the From: header isn't rewritten.
  ADMIN_NOTIFY_EMAIL  Optional. Recipient for admin-only notifications
                  (new community-source submission, new report, new
                  feedback). If unset, notify_admin is a no-op.

For higher volume / better deliverability later, swap this module out
for Resend or SendGrid — `send_email` is the only public surface.
"""
from __future__ import annotations

import os
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger(__name__)


def _smtp_config() -> Optional[dict]:
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    if not (host and user and password):
        return None
    return {
        "host": host,
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": user,
        "password": password,
        "from_email": os.environ.get("FROM_EMAIL") or user,
    }


def send_email(to: str, subject: str, html: str, text_fallback: str = "") -> bool:
    """Send a single email. Returns True if dispatched, False if not
    configured / failed. Errors are logged, not raised — callers should
    decide whether to retry."""
    cfg = _smtp_config()
    if not cfg:
        logger.warning("send_email skipped (SMTP not configured): to=%s subject=%s", to, subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_email"]
    msg["To"] = to
    if text_fallback:
        msg.set_content(text_fallback)
    else:
        # Crude HTML -> text fallback so non-HTML clients still see something
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        msg.set_content(text or "(see HTML version)")
    msg.add_alternative(html, subtype="html")

    try:
        ctx = ssl.create_default_context()
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx, timeout=15) as s:
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
                s.starttls(context=ctx)
                s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        return True
    except Exception as e:
        logger.error("send_email failed: to=%s err=%s", to, e)
        return False


def notify_admin(subject: str, html: str, text_fallback: str = "") -> bool:
    """Fire-and-forget notification to the admin recipient. Used for
    things like "a new community source was submitted" or "abuse
    reported." Reads ADMIN_NOTIFY_EMAIL from env; no-ops if unset so
    we never block a user's submission on missing config.

    Always returns the result for tests/logging — callers should NOT
    raise on a False return. Treat it like print() that may not print."""
    recipient = os.environ.get("ADMIN_NOTIFY_EMAIL", "").strip()
    if not recipient:
        return False
    try:
        return send_email(recipient, subject, html, text_fallback=text_fallback)
    except Exception as e:
        # Defensive — send_email already swallows internal errors, but
        # this protects callers from any unexpected exception in the
        # path (DNS, env-var manipulation, etc.).
        logger.error("notify_admin failed: subject=%s err=%s", subject, e)
        return False
