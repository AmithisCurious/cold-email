# cold-email

Automated cold email outreach for job hunting. Scrapes hiring managers and AI leads, writes personalized emails via a local LLM, sends via Gmail. Free tier friendly — rotates across multiple accounts.

## Stack

- **Scraping**: Apollo.io API, team page scraping (BeautifulSoup), GitHub API
- **Email gen**: Local LLM via [Ollama](https://ollama.com) (runs on your GPU)
- **Sending**: Gmail API (OAuth)
- **Rate limiting**: 25 emails/day, 5/hour, randomized 2–5min gaps
- **Account rotation**: Multiple Apollo/Hunter accounts, monthly limit tracking

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure accounts

```bash
cp accounts.yml.example accounts.yml
```

Fill in `accounts.yml`:
- **Apollo**: free account at [app.apollo.io](https://app.apollo.io) → Settings → API Keys (50 exports/month free)
- **Gmail**: see OAuth setup below

### 3. Gmail OAuth

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **Gmail API**
3. OAuth consent screen → External → add your Gmail as test user
4. Credentials → OAuth 2.0 Client ID → **Desktop app** → note `client_id` and `client_secret`
5. Paste them into `accounts.yml` under `gmail:`
6. Run the auth helper:

```bash
python auth.py
```

A browser window will open — sign in and approve. The `refresh_token` is saved to `accounts.yml` automatically.

### 4. Set up Ollama (on your local GPU machine)

```bash
# Install Ollama: https://ollama.com
ollama pull llama3.1:8b   # or mistral, qwen2.5, etc.
ollama serve              # starts on localhost:11434
```

Update `config.yml` if you want a different model:

```yaml
llm:
  model: "mistral:7b"   # or qwen2.5:7b, phi3:mini, etc.
```

### 5. Customize targeting

Edit `config.yml`:
- `targeting.titles` — who to email
- `targeting.skip_titles` — who to skip
- `targeting.max_company_size` — skip large companies
- `sender.*` — your info (name, email, LinkedIn, GitHub, blurb)

Edit `companies.json` (optional) to target specific companies:

```json
[
  { "name": "Sarvam AI", "url": "https://sarvam.ai" },
  { "name": "Yellow.ai", "url": "https://yellow.ai" }
]
```

If `companies.json` doesn't exist, the service uses a built-in list of ~20 Indian AI startups.

## Usage

```bash
# Run once (scrape → generate → send)
python service.py

# Start as a daily cron daemon (9am every day)
python service.py --cron

# Check account usage and send log
python service.py --status
```

## File structure

```
cold-email/
├── config.yml            # targeting, rate limits, LLM config (edit this)
├── accounts.yml          # credentials — gitignored, never commit
├── accounts.yml.example  # template
├── companies.json        # optional custom company list
│
├── service.py            # main orchestrator
├── scraper.py            # Apollo + Hunter + team pages + GitHub
├── email_gen.py          # Ollama email generator
├── sender.py             # Gmail API sender with rate limiting
├── rotate.py             # account pool rotation
├── auth.py               # Gmail OAuth setup (run once)
├── requirements.txt      # pip dependencies
│
├── targets.json          # scraped contacts DB (gitignored)
└── sent.log              # send history (gitignored)
```

## Multi-account rotation

When one Apollo or Hunter account hits its monthly limit, the service automatically picks the next account in the pool. Add more accounts to `accounts.yml`:

```yaml
apollo:
  - email: "account1@gmail.com"
    api_key: "..."
    monthly_limit: 50
    used: 0
    reset_date: ""
  - email: "account2@gmail.com"
    api_key: "..."
    monthly_limit: 50
    used: 0
    reset_date: ""
```

## Rate limits (defaults)

| Limit | Value |
|-------|-------|
| Emails per day | 25 |
| Emails per hour | 5 |
| Delay between sends | 2–5 min (randomized) |

Adjust in `config.yml` under `rate_limits`.
