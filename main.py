from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
# sqlite3 was used previously for local DB; replaced by SQLAlchemy engine for generic DB support
from sqlalchemy import text
from db import get_engine, test_connection
import json
import uvicorn
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import io
from datetime import datetime
import time
import os
from fastapi.responses import JSONResponse
from file_loader_api.file_loader_service import process_file_loader_job

app = FastAPI(title="FAPI_QExec")

# Load API keys
with open("api_keys.json", "r", encoding="utf-8") as f:
    _KEYS = json.load(f).get("api_keys", [])

API_KEY_HEADER = APIKeyHeader(name="x-api-key", auto_error=False)

def get_api_key(api_key_header: str = Depends(API_KEY_HEADER)):
    if api_key_header in _KEYS:
        return api_key_header
    raise HTTPException(status_code=401, detail="Invalid or missing API Key")

# Setup Logging
LOG_FILE = "query_logs.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(message)s'
)

def log_query(details: Dict[str, Any]):
    log_entry = json.dumps(details)
    logging.info(log_entry)


# Startup: log which DB dialect is configured and a quick connection test
@app.on_event("startup")
async def _log_db_on_startup():
    try:
        info = test_connection()
        dialect = info.get("dialect")
        ok = info.get("ok")
        msg = info.get("message")
        line = f"DB startup check: dialect={dialect}, ok={ok}, message={msg}"
        print(line)
        logging.info(line)
    except Exception as e:
        logging.exception("DB startup check failed: %s", e)


# Updated Request Model
class QueryOptions(BaseModel):
    readonly: Optional[bool] = False
    multi_statement: Optional[bool] = False
    track_performance: Optional[bool] = True
    allow_transaction: Optional[bool] = False

class QueryMetadata(BaseModel):
    file_name: Optional[str] = None
    query_identifier: Optional[str] = None

class GenericQueryRequest(BaseModel):
    query: str
    parameters: Optional[List[Any]] = []
    options: Optional[QueryOptions] = QueryOptions()
    metadata: Optional[QueryMetadata] = QueryMetadata()


class ConfigExecuteRequest(BaseModel):
    filename: str
    query_identifier: str
    bind_variables: Dict[str, Any]


# SQL Type Detection
def detect_sql_type(query: str) -> str:
    q = query.strip().lower()
    if q.startswith("select"):
        return "select"
    elif q.startswith("insert"):
        return "insert"
    elif q.startswith("update"):
        return "update"
    elif q.startswith("delete"):
        return "delete"
    elif q.startswith("create") or q.startswith("drop") or q.startswith("alter"):
        return "ddl"
    elif q.startswith("show"):
        return "show"
    elif q.startswith("explain"):
        return "explain"
    else:
        return "other"


