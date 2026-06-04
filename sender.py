import base64
import json
import random
import time
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CONFIG_PATH = Path(__file__).parent / "config.yml"
ACCOUNTS_PATH = Path(__file__).parent / "accounts.yml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

SENT_LOG_PATH = Path(__file__).parent / config["paths"]["sent_log"]

_sent_this_hour = 0
_sent_today = 0
_hour_window_start = time.time()
_day_window_start = time.time()


def _random_delay():
    rl = config["rate_limits"]
    return random.uniform(rl["min_delay_seconds"], rl["max_delay_seconds"])


def _already_sent(email):
    if not SENT_LOG_PATH.exists():
        return False
    return email in SENT_LOG_PATH.read_text()


def _log_sent(target, subject):
    entry = json.dumps({
        "email": target["email"],
        "name": target.get("name"),
        "company": target.get("company"),
        "subject": subject,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    })
    with open(SENT_LOG_PATH, "a") as f:
        f.write(entry + "\n")


def _get_gmail_client():
    with open(ACCOUNTS_PATH) as f:
        accounts = yaml.safe_load(f)
    gmail = accounts.get("gmail", {})

    if not all([gmail.get("client_id"), gmail.get("client_secret"), gmail.get("refresh_token")]):
        raise RuntimeError("Gmail not configured. Run: python auth.py")

    creds = Credentials(
        token=None,
        refresh_token=gmail["refresh_token"],
        client_id=gmail["client_id"],
        client_secret=gmail["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _check_rate_limits():
    global _sent_this_hour, _sent_today, _hour_window_start, _day_window_start
    now = time.time()

    if now - _hour_window_start > 3600:
        _sent_this_hour = 0
        _hour_window_start = now

    if now - _day_window_start > 86400:
        _sent_today = 0
        _day_window_start = now

    rl = config["rate_limits"]

    if _sent_this_hour >= rl["emails_per_hour"]:
        wait_min = (3600 - (now - _hour_window_start)) / 60
        print(f"[sender] Hourly limit reached. Next window in {wait_min:.0f} min")
        return False

    if _sent_today >= rl["emails_per_day"]:
        print(f"[sender] Daily limit reached ({_sent_today}/{rl['emails_per_day']})")
        return False

    return True


def send_email(target, subject, body):
    global _sent_this_hour, _sent_today

    if not _check_rate_limits():
        return False

    if _already_sent(target["email"]):
        print(f"[sender] Skipping {target['email']} — already in sent.log")
        return False

    try:
        service = _get_gmail_client()
        with open(ACCOUNTS_PATH) as f:
            _accs = yaml.safe_load(f)
        sender_cfg = _accs.get("sender", {})
        resume_pdf = target.get("resume_pdf")

        msg = MIMEMultipart()
        msg["From"] = f"{sender_cfg['name']} <{sender_cfg['email']}>"
        msg["To"] = target["email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if resume_pdf and Path(resume_pdf).exists():
            with open(resume_pdf, "rb") as f:
                pdf_part = MIMEApplication(f.read(), _subtype="pdf")
                pdf_part.add_header(
                    "Content-Disposition", "attachment", filename=Path(resume_pdf).name
                )
                msg.attach(pdf_part)
        elif resume_pdf:
            print(f"[sender] Warning: PDF not found at {resume_pdf} — sending without attachment")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

        _log_sent(target, subject)
        _sent_this_hour += 1
        _sent_today += 1

        attachment_note = (
            f" + PDF ({Path(resume_pdf).name})"
            if resume_pdf and Path(resume_pdf).exists()
            else ""
        )
        print(f"[sender] Sent to {target.get('name')} <{target['email']}> ({target.get('company')}){attachment_note}")
        return True
    except Exception as e:
        print(f"[sender] Failed to send to {target['email']}: {e}")
        return False


def send_batch(targets, generate_email_fn):
    sent = 0
    for target in targets:
        if not _check_rate_limits():
            print(f"[sender] Rate limit hit — stopping batch after {sent} sent")
            break

        email = generate_email_fn(target)
        if not email:
            print(f"[sender] No email generated for {target['email']} — skipping")
            continue

        if send_email(target, email["subject"], email["body"]):
            sent += 1
            delay = _random_delay()
            print(f"[sender] Waiting {delay:.0f}s before next send...")
            time.sleep(delay)

    print(f"[sender] Batch complete. Sent {sent} emails.")
    return sent


def print_sent_summary():
    if not SENT_LOG_PATH.exists():
        print("[sender] No emails sent yet (sent.log not found)")
        return

    lines = [l for l in SENT_LOG_PATH.read_text().splitlines() if l.strip()]
    print(f"\n[sent log] {len(lines)} emails sent total")

    for line in lines[-10:]:
        try:
            entry = json.loads(line)
            print(f"  {entry['sent_at']} → {entry['email']} ({entry.get('company')})")
        except Exception:
            print("  [unparseable entry]")
