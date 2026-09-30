from .connection import get_connection


def get_sender_rule_types(address: str, domain: str) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            select rule_type from sender_rules
            where (scope = 'address' and value = %s)
               or (scope = 'domain' and value = %s)
            """,
            (address, domain),
        ).fetchall()
    return {row[0] for row in rows}


def add_sender_rule(scope: str, value: str, rule_type: str) -> None:
    value = value.lower()
    with get_connection() as conn:
        if rule_type in ("always_skip", "always_draft"):
            # The two are mutually exclusive for a given sender/domain.
            other = "always_draft" if rule_type == "always_skip" else "always_skip"
            conn.execute(
                "delete from sender_rules where scope = %s and value = %s and rule_type = %s",
                (scope, value, other),
            )
        conn.execute(
            """
            insert into sender_rules (scope, value, rule_type)
            values (%s, %s, %s)
            on conflict (scope, value, rule_type) do nothing
            """,
            (scope, value, rule_type),
        )
        conn.commit()
