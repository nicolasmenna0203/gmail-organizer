"""
Gmail Organizer - Rule-based automated inbox management.
Runs daily via GitHub Actions. No AI/LLM tokens consumed - pure pattern matching.

Steps:
  0. Trash emails from already-unsubscribed senders
  1. Tag unlabeled emails (rule-based, up to 250/run)
  2. Archive old read emails (3+ months, up to 50)
  3. Trash old promotions (6+ months, up to 50)
  4. Report repeat promo senders as unsubscribe candidates

Configuration (labels, unsubscribed senders, tagging rules) lives in
config.json, which is gitignored since it reflects one person's inbox.
See config.example.json for the expected shape.
"""

import os
import json
import re
import time
from collections import Counter, defaultdict

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CONFIG_PATH = os.environ.get("GMAIL_ORGANIZER_CONFIG", "config.json")

# Patterns that indicate an automated/no-reply sender (not Personal)
AUTOMATED_SENDER_PATTERNS = re.compile(
    r"no.?reply|noreply|donotreply|do-not-reply|bounce|mailer|automated|"
    r"notification|alert|info@|news@|newsletter|promo|marketing|support@|"
    r"help@|service@|system@|admin@|contact@|hello@|hola@|update@|"
    r"invoices@|billing@|receipt@|orders@|shipping@|delivery@|team@|"
    r"hr@|rrhh@|noresponder|no-responder",
    re.IGNORECASE,
)


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8-sig") as f:
        raw = json.load(f)

    # JSON can't express sets/tuples natively, so normalize on load.
    rules = [
        (rule["label"], set(rule.get("sender_patterns", [])), set(rule.get("subject_patterns", [])))
        for rule in raw["tagging_rules"]
    ]
    return {
        "labels": raw["labels"],
        "unsubscribed": raw["unsubscribed"],
        "tagging_rules": rules,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

def get_service():
    """Build Gmail service from env var GMAIL_TOKEN_JSON (GitHub Secret)."""
    token_data = os.environ.get("GMAIL_TOKEN_JSON")
    if not token_data:
        raise RuntimeError("GMAIL_TOKEN_JSON env var not set")

    creds_info = json.loads(token_data.lstrip("﻿"))
    creds = Credentials.from_authorized_user_info(creds_info, SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Write updated token so the GH Action can capture & update the secret
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            token_json = creds.to_json().replace("\n", "")
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(f"updated_token={token_json}\n")

    return build("gmail", "v1", credentials=creds)


# ─────────────────────────────────────────────────────────────────────────────
# Gmail helpers
# ─────────────────────────────────────────────────────────────────────────────

def search_threads(service, query, max_results=50, page_token=None):
    params = dict(userId="me", q=query, maxResults=max_results)
    if page_token:
        params["pageToken"] = page_token
    resp = service.users().threads().list(**params).execute()
    return resp.get("threads", []), resp.get("nextPageToken")


def get_thread_meta(service, thread_id):
    """Fetch minimal metadata (sender, subject, snippet, labels)."""
    resp = service.users().threads().get(
        userId="me", id=thread_id, format="metadata",
        metadataHeaders=["From", "Subject"],
    ).execute()
    messages = resp.get("messages", [])
    if not messages:
        return None

    # Gather all label IDs across messages
    all_labels = set()
    for m in messages:
        all_labels.update(m.get("labelIds", []))

    first = messages[0]
    headers = {h["name"]: h["value"] for h in first.get("payload", {}).get("headers", [])}
    return {
        "id": thread_id,
        "sender": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "snippet": first.get("snippet", ""),
        "label_ids": all_labels,
    }


def label_thread(service, thread_id, label_id):
    service.users().threads().modify(
        userId="me", id=thread_id,
        body={"addLabelIds": [label_id]},
    ).execute()


def unlabel_thread(service, thread_id, label_ids):
    service.users().threads().modify(
        userId="me", id=thread_id,
        body={"removeLabelIds": label_ids},
    ).execute()


def trash_thread(service, thread_id):
    service.users().threads().trash(userId="me", id=thread_id).execute()


def is_starred_or_important(label_ids):
    return bool({"STARRED", "IMPORTANT"} & label_ids)


# ─────────────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────────────

def normalize(text):
    return text.lower()


def sender_matches(sender_lower, patterns):
    """Return True if any pattern is a substring of sender_lower."""
    return any(p in sender_lower for p in patterns)


def subject_matches(subject_lower, patterns):
    return any(p in subject_lower for p in patterns)


def classify_thread(meta, tagging_rules):
    """Return label name or None if unsure."""
    sender = normalize(meta["sender"])
    subject = normalize(meta["subject"])

    for label_name, sender_pats, subject_pats in tagging_rules:
        s_match = sender_matches(sender, sender_pats) if sender_pats else True
        subj_match = subject_matches(subject, subject_pats) if subject_pats else True

        if sender_pats and subject_pats:
            if s_match and subj_match:
                return label_name
        elif sender_pats:
            if s_match:
                return label_name
        elif subject_pats:
            if subj_match:
                return label_name

    # Personal: real human sender not matching automated patterns
    if not AUTOMATED_SENDER_PATTERNS.search(sender):
        return "Personal"

    return None  # unsure — leave unlabeled


# ─────────────────────────────────────────────────────────────────────────────
# Steps
# ─────────────────────────────────────────────────────────────────────────────

def paso_0(service, unsubscribed):
    """Trash emails from already-unsubscribed senders."""
    if not unsubscribed:
        return 0, []

    from_query = " OR ".join(f"from:{s}" for s in unsubscribed)
    query = f"in:inbox ({from_query})"
    threads, _ = search_threads(service, query, max_results=50)

    trashed = 0
    skipped_starred = []
    for t in threads:
        meta = get_thread_meta(service, t["id"])
        if not meta:
            continue
        if is_starred_or_important(meta["label_ids"]):
            skipped_starred.append(meta["subject"] or meta["sender"])
            continue
        trash_thread(service, t["id"])
        trashed += 1
        time.sleep(0.1)

    return trashed, skipped_starred


def paso_1(service, tagging_rules, labels, max_threads=250):
    """Tag unlabeled threads using rule-based classification."""
    tagged = 0
    counts = Counter()
    processed = 0
    page_token = None

    while processed < max_threads:
        batch_size = min(50, max_threads - processed)
        threads, page_token = search_threads(
            service,
            "has:nouserlabels -in:trash -in:spam",
            max_results=batch_size,
            page_token=page_token,
        )
        if not threads:
            break

        for t in threads:
            if processed >= max_threads:
                break
            processed += 1

            meta = get_thread_meta(service, t["id"])
            if not meta:
                continue

            # Skip if it already has user labels (race condition guard)
            user_labels = {l for l in meta["label_ids"] if l.startswith("Label_")}
            if user_labels:
                continue

            label_name = classify_thread(meta, tagging_rules)
            if label_name:
                label_thread(service, t["id"], labels[label_name])
                tagged += 1
                counts[label_name] += 1
                time.sleep(0.05)

        if not page_token:
            break

    return tagged, counts


def paso_2(service, labels, max_threads=50):
    """Archive old read emails (3+ months, not starred/important/Personal)."""
    query = "is:read older_than:3m in:inbox -is:starred -in:important -label:Personal"
    threads, _ = search_threads(service, query, max_results=max_threads)

    personal_label = labels.get("Personal")
    archived = 0
    for t in threads:
        meta = get_thread_meta(service, t["id"])
        if not meta:
            continue
        if is_starred_or_important(meta["label_ids"]):
            continue
        if personal_label and personal_label in meta["label_ids"]:
            continue
        unlabel_thread(service, t["id"], ["INBOX"])
        archived += 1
        time.sleep(0.1)

    return archived


def paso_3(service, labels, protected_label_names, max_threads=50):
    """Trash old promotional emails (6+ months)."""
    query = "category:promotions older_than:6m in:inbox -is:starred -in:important"
    threads, _ = search_threads(service, query, max_results=max_threads)

    protected_labels = {labels[name] for name in protected_label_names if name in labels}
    trashed = 0
    for t in threads:
        meta = get_thread_meta(service, t["id"])
        if not meta:
            continue
        if is_starred_or_important(meta["label_ids"]):
            continue
        if meta["label_ids"] & protected_labels:
            continue
        trash_thread(service, t["id"])
        trashed += 1
        time.sleep(0.1)

    return trashed


def paso_4(service, unsubscribed):
    """Detect repeat promotional senders (3+) not in the unsubscribe list."""
    threads, _ = search_threads(service, "category:promotions in:inbox", max_results=50)

    unsubscribed_lower = {s.lower() for s in unsubscribed}
    sender_counts = defaultdict(int)

    for t in threads:
        meta = get_thread_meta(service, t["id"])
        if not meta:
            continue
        m = re.search(r"<(.+?)>", meta["sender"])
        email = m.group(1).lower() if m else normalize(meta["sender"])
        if any(u in email for u in unsubscribed_lower):
            continue
        sender_counts[email] += 1
        time.sleep(0.03)

    candidates = [(email, count) for email, count in sender_counts.items() if count >= 3]
    candidates.sort(key=lambda x: -x[1])
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    config = load_config()
    labels = config["labels"]
    unsubscribed = config["unsubscribed"]
    tagging_rules = config["tagging_rules"]
    protected_label_names = [name for name in labels if name != "Promociones"]

    service = get_service()

    print("=== Gmail Organizer ===\n")

    print("▶ Paso 0: Trashing unsubscribed senders...")
    trashed_0, skipped = paso_0(service, unsubscribed)
    print(f"  Trashed: {trashed_0}")
    if skipped:
        print(f"  Skipped (starred): {skipped}")

    print("\n▶ Paso 1: Tagging unlabeled threads (up to 250)...")
    tagged, tag_counts = paso_1(service, tagging_rules, labels)
    for label, count in tag_counts.most_common():
        print(f"  {label}: {count}")
    print(f"  Total tagged: {tagged}")

    print("\n▶ Paso 2: Archiving old read emails...")
    archived = paso_2(service, labels)
    print(f"  Archived: {archived}")

    print("\n▶ Paso 3: Trashing old promotions...")
    trashed_3 = paso_3(service, labels, protected_label_names)
    print(f"  Trashed: {trashed_3}")

    print("\n▶ Paso 4: Unsubscribe candidates...")
    candidates = paso_4(service, unsubscribed)
    if candidates:
        for email, count in candidates:
            print(f"  {email} ({count} mails)")
    else:
        print("  Ninguno encontrado.")

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tagged: {tagged} | Archived: {archived} | Trashed: {trashed_0 + trashed_3}
Unsubscribe candidates: {len(candidates)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    main()
