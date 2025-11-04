"""
Config loader: reads Fileloader.csv and upserts rows into `config_table`.

    This populates explicit columns required by the file_loader flow:
    - filename, query_identifier, query_text, bind_keys
    - table_name, proc, load_action

Call `ensure_configs_loaded()` at application startup or on-demand.
"""
from __future__ import annotations
import os
import csv
import json
import ast
from typing import Optional, Dict, Any
from sqlalchemy import text
from db import get_engine


def _parse_column_mapping(mapping_text: str) -> Optional[dict]:
    if not mapping_text:
        return None
    try:
        return ast.literal_eval(mapping_text)
    except Exception:
        try:
            return json.loads(mapping_text.replace("'", '"'))
        except Exception:
            return None


def _ensure_table_and_columns(conn):
    try:
        conn.execute(text("SELECT 1 FROM config_table WHERE 1=0"))
    except Exception:
        # create a table compatible with init_db.sql if missing
        conn.execute(text(
            "CREATE TABLE config_table (id NUMBER PRIMARY KEY, filename VARCHAR2(4000) NOT NULL, query_identifier VARCHAR2(4000) NOT NULL, query_text CLOB NOT NULL, bind_keys VARCHAR2(4000), table_name VARCHAR2(4000), proc VARCHAR2(4000), load_action VARCHAR2(50))"
        ))

    # ensure specific columns exist - best-effort
    for col_def in ("table_name VARCHAR2(4000)", "proc VARCHAR2(4000)", "load_action VARCHAR2(50)"):
        col = col_def.split()[0]
        try:
            conn.execute(text(f"SELECT {col} FROM config_table WHERE 1=0"))
        except Exception:
            try:
                # try generic alter - may fail on restricted DBs
                conn.execute(text(f"ALTER TABLE config_table ADD ({col_def})"))
            except Exception:
                pass


def load_configs_from_file(csv_path: Optional[str] = None) -> int:
    if not csv_path:
        csv_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'file_loader', 'Fileloader.csv'))

    engine = get_engine()
    upsert_count = 0

    with open(csv_path, encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        with engine.connect() as conn:
            try:
                _ensure_table_and_columns(conn)
            except Exception:
                pass

            for row in reader:
                try:
                    enabled = (row.get('ENABLED') or '').strip().upper()
                    if enabled != 'Y':
                        continue

                    path = (row.get('PATH') or '').strip()
                    table_name_val = (row.get('TABLE_NAME') or '').strip()
                    mapping_text = (row.get('COLUMN_MAPPING') or '').strip()
                    proc_val = (row.get('PROC') or '').strip()
                    load_action_val = (row.get('LOAD_ACTION') or '').strip()

                    if not table_name_val:
                        continue

                    mapping = _parse_column_mapping(mapping_text)
                    csv_cols = []
                    db_cols = []
                    if isinstance(mapping, dict):
                        csv_cols = [k for k in mapping.keys()]
                        db_cols = [v for v in mapping.values()]

                    bind_keys = ",".join(csv_cols) if csv_cols else None

                    query_text = None
                    if csv_cols and db_cols and len(csv_cols) == len(db_cols):
                        binds = [f":{col}" for col in csv_cols]
                        cols_sql = ', '.join(db_cols)
                        binds_sql = ', '.join(binds)
                        query_text = f"INSERT INTO {table_name_val} ({cols_sql}) VALUES ({binds_sql})"

                    filename = os.path.basename(path) if path else table_name_val
                    query_identifier = table_name_val

                    existing = conn.execute(text("SELECT id FROM config_table WHERE filename = :f AND query_identifier = :q"), {"f": filename, "q": query_identifier}).fetchone()
                    if existing:
                        conn.execute(text("UPDATE config_table SET query_text = :qt, bind_keys = :bk, table_name = :tn, proc = :pr, load_action = :la WHERE id = :id"), {"qt": query_text, "bk": bind_keys, "tn": table_name_val, "pr": proc_val, "la": load_action_val, "id": existing[0]})
                    else:
                        try:
                            got = conn.execute(text("SELECT MAX(id) FROM config_table")).fetchone()
                            next_id = (got[0] or 0) + 1
                        except Exception:
                            next_id = 1
                        conn.execute(text("INSERT INTO config_table (id, filename, query_identifier, query_text, bind_keys, table_name, proc, load_action) VALUES (:id, :f, :q, :qt, :bk, :tn, :pr, :la)"), {"id": next_id, "f": filename, "q": query_identifier, "qt": query_text, "bk": bind_keys, "tn": table_name_val, "pr": proc_val, "la": load_action_val})

                    upsert_count += 1
                except Exception as e:
                    print(f"Failed to process Fileloader row for {row.get('TABLE_NAME')}: {e}")

    return upsert_count


def ensure_configs_loaded(csv_path: Optional[str] = None) -> int:
    try:
        return load_configs_from_file(csv_path)
    except Exception:
        return 0
