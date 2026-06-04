from datetime import date, datetime
from pathlib import Path

import yaml

ACCOUNTS_PATH = Path(__file__).parent / "accounts.yml"


def _load():
    with open(ACCOUNTS_PATH) as f:
        return yaml.safe_load(f)


def _save(accounts):
    with open(ACCOUNTS_PATH, "w") as f:
        yaml.dump(accounts, f, default_flow_style=False)


def get_active_account(service):
    accounts = _load()
    pool = accounts.get(service, [])

    if not isinstance(pool, list) or not pool:
        print(f"[rotate] No accounts configured for {service}")
        return None

    today = date.today().isoformat()

    for account in pool:
        if not account.get("api_key"):
            continue

        if account.get("reset_date"):
            days_since = (datetime.now() - datetime.fromisoformat(str(account["reset_date"]))).days
            if days_since >= 30:
                account["used"] = 0
                account["reset_date"] = today
                print(f"[rotate] Monthly reset for {account['email']} ({service})")

        if account.get("used", 0) < account.get("monthly_limit", 0):
            if not account.get("reset_date"):
                account["reset_date"] = today
            _save(accounts)
            return account

    print(f"[rotate] All {service} accounts exhausted. Add more to accounts.yml")
    return None


def record_usage(service, email):
    accounts = _load()
    for account in accounts.get(service, []):
        if account.get("email") == email:
            account["used"] = account.get("used", 0) + 1
            _save(accounts)
            return


def print_status():
    accounts = _load()
    for service, pool in accounts.items():
        if not isinstance(pool, list):
            continue
        print(f"\n[{service}]")
        for a in pool:
            if not a.get("api_key"):
                print("  - (unconfigured)")
                continue
            left = a.get("monthly_limit", 0) - a.get("used", 0)
            status = f"{left} remaining" if left > 0 else "EXHAUSTED"
            print(f"  - {a['email']}: {status} ({a.get('used', 0)}/{a.get('monthly_limit', 0)})")
