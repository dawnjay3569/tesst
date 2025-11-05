"""
File loader service module

This module implements the file-loader-specific processing that is invoked
from the `/executeConfigBulk` endpoint when the `file_loader` boolean flag
is true. It reuses existing helpers from `file_loader` and
`file_loader_api.common_lib` (update_sql, update_sql_oi_rtqm, insert_to_oi_rtqm,
fileloaderdecisionmaker) where available.

The function `process_file_loader_job(cfg, upload_file, logical_filename)` is
the main entry point and returns a dict result suitable for inclusion in the
API response.

Comments are included to explain each step and match the numbered steps in
the task description (steps 6-14 of the original main workflow).
"""
from __future__ import annotations
import os
import io
import ast
import socket
import datetime
import logging
import json
import pandas as pd
from typing import Dict, Any

# Reuse existing helpers from the file_loader package when available
try:
    from file_loader_api.file_loader.main import insert_to_oi_rtqm, movefile, IS_FILELOADER_TEST
except Exception:
    insert_to_oi_rtqm = None
    movefile = None
    IS_FILELOADER_TEST = True

try:
    from file_loader_api.common_lib.oracle_insights import update_sql
except Exception:
    update_sql = None

try:
    from file_loader_api.file_loader.oracle_oi_rtqm import update_sql_oi_rtqm
except Exception:
    update_sql_oi_rtqm = None

try:
    import file_loader_api.file_loader.fileloaderdecisionmaker as fldm
    fileloaderdecisionmaker = fldm
except Exception:
    fileloaderdecisionmaker = None

# Use the project's structured logger when available, else fall back
try:
    from file_loader_api.common_lib.logging_config import get_logger
    logger = get_logger("file_loader_service")
except Exception:
    logger = logging.getLogger("file_loader_service")


def _adjust_utc_to_db_tz(dt_utc: datetime.datetime) -> str:
    """Apply deterministic +05:30 offset and return timestamp string used in UV."""
    offset = datetime.timedelta(hours=5, minutes=30)
    adjusted = dt_utc + offset
    # Use the compact format similar to file_loader/main.py: YYYYMMDDHHMMSS
    return adjusted.strftime("%Y%m%d%H%M%S")


def _normalize_column_name(col: str) -> str:
    if col is None:
        return col
    out = str(col).replace(" ", "_")
    out = out.replace(".", "")
    out = out.replace("/", "_").replace("-", "_")
    out = out.lstrip("_")
    return out


def _select_uv_processed(uv: str):
    """Helper to check UV existence in RPA_INPUTS.EXCEL_LOAD_TO_ORACLE.

    Uses update_sql/update_sql_oi_rtqm if available and expects a pandas
    DataFrame-like return where an empty result indicates no match.
    """
    sql = f"SELECT UV FROM RPA_INPUTS.EXCEL_LOAD_TO_ORACLE WHERE UV = '{uv}' AND PROCESSINGTIME IS NOT NULL"
    try:
        if update_sql_oi_rtqm:
            return update_sql_oi_rtqm(sql)
        if update_sql:
            return update_sql(sql)
    except Exception:
        logger.exception("UV duplicate-check query failed")
    return None


