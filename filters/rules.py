from dataclasses import dataclass

from db.sender_rules import get_sender_rule_types
from gmail.parsing import get_categories, get_sender, has_list_unsubscribe

NO_REPLY_PATTERNS = ("no-reply@", "noreply@", "donotreply@")
SKIP_CATEGORIES = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}


@dataclass(frozen=True)
class Classification:
    should_draft: bool
    reason: str
    sender_address: str
    sender_domain: str


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
        return Classification(False, "gmail category (promotions/social)", address, domain)

    if has_list_unsubscribe(message):
        return Classification(False, "List-Unsubscribe header present", address, domain)

    return Classification(True, "real email", address, domain)
