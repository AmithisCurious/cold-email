"""
Main service — orchestrates scraping, generation, and sending.

Usage:
  python service.py           — run once now
  python service.py --cron    — start persistent cron daemon (runs daily at 9am)
  python service.py --status  — print account usage and sent log summary

Modes:
  Role-aware  — if cold-email-queue.json exists, uses it (role + resume PDF per company)
  Generic     — falls back to companies.json or built-in default list
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule
import yaml

from email_gen import check_llm, generate_email
from rotate import print_status
from scraper import scrape
from sender import print_sent_summary, send_batch

CONFIG_PATH = Path(__file__).parent / "config.yml"
QUEUE_PATH = Path(__file__).parent / "cold-email-queue.json"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

DEFAULT_COMPANIES = [
    {"name": "Sarvam AI", "url": "https://www.sarvam.ai"},
    {"name": "Krutrim", "url": "https://krutrim.com"},
    {"name": "Yellow.ai", "url": "https://yellow.ai"},
    {"name": "Haptik", "url": "https://haptik.ai"},
    {"name": "Vernacular.ai", "url": "https://vernacular.ai"},
    {"name": "Observe.AI", "url": "https://observe.ai"},
    {"name": "Mihup", "url": "https://mihup.com"},
    {"name": "Slang Labs", "url": "https://slanglabs.in"},
    {"name": "Gnani.ai", "url": "https://gnani.ai"},
    {"name": "Leena AI", "url": "https://leena.ai"},
    {"name": "Sprinklr", "url": "https://sprinklr.com"},
    {"name": "Freshworks", "url": "https://freshworks.com"},
    {"name": "Fractal Analytics", "url": "https://fractal.ai"},
    {"name": "Sigmoid", "url": "https://sigmoid.com"},
    {"name": "Postman", "url": "https://postman.com"},
    {"name": "Razorpay", "url": "https://razorpay.com"},
    {"name": "BrowserStack", "url": "https://browserstack.com"},
    {"name": "Darwinbox", "url": "https://darwinbox.com"},
    {"name": "Juspay", "url": "https://juspay.in"},
    {"name": "Mindtickle", "url": "https://mindtickle.com"},
]


def load_queue():
    """Load role-aware queue from career-ops. Returns list of queue entries."""
    if not QUEUE_PATH.exists():
        return None
    with open(QUEUE_PATH) as f:
        queue = json.load(f)
    print(f"[service] Loaded {len(queue)} entries from cold-email-queue.json (role-aware mode)")
    return queue


def queue_to_scraper_targets(queue):
    """Convert queue entries to the format scrape() expects."""
    return [
        {
            "name": entry["company"],
            "url": entry.get("company_url", ""),
            "role": entry.get("role", ""),
            "role_url": entry.get("role_url", ""),
            "resume_pdf": entry.get("resume_pdf", ""),
            "notes": entry.get("notes", ""),
        }
        for entry in queue
    ]


def load_companies():
    """Load generic company list (fallback when no queue file)."""
    companies_path = Path(__file__).parent / "companies.json"
    if companies_path.exists():
        with open(companies_path) as f:
            companies = json.load(f)
        print(f"[service] Loaded {len(companies)} companies from companies.json")
        return companies
    print(f"[service] Using {len(DEFAULT_COMPANIES)} default companies")
    return DEFAULT_COMPANIES


def run():
    print(f"\n[service] Starting run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not check_llm():
        print("[service] LLM unavailable — aborting run. Fix Ollama and retry.")
        return

    queue = load_queue()
    if queue:
        print("[service] Role-aware mode: scraping contacts for queued roles...")
        targets = queue_to_scraper_targets(queue)
    else:
        print("[service] Generic mode: no cold-email-queue.json found, using company list...")
        targets = load_companies()

    new_targets = scrape(targets)

    if not new_targets:
        print("[service] No new targets found. Done.")
        return

    print(f"[service] {len(new_targets)} new targets. Starting email generation + send...")
    sent = send_batch(new_targets, generate_email)
    print(f"[service] Run complete. {sent}/{len(new_targets)} emails sent.")


def print_status_summary():
    print("\n=== Account Status ===")
    print_status()
    print("\n=== Send Log ===")
    print_sent_summary()


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--status" in args:
        print_status_summary()
    elif "--cron" in args:
        print("[service] Cron daemon started. Runs daily at 9:00 AM.")
        print("[service] Press Ctrl+C to stop.\n")
        run()
        schedule.every().day.at("09:00").do(run)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run()
