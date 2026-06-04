from pathlib import Path

import requests
import yaml

CONFIG_PATH = Path(__file__).parent / "config.yml"
ACCOUNTS_PATH = Path(__file__).parent / "accounts.yml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)


def _load_sender():
    with open(ACCOUNTS_PATH) as f:
        accounts = yaml.safe_load(f)
    sender = accounts.get("sender")
    if not sender or not sender.get("email"):
        raise RuntimeError("Missing sender config in accounts.yml — add a 'sender:' section")
    return sender


def _build_prompt(sender, target):
    role_line = ""
    if target.get("role"):
        role_line = f"- They have an open role: {target['role']}\n"
        if target.get("role_url"):
            role_line += f"  URL: {target['role_url']}\n"

    notes_line = ""
    if target.get("notes"):
        notes_line = f"\nExtra context about why this company is a good fit:\n{target['notes']}\n"

    has_attachment = bool(target.get("resume_pdf"))
    attachment_instruction = (
        "- Mention that your resume is attached\n" if has_attachment
        else ""
    )

    return (
        f"You are writing a cold email from {sender['name']} to "
        f"{target['name']} ({target['title']} at {target['company']}).\n\n"
        f"About the sender:\n"
        f"- Name: {sender['name']}\n"
        f"- Role: {sender['role']}\n"
        f"- Background: {sender['blurb']}\n"
        f"- LinkedIn: {sender['linkedin']}\n"
        f"- GitHub: {sender['github']}\n\n"
        f"About the recipient's company:\n"
        f"{role_line}"
        f"{notes_line}\n"
        f"Write a SHORT cold email (4-6 sentences max). Requirements:\n"
        f'- Subject line on the first line, prefixed with "Subject: "\n'
        f"- One blank line\n"
        f"- Then the email body\n"
        f"- If there's an open role, mention it naturally — not robotic\n"
        f"- Open with something specific about their company or role (not generic flattery)\n"
        f"- One concrete thing the sender built that's relevant to their work\n"
        f"- Clear ask: 15-min call or reply if open to talking\n"
        f"{attachment_instruction}"
        f'- No fluff, no buzzwords, no "I hope this email finds you well"\n'
        f"- Sound like a human engineer, not a recruiter or salesperson\n"
        f"- Sign off with just the sender's first name\n\n"
        f"Output ONLY the subject line and email body. Nothing else."
    )


def _call_llm(prompt):
    llm = config["llm"]
    res = requests.post(
        f"{llm['base_url']}/api/generate",
        json={
            "model": llm["model"],
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": llm["temperature"],
                "num_predict": llm["max_tokens"],
            },
        },
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Ollama error: {res.status_code} {res.text}")
    return res.json().get("response", "").strip()


def _parse_email(raw):
    lines = raw.splitlines()
    subject_line = next((l for l in lines if l.lower().startswith("subject:")), None)
    if not subject_line:
        return {
            "subject": f"{config['sender']['role']} — open to a quick chat?",
            "body": raw.strip(),
        }
    subject = subject_line[len("subject:"):].strip()
    idx = lines.index(subject_line)
    body = "\n".join(lines[idx + 1:]).strip()
    return {"subject": subject, "body": body}


def generate_email(target):
    sender = _load_sender()
    try:
        prompt = _build_prompt(sender, target)
        raw = _call_llm(prompt)

        if not raw:
            print(f"[email-gen] Empty response for {target['email']}")
            return None

        result = _parse_email(raw)

        if not (50 <= len(result["body"]) <= 2000):
            print(f"[email-gen] Suspicious body length ({len(result['body'])}) for {target['email']}")
            return None

        return result
    except Exception as e:
        print(f"[email-gen] Failed for {target['email']}: {e}")
        return None


def check_llm():
    try:
        res = requests.get(f"{config['llm']['base_url']}/api/tags", timeout=5)
        if not res.ok:
            return False
        models = [m["name"] for m in res.json().get("models", [])]
        model_prefix = config["llm"]["model"].split(":")[0]
        has_model = any(m.startswith(model_prefix) for m in models)
        if not has_model:
            print(f"[email-gen] Model \"{config['llm']['model']}\" not found. Available: {', '.join(models)}")
            print(f"[email-gen] Run: ollama pull {config['llm']['model']}")
        return has_model
    except Exception:
        print(f"[email-gen] Ollama unreachable at {config['llm']['base_url']}. Is it running?")
        return False
