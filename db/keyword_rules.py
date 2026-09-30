from .connection import get_connection


def get_keywords() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("select keyword from keyword_rules").fetchall()
    return [row[0] for row in rows]


def add_keyword(keyword: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "insert into keyword_rules (keyword) values (%s) on conflict (keyword) do nothing",
            (keyword.lower(),),
        )
        conn.commit()