# Query Runner
def run_generic_query(query: str, parameters: List[Any], options: QueryOptions, metadata: QueryMetadata):
    sql_type = detect_sql_type(query)
    start_time = time.time()

    if options.readonly and sql_type != "select":
        raise HTTPException(status_code=403, detail="Read-only mode: Only SELECT queries allowed.")

    if not options.multi_statement and ";" in query.strip().replace(";", "", 1):
        raise HTTPException(status_code=400, detail="Multiple statements not allowed.")

    engine = get_engine()
    conn = engine.connect()

    try:
        # Detect bulk executemany: parameters is a list and its first element is a sequence or mapping
        params = parameters or []
        is_bulk = isinstance(params, list) and len(params) > 0 and isinstance(params[0], (list, tuple, dict))

        if is_bulk and sql_type in ["insert", "update", "delete"]:
            # Bulk operation - use executemany via SQLAlchemy execution of text()
            trans = conn.begin()
            try:
                conn.execute(text(query), params)
                # For executemany, SQLAlchemy may not provide rowcount uniformly; use len(params)
                row_count = len(params)
                last_insert_id = None
                trans.commit()

                execution_time_ms = int((time.time() - start_time) * 1000) if options.track_performance else None

                # Log bulk query
                log_query({
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "file_name": metadata.file_name,
                    "query_identifier": metadata.query_identifier,
                    "query": query,
                    "parameters": params,
                    "status": "success",
                    "execution_time_ms": execution_time_ms,
                    "bulk": True,
                    "rows_affected": row_count
                })

                data = {
                    "columns": [],
                    "rows": [],
                    "row_count": row_count,
                    "last_insert_id": last_insert_id,
                    "message": f"{row_count} row(s) affected"
                }

                return {
                    "status": "success",
                    "type": sql_type,
                    "data": data,
                    "execution_time_ms": execution_time_ms,
                    "metadata": {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "file_name": metadata.file_name,
                        "query_identifier": metadata.query_identifier
                    },
                    "error": None
                }
            except Exception:
                trans.rollback()
                raise

        # Single execute path
        # For DML/DDL use an explicit transaction so changes are committed across dialects
        if sql_type in ["insert", "update", "delete", "ddl"]:
            trans = conn.begin()
            try:
                result = conn.execute(text(query), params if params else {})
                trans.commit()
            except Exception:
                try:
                    trans.rollback()
                except Exception:
                    pass
                raise
        else:
            result = conn.execute(text(query), params if params else {})

        rows = []
        row_count = None
        columns = []
        if sql_type in ["select", "show", "explain"]:
            fetched = result.fetchall()
            rows = [list(r) for r in fetched]
            row_count = len(rows)
            columns = result.keys()
        else:
            try:
                row_count = result.rowcount
            except Exception:
                row_count = None

        last_insert_id = None
        # Attempt to obtain a last-insert id in a dialect-agnostic way where supported
        try:
            # Some DBAPI results expose lastrowid
            last_insert_id = getattr(result, "lastrowid", None)
            if last_insert_id is None:
                # SQLAlchemy Result may expose inserted_primary_key for INSERTs
                try:
                    ipk = getattr(result, "inserted_primary_key", None)
                    if ipk:
                        last_insert_id = ipk[0]
                except Exception:
                    last_insert_id = None
            if last_insert_id is not None:
                last_insert_id = int(last_insert_id)
        except Exception:
            last_insert_id = None

        data = {
            "columns": list(columns) if columns else [],
            "rows": rows,
            "row_count": row_count,
            "last_insert_id": last_insert_id,
            "message": f"{row_count} row(s) affected" if sql_type in ["insert", "update", "delete"] else "Query executed successfully"
        }

        execution_time_ms = int((time.time() - start_time) * 1000) if options.track_performance else None

        # Log query
        log_query({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "file_name": metadata.file_name,
            "query_identifier": metadata.query_identifier,
            "query": query,
            "parameters": parameters,
            "status": "success",
            "execution_time_ms": execution_time_ms
        })

        return {
            "status": "success",
            "type": sql_type,
            "data": data,
            "execution_time_ms": execution_time_ms,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "file_name": metadata.file_name,
                "query_identifier": metadata.query_identifier
            },
            "error": None
        }

    except Exception as e:
        # Log error
        log_query({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "file_name": metadata.file_name,
            "query_identifier": metadata.query_identifier,
            "query": query,
            "parameters": parameters,
            "status": "error",
            "error_message": str(e)
        })

        return {
            "status": "error",
            "type": sql_type,
            "data": {},
            "error": {
                "code": type(e).__name__,
                "message": str(e),
                "sql_state": None
            },
            "metadata": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "file_name": metadata.file_name,
                "query_identifier": metadata.query_identifier
            }
        }

    finally:
        try:
            conn.close()
        except Exception:
            pass


def fetch_config_query(filename: str, query_identifier: str):
    engine = get_engine()
    with engine.connect() as conn:
        res = conn.execute(text("SELECT query_text, bind_keys FROM config_table WHERE filename = :f AND query_identifier = :q"), {"f": filename, "q": query_identifier})
        row = res.fetchone()
        if not row:
            return None
        return {"query_text": row[0], "bind_keys": row[1]}


def validate_and_prepare_bind(bind_keys_csv: Optional[str], bind_variables: Dict[str, Any]):
    # bind_keys in config is comma separated list
    if not bind_keys_csv:
        expected = []
    else:
        expected = [k.strip() for k in bind_keys_csv.split(",") if k.strip()]

    # Validate presence
    missing = [k for k in expected if k not in bind_variables]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing bind variables: {missing}")

    # Prepare dict for named parameters (:key or :name)
    named_params = {k: bind_variables.get(k) for k in expected}
    return named_params


