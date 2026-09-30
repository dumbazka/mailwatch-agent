from dataclasses import dataclass

from db.keyword_rules import get_keywords
from db.sender_rules import get_sender_rule_types
from gmail.parsing import (
    get_categories,
    get_sender,
    get_sender_display_name,
    get_subject,
    has_list_unsubscribe,
    is_auto_submitted,
    is_bulk_precedence,
)

NO_REPLY_PATTERNS = ("no-reply@", "noreply@", "donotreply@")

# CATEGORY_UPDATES/CATEGORY_FORUMS is where Gmail's own classifier buckets
# job-alert and other automated-notification mail (Indeed, LinkedIn, GitHub,
# etc.) — not just promos/social.
SKIP_CATEGORIES = {
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES",
    "CATEGORY_FORUMS",
}


@dataclass(frozen=True)
class Classification:
    should_draft: bool
    reason: str
    sender_address: str
    sender_domain: str


def _matched_keyword(text: str, keywords: list[str]) -> str | None:
    lowered = text.lower()
    for kw in keywords:
        if kw in lowered:
            return kw
    return None


def classify_message(message: dict) -> Classification:
    address, domain = get_sender(message)
    rule_types = get_sender_rule_types(address, domain)

    # Always-skip overrides everything, including always-draft.
    if "always_skip" in rule_types:
        return Classification(False, "sender marked always-skip", address, domain)

    # Always-draft overrides every other skip signal below.
    if "always_draft" in rule_types:
        return Classification(True, "sender marked always-draft", address, domain)

    if "block" in rule_types:
        return Classification(False, "sender on block list", address, domain)

    if any(address.startswith(p) for p in NO_REPLY_PATTERNS):
        return Classification(False, "no-reply sender pattern", address, domain)

    if get_categories(message) & SKIP_CATEGORIES:
        return Classification(False, "gmail category (promotions/updates/social/forums)", address, domain)

    if has_list_unsubscribe(message):
        return Classification(False, "List-Unsubscribe header present", address, domain)

    if is_bulk_precedence(message):
        return Classification(False, "Precedence: bulk/list header", address, domain)

    if is_auto_submitted(message):
        return Classification(False, "Auto-Submitted header", address, domain)

    keywords = get_keywords()
    subject = get_subject(message)
    display_name = get_sender_display_name(message)
    matched = _matched_keyword(subject, keywords) or _matched_keyword(display_name, keywords)
    if matched:
        return Classification(False, f"matched blocked keyword '{matched}'", address, domain)

    return Classification(True, "real email", address, domain)