def process_file_loader_job(cfg: Dict[str, Any], upload_file, logical_filename: str) -> Dict[str, Any]:
    """Process a single fileloader job.

    Args:
      cfg: configuration dict from `config_table` (should contain query_text and bind_keys)
      upload_file: FastAPI UploadFile-like object
      logical_filename: supplied filename parameter used to build UV

    Returns:
      dict with status and metadata (rows_inserted, uv, table) or error details
    """
    # Step 1: Validate config
    if not cfg:
        return {"status": "error", "message": "Missing configuration"}

    schema_table = cfg.get("schema_table") or cfg.get("table") or cfg.get("TABLE_NAME") or cfg.get("table_name")
    action = cfg.get("proc") or cfg.get("PROC") or cfg.get("action") or None
    load_action = cfg.get("load_action") or cfg.get("LOAD_ACTION") or None
    bind_keys_csv = cfg.get("bind_keys") or cfg.get("BIND_KEYS") or cfg.get("bind_keys_csv")

    if not schema_table:
        return {"status": "error", "message": "Configuration missing schema/table name"}

    # Step 2: Build UV and duplicate check
    utcnow = datetime.datetime.utcnow()
    ts = _adjust_utc_to_db_tz(utcnow)
    _, ext = os.path.splitext(logical_filename)
    if not ext:
        ext = ".csv"
    uv = f"{logical_filename}_{ts}{ext}"

    try:
        sel = _select_uv_processed(uv)
        if sel is not None and hasattr(sel, "empty") and not sel.empty:
            return {"status": "error", "message": "File already processed", "uv": uv, "code": 409}
    except Exception:
        # logger.exception("UV duplicate check failed; continuing")
        pass

    # Step 3: Insert in-progress log row
    try:
        logDF = pd.DataFrame(columns=["FILENAME", "UV", "SV1", "SV5"])
        logDF = pd.concat([logDF, pd.DataFrame([{"FILENAME": logical_filename, "UV": uv, "SV1": schema_table, "SV5": socket.gethostname()}])], ignore_index=True)
        df_vals = [tuple(x)[1:] for x in logDF.itertuples()]
        logColumns = ",".join(x for x in logDF.columns)
        value_placeholder_list = ", ".join([f":{i+1}" for i in range(len(logDF.columns))])
        if insert_to_oi_rtqm:
            # call using kwargs similar to original module
            insert_to_oi_rtqm(schema_table='RPA_INPUTS.EXCEL_LOAD_TO_ORACLE', data_to_insert=df_vals, placeholder_list=value_placeholder_list, table_columns=logColumns)
        else:
            # fallback: try direct update_sql insert
            cols = ",".join(logDF.columns)
            vals = ",".join(["'" + str(v).replace("'", "''") + "'" for v in [logical_filename, uv, schema_table, socket.gethostname()] ])
            if update_sql:
                update_sql(f"INSERT INTO RPA_INPUTS.EXCEL_LOAD_TO_ORACLE ({cols}) VALUES ({vals})")
    except Exception:
        # logger.exception("Failed to insert in-progress log row")
        return {"status": "error", "message": "Failed to create in-progress log row", "uv": uv}

    # Step 4: Read CSV in-memory
    try:
        raw = upload_file.file.read()
        try:
            df = pd.read_csv(io.BytesIO(raw), dtype=str)
        except Exception:
            df = pd.read_csv(io.BytesIO(raw), encoding='iso-8859-1', dtype=str)
    except Exception:
        # logger.exception("Failed to read CSV in-memory")
        return {"status": "error", "message": "Failed to read CSV file", "uv": uv}

    # Step 5: Column mapping / normalization
    # If cfg contains a COLUMN_MAPPING-like key, attempt to apply
    column_mapping_raw = cfg.get("COLUMN_MAPPING") or cfg.get("column_mapping")
    col_map = None
    if column_mapping_raw:
        try:
            col_map = ast.literal_eval(str(column_mapping_raw))
        except Exception:
            # logger.exception("Failed to parse COLUMN_MAPPING; falling back to normalization")
            pass

    if isinstance(col_map, dict):
        df = df.rename(columns=col_map)
    elif isinstance(col_map, (list, tuple)):
        try:
            df.columns = list(col_map)
        except Exception:
            df.columns = [_normalize_column_name(c) for c in df.columns]
    else:
        df.columns = [_normalize_column_name(c) for c in df.columns]

    # df = df.fillna("").astype(str).applymap(lambda v: v.replace('\n', ' ').replace('\r', ' '))
    df = df.fillna("").astype(str).replace({r'[\n\r]+': ' '}, regex=True)

    # Step 6: Build insert payload
    cols_upper = [c.upper() for c in df.columns]
    # Validate headers against bind_keys if provided
    if bind_keys_csv:
        expected = [k.strip().upper() for k in bind_keys_csv.split(",") if k.strip()]
        if expected and expected != cols_upper:
            return {"status": "error", "message": f"CSV headers do not match bind keys. Expected: {expected}, got: {cols_upper}", "uv": uv}

    finalInsertColumn = ",".join([f'"{c}"' for c in cols_upper])
    data = [tuple(row) for row in df.itertuples(index=False, name=None)]
    placeholder_list = ", ".join([f":{i+1}" for i in range(len(cols_upper))])

    # Step 7: Apply decision maker
    try:
        if fileloaderdecisionmaker and hasattr(fileloaderdecisionmaker, 'file_loader_decision_maker'):
            try:
                fm_ret = fileloaderdecisionmaker.file_loader_decision_maker(filename=schema_table.split(".")[-1], final_insert_column=finalInsertColumn, dataframe=df, workbook_name=logical_filename)
                if isinstance(fm_ret, (list, tuple)) and len(fm_ret) >= 3:
                    finalInsertColumn, data, placeholder_list = fm_ret[0], fm_ret[1], fm_ret[2]
            except Exception:
                # logger.exception("Decision maker raised an exception; continuing")
                pass
    except Exception:
        # logger.exception("Error calling decision maker")
        pass

    # Step 8: Insert into target table and run PROC
    try:
        # If the helper is available it may support load_action/proc natively
        if insert_to_oi_rtqm:
            insert_to_oi_rtqm(schema_table=schema_table, data_to_insert=data, placeholder_list=placeholder_list, table_columns=finalInsertColumn.upper(), action=action, load_action=load_action)
        else:
            # Fallback path: delegate Oracle-specific operations to oracle_insights.update_sql
            # which knows how to handle executemany, TRUNCATE, and PL/SQL blocks.
            load_action_upper = (load_action or "").strip().upper()
            proc_val = (action or "").strip()

            # TRUNCATE (or DELETE fallback) before insert if requested
            if load_action_upper == "TRUNCATE":
                try:
                    if update_sql:
                        update_sql(f"TRUNCATE TABLE {schema_table}")
                except Exception:
                    try:
                        if update_sql:
                            update_sql(f"DELETE FROM {schema_table}")
                    except Exception:
                        # logger.exception("Failed to clear target table %s before insert", schema_table)
                        pass

            # Perform batch insert using the oracle helper when available
            if update_sql_oi_rtqm:
                insert_sql = f"insert into {schema_table} ({finalInsertColumn}) values ({placeholder_list})"
                update_sql_oi_rtqm(insert_sql, data)
            elif update_sql:
                # Use oracle_insights.update_sql which supports executemany via data param
                insert_sql = f"INSERT INTO {schema_table} ({finalInsertColumn}) VALUES ({placeholder_list})"
                try:
                    update_sql(insert_sql, data)
                except Exception:
                    # Fallback: try per-row via update_sql to increase robustness
                    for row in data:
                        vals = ",".join(["'" + str(v).replace("'", "''") + "'" for v in row])
                        update_sql(f"INSERT INTO {schema_table} ({finalInsertColumn}) VALUES ({vals})")

            # After insertion: run PROC if provided and not NO_PROC
            try:
                if proc_val and proc_val.upper() != "NO_PROC":
                    pv = proc_val.strip()
                    if pv.lower().startswith("execute "):
                        pv = pv.split(None, 1)[1]
                    if update_sql:
                        # oracle_insights.update_sql recognizes BEGIN... blocks
                        update_sql(f"BEGIN {pv}; END;")
            except Exception:
                # logger.exception("Failed to execute PROC %s for table %s", proc_val, schema_table)
                pass

        rows_inserted = len(data)

        # Write structured success log (same format as main.log_query)
        try:
            logging.info(json.dumps({
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "file_name": logical_filename,
                "query_identifier": cfg.get("query_identifier", ""),
                "query": insert_sql if 'insert_sql' in locals() else cfg.get("query_text", ""),
                "parameters": f"CSV rows, rows_inserted={rows_inserted}",
                "status": "success",
                "execution_time_ms": None,
                "bulk": True,
                "rows_affected": rows_inserted
            }))
        except Exception:
            # ignore logging failures
            pass
    except Exception as e:
        # logger.exception("Insert or PROC failed: %s", e)
        # Write structured error into query log (same schema as main.log_query)
        try:
            logging.info(json.dumps({
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "file_name": logical_filename,
                "query_identifier": cfg.get("query_identifier", ""),
                "query": cfg.get("query_text") or "",
                "parameters": "CSV rows",
                "status": "error",
                "error_message": str(e)
            }))
        except Exception:
            # logger.exception("Failed to write error query log")
            pass

        # Update log row with error indicator if possible
        try:
            if update_sql:
                err_msg = str(e).replace("'", "''")
                update_sql(f"UPDATE RPA_INPUTS.EXCEL_LOAD_TO_ORACLE SET SV6 = 'ERROR', SV7 = '{err_msg[:4000]}' WHERE UV = '{uv}'")
        except Exception:
            # logger.exception("Failed to update error status in log row")
            pass
        return {"status": "error", "message": "DB insert or PROC failed", "uv": uv}

    # Step 9: Mark processed
    try:
        if update_sql:
            update_sql(f"UPDATE RPA_INPUTS.EXCEL_LOAD_TO_ORACLE SET PROCESSINGTIME = systimestamp WHERE UV = '{uv}'")
    except Exception:
        # logger.exception("Failed to mark PROCESSINGTIME for UV=%s", uv)
        pass

    # Step 10: Persist processed file optionally
    try:
        if not IS_FILELOADER_TEST:
            processed_dir = os.path.join(os.path.dirname(__file__), 'processed')
            os.makedirs(processed_dir, exist_ok=True)
            tsfile = datetime.datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
            safe_name = f"{logical_filename}_{tsfile}.csv"
            out_path = os.path.join(processed_dir, safe_name)
            with open(out_path, 'wb') as fh:
                fh.write(upload_file.file.read())
    except Exception:
        # logger.exception("Failed to persist processed file for UV=%s", uv)
        pass

    # Step 11: return success
    return {"status": "success", "uv": uv, "rows_inserted": rows_inserted, "table": schema_table}