@app.post("/executeConfig")
def execute_config(req: ConfigExecuteRequest, api_key: str = Depends(get_api_key)):
    cfg = fetch_config_query(req.filename, req.query_identifier)
    if not cfg:
        raise HTTPException(status_code=404, detail="Configuration not found for given filename and query_identifier")

    # Validate bind keys and prepare named params
    named_params = validate_and_prepare_bind(cfg.get("bind_keys"), req.bind_variables or {})

    # Execute the fetched query using run_generic_query infrastructure
    # We use the same options/metadata defaults
    options = QueryOptions()
    metadata = QueryMetadata(file_name=req.filename, query_identifier=req.query_identifier)

    # run_generic_query expects positional parameters list; but it accepts parameterized query too
    # We'll call the lower-level run to avoid re-parsing; use a tiny wrapper
    return run_generic_query(cfg["query_text"], [], options, metadata) if not named_params else run_generic_query(cfg["query_text"], named_params, options, metadata)


@app.post("/executeConfigBulk")
def execute_config_bulk(
    # New contract: accept multiple jobs and multiple files
    # jobs: JSON string, list of objects {"filename":..., "query_identifier":..., "chunk_size": <int>}
    jobs: str = Form(...),
    csv_files: List[UploadFile] = File(...),
    bulk_insert: bool = Form(...),
    parallel: bool = Form(False),
    file_loader: bool = Form(False),
    api_key: str = Depends(get_api_key),
):
    """
    Accepts multipart/form-data with fields:
      - filename (str)
      - query_identifier (str)
      - bulk_insert (bool) - must be true
      - csv_file - CSV file where header names match bind_keys
    """
    
    if not bulk_insert:
        raise HTTPException(status_code=400, detail="bulk_insert must be true for this endpoint")

    # default chunk size if not specified per-job
    chunk_size = 1000

    # parse jobs JSON
    try:
        jobs_list = json.loads(jobs)
        if not isinstance(jobs_list, list) or len(jobs_list) == 0:
            raise ValueError("jobs must be a non-empty JSON array")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid jobs JSON: {e}")

    if len(jobs_list) != len(csv_files):
        raise HTTPException(status_code=400, detail="Number of jobs must equal number of uploaded csv_files")

    # helper to process a single job (streaming, chunked)
    def _process_job(job: Dict[str, Any], upload: UploadFile):
        job_filename = job.get("filename")
        job_qid = job.get("query_identifier")
        job_chunk = int(job.get("chunk_size") or chunk_size)

        cfg = fetch_config_query(job_filename, job_qid)
        if not cfg:
            return {"status": "error", "detail": f"Config not found for {job_filename}:{job_qid}"}

        # Only allow INSERT queries for this bulk endpoint
        sql_type = detect_sql_type(cfg["query_text"])
        if sql_type != "insert":
            return {"status": "error", "detail": f"Config query must be INSERT for {job_filename}:{job_qid}"}

        bind_keys_csv = cfg.get("bind_keys")
        expected_keys = [k.strip() for k in bind_keys_csv.split(",") if k.strip()] if bind_keys_csv else []

        # stream the upload
        try:
            upload.file.seek(0)  # Ensure the file pointer is at the beginning
            reader = csv.DictReader(io.StringIO(upload.file.read().decode('utf-8-sig')))
        except Exception as e:
            return {"status": "error", "detail": f"Failed to read CSV for {job_filename}:{job_qid}: {e}"}

        if not reader.fieldnames:
            return {"status": "error", "detail": "CSV file has no header row"}

        missing_cols = [k for k in expected_keys if k not in reader.fieldnames]
        if missing_cols:
            return {"status": "error", "detail": f"CSV missing expected columns: {missing_cols}"}

        engine = get_engine()
        conn = engine.connect()
        total_rows = 0
        last_insert_id = None
        start_time = time.time()
        chunk_count = 0

        try:
            trans = conn.begin()
            chunk = []
            for i, row in enumerate(reader):
                params = {k: (row.get(k) if row.get(k) != '' else None) for k in expected_keys}
                chunk.append(params)

                if len(chunk) >= max(1, job_chunk):
                    # executemany via SQLAlchemy: pass list of dicts
                    conn.execute(text(cfg["query_text"]), chunk)
                    rows_affected = len(chunk)
                    total_rows += rows_affected
                    chunk_count += 1
                    chunk = []

            if len(chunk) > 0:
                conn.execute(text(cfg["query_text"]), chunk)
                rows_affected = len(chunk)
                total_rows += rows_affected
                chunk_count += 1

            trans.commit()
            execution_time_ms = int((time.time() - start_time) * 1000)

            # We do not attempt a dialect-specific last-insert lookup here. If
            # callers need generated IDs for Oracle, use INSERT ... RETURNING
            # in the configured query or perform a SELECT in the query itself.
            last_insert_id = None

            log_query({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "file_name": job_filename,
                "query_identifier": job_qid,
                "query": cfg["query_text"],
                "parameters": f"CSV rows, chunks={chunk_count}",
                "status": "success",
                "execution_time_ms": execution_time_ms,
                "bulk": True,
                "rows_affected": total_rows
            })

            return {
                "status": "success",
                "type": sql_type,
                "data": {
                    "columns": [],
                    "rows": [],
                    "row_count": total_rows,
                    "last_insert_id": last_insert_id,
                    "message": f"{total_rows} row(s) affected in {chunk_count} chunks"
                },
                "execution_time_ms": execution_time_ms,
                "metadata": {"file_name": job_filename, "query_identifier": job_qid},
                "error": None
            }

        except Exception as e:
            try:
                trans.rollback()
            except Exception:
                pass
            log_query({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "file_name": job_filename,
                "query_identifier": job_qid,
                "query": cfg["query_text"],
                "status": "error",
                "error_message": str(e)
            })
            return {"status": "error", "detail": f"Bulk insert failed: {e}"}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # process jobs either using fileloader flow or the generic CSV-to-config flow
    results = []
    if file_loader:
        # Use the file loader service for each job. We fetch the config and pass it
        # to the service which implements steps 6-14 (in-memory CSV handling).
        if parallel:
            with ThreadPoolExecutor(max_workers=min(4, len(jobs_list))) as ex:
                futures = []
                for job, upload in zip(jobs_list, csv_files):
                    # fetch config for this job
                    cfg = fetch_config_query(job.get("filename"), job.get("query_identifier"))
                    if not cfg:
                        results.append({"status": "error", "detail": f"Config not found for {job.get('filename')}:{job.get('query_identifier')}"})
                        continue
                    # augment cfg with inferred schema_table from query_text when possible
                    try:
                        # naive extract of table name from INSERT INTO <table> (...)
                        import re
                        m = re.search(r"insert\s+into\s+([\w\.\"]+)", cfg.get("query_text", ""), re.IGNORECASE)
                        if m:
                            cfg["schema_table"] = m.group(1)
                    except Exception:
                        pass
                    futures.append(ex.submit(process_file_loader_job, cfg, upload, job.get("filename")))
                for f in as_completed(futures):
                    results.append(f.result())
        else:
            for job, upload in zip(jobs_list, csv_files):
                cfg = fetch_config_query(job.get("filename"), job.get("query_identifier"))
                if not cfg:
                    results.append({"status": "error", "detail": f"Config not found for {job.get('filename')}:{job.get('query_identifier')}"})
                    continue
                # infer schema_table from query_text
                try:
                    import re
                    m = re.search(r"insert\s+into\s+([\w\.\"]+)", cfg.get("query_text", ""), re.IGNORECASE)
                    if m:
                        cfg["schema_table"] = m.group(1)
                except Exception:
                    pass
                results.append(process_file_loader_job(cfg, upload, job.get("filename")))
        return JSONResponse(content={"results": results})

    # If file_loader flag is not set, fall back to original generic CSV-to-config bulk insert
    # process jobs either sequentially or in parallel using existing _process_job helper
    if parallel:
        # run in ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(jobs_list))) as ex:
            futures = []
            for job, upload in zip(jobs_list, csv_files):
                futures.append(ex.submit(_process_job, job, upload))
            for f in as_completed(futures):
                results.append(f.result())
    else:
        for job, upload in zip(jobs_list, csv_files):
            results.append(_process_job(job, upload))

    return JSONResponse(content={"results": results})


# Final API Endpoint
@app.post("/executeQuery")
def execute_query(req: GenericQueryRequest, api_key: str = Depends(get_api_key)):
    return run_generic_query(req.query, req.parameters, req.options, req.metadata)

@app.get("/getallItems")
def get_all_items(api_key: str = Depends(get_api_key)):
    query = "SELECT * FROM items"
    options = QueryOptions(readonly=True, track_performance=True)
    metadata = QueryMetadata(file_name="getallItems", query_identifier="GET_ALL_ITEMS")
    return run_generic_query(query, [], options, metadata)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
