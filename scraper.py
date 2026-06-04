import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

from rotate import get_active_account, record_usage

CONFIG_PATH = Path(__file__).parent / "config.yml"
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

TARGETS_PATH = Path(__file__).parent / config["paths"]["targets_db"]


def _load_targets():
    if not TARGETS_PATH.exists():
        return []
    with open(TARGETS_PATH) as f:
        return json.load(f)


def _save_targets(targets):
    with open(TARGETS_PATH, "w") as f:
        json.dump(targets, f, indent=2)


def _is_duplicate(targets, email):
    return any(t.get("email") == email for t in targets)


def _should_skip_title(title):
    if not title:
        return True
    t = title.lower()
    return any(s.lower() in t for s in config["targeting"]["skip_titles"])


def _is_good_title(title):
    if not title:
        return False
    t = title.lower()
    return any(s.lower() in t for s in config["targeting"]["titles"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _role_fields(company):
    """Extract role passthrough fields from a company/queue entry."""
    return {
        "role": company.get("role", ""),
        "role_url": company.get("role_url", ""),
        "resume_pdf": company.get("resume_pdf", ""),
        "notes": company.get("notes", ""),
    }


def _scrape_apollo(companies):
    account = get_active_account("apollo")
    if not account:
        print("[scraper] Skipping Apollo — no active account")
        return []

    found = []
    for company in companies:
        try:
            res = requests.post(
                "https://api.apollo.io/v1/mixed_people/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": account["api_key"],
                },
                json={
                    "q_organization_name": company["name"],
                    "person_titles": config["targeting"]["titles"],
                    "per_page": 10,
                },
                timeout=15,
            )
            if not res.ok:
                print(f"[apollo] {company['name']}: {res.status_code}")
                continue

            data = res.json()
            record_usage("apollo", account["email"])

            for person in data.get("people", []):
                if not person.get("email"):
                    continue
                if _should_skip_title(person.get("title")):
                    continue
                if not _is_good_title(person.get("title")):
                    continue

                found.append({
                    "name": person.get("name"),
                    "email": person["email"],
                    "title": person.get("title"),
                    "company": company["name"],
                    "company_url": company.get("url", ""),
                    "source": "apollo",
                    "scraped_at": _now(),
                    **_role_fields(company),
                })

            time.sleep(config["scraping"]["request_delay_seconds"])
        except Exception as e:
            print(f"[apollo] Error for {company['name']}: {e}")

    return found


def _scrape_team_page(company):
    if not company.get("url"):
        return []

    found = []
    urls = [
        f"{company['url']}/about",
        f"{company['url']}/team",
        f"{company['url']}/about-us",
        f"{company['url']}/company",
    ]

    for url in urls:
        try:
            res = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"},
                timeout=8,
            )
            if not res.ok:
                continue

            soup = BeautifulSoup(res.text, "html.parser")

            candidates = []
            for keyword in ["team", "member", "person", "people"]:
                candidates += soup.find_all(
                    class_=lambda c, k=keyword: c and k in c.lower()
                )

            for el in candidates:
                name_el = el.find(["h2", "h3", "h4", "strong"])
                role_el = el.find(["p", "span"])

                if not name_el or not role_el:
                    continue

                name = name_el.get_text(strip=True)
                role = role_el.get_text(strip=True)

                if not _is_good_title(role) or _should_skip_title(role):
                    continue

                found.append({
                    "name": name,
                    "title": role,
                    "company": company["name"],
                    "company_url": company["url"],
                    "email": None,
                    "source": "team-page",
                    "scraped_at": _now(),
                    **_role_fields(company),
                })

            if found:
                break
            time.sleep(config["scraping"]["request_delay_seconds"])
        except Exception:
            pass  # many team pages block scrapers

    return found


def _scrape_github(company):
    found = []
    try:
        res = requests.get(
            "https://api.github.com/search/users",
            params={"q": f"{company['name']} engineer type:user", "per_page": 10},
            headers={"User-Agent": "cold-email-bot/1.0"},
            timeout=10,
        )
        if not res.ok:
            return []

        for user in res.json().get("items", []):
            time.sleep(1)
            profile_res = requests.get(
                f"https://api.github.com/users/{user['login']}",
                headers={"User-Agent": "cold-email-bot/1.0"},
                timeout=10,
            )
            if not profile_res.ok:
                continue
            profile = profile_res.json()

            if not profile.get("email"):
                continue
            if company["name"].lower() not in (profile.get("company") or "").lower():
                continue

            found.append({
                "name": profile.get("name") or user["login"],
                "email": profile["email"],
                "title": profile.get("bio") or "Engineer",
                "company": company["name"],
                "company_url": company.get("url", ""),
                "github": user.get("html_url"),
                "source": "github",
                "scraped_at": _now(),
                **_role_fields(company),
            })
    except Exception as e:
        print(f"[github] Error: {e}")

    return found


def _normalize(companies):
    """Accept both {name, url} (generic) and {name, url, role, ...} (queue) formats."""
    normalized = []
    for c in companies:
        entry = dict(c)
        # queue entries use 'company'/'company_url'; scraper internally uses 'name'/'url'
        if "company" in entry and "name" not in entry:
            entry["name"] = entry.pop("company")
        if "company_url" in entry and "url" not in entry:
            entry["url"] = entry.pop("company_url")
        normalized.append(entry)
    return normalized


def scrape(companies):
    companies = _normalize(companies)
    existing = _load_targets()
    new_targets = []

    print(f"[scraper] Starting scrape for {len(companies)} companies...")

    apollo_results = _scrape_apollo(companies)
    for t in apollo_results:
        if not _is_duplicate(existing, t["email"]) and not _is_duplicate(new_targets, t["email"]):
            new_targets.append(t)

    # Team page scraping — only keeps contacts where email is directly visible on the page
    apollo_companies = {t["company"] for t in apollo_results}
    for company in companies:
        if company["name"] in apollo_companies or not company.get("url"):
            continue

        team_results = _scrape_team_page(company)
        for t in team_results:
            if t.get("email") and not _is_duplicate(existing, t["email"]) and not _is_duplicate(new_targets, t["email"]):
                new_targets.append(t)

    for company in companies:
        for t in _scrape_github(company):
            if not _is_duplicate(existing, t["email"]) and not _is_duplicate(new_targets, t["email"]):
                new_targets.append(t)

    all_targets = existing + new_targets
    _save_targets(all_targets)
    print(f"[scraper] Found {len(new_targets)} new targets. Total: {len(all_targets)}")
    return new_targets
