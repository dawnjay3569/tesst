from db import get_engine
from sqlalchemy import text
import pathlib


def init_db_from_sql(sql_path: str = "init_db.sql"):
    engine = get_engine()
    # Use the provided SQL path (default: init_db.sql). We no longer maintain
    # a separate SQLite SQL file; init_db.sql should contain the portable/Oracle
    # initialization statements expected in production.
    sql_file = pathlib.Path(sql_path)
    if not sql_file.exists():
        raise FileNotFoundError(f"{sql_path} not found")

    sql_text = sql_file.read_text(encoding="utf-8")

    # Split on forward slash separators (Oracle script style) first, else treat as whole
    raw_statements = [s.strip() for s in sql_text.split("/") if s.strip()]

    with engine.connect() as conn:
        for raw in raw_statements:
            # Some blocks may contain multiple statements separated by semicolons; split them
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            for stmt in parts:
                try:
                    conn.execute(text(stmt))
                except Exception as e:
                    # If object already exists (ORA-00955) ignore; otherwise re-raise
                    msg = str(e)
                    if "ORA-00955" in msg or "already exists" in msg:
                        # skip existing object
                        continue
                    else:
                        raise


if __name__ == "__main__":
    init_db_from_sql()
    print("Initialized database from init_db.sql")
