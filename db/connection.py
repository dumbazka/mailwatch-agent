import psycopg

from config import settings


def get_connection() -> psycopg.Connection:
    return psycopg.connect(settings.database_url)


def apply_schema() -> None:
    """Run schema.sql against DATABASE_URL. Safe to re-run (all statements use IF NOT EXISTS)."""
    schema_path = __file__.replace("connection.py", "schema.sql")
    with open(schema_path) as f:
        schema_sql = f.read()

    with get_connection() as conn:
        conn.execute(schema_sql)
        conn.commit()


if __name__ == "__main__":
    apply_schema()
    print("Schema applied.")
