from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
# sqlite3 was used previously for local DB; replaced by SQLAlchemy engine for generic DB support
from sqlalchemy import text
from db import get_engine, test_connection
import jwt
import tempfile
from file_loader_api.common_lib.executive_mailer import send_email
import json
import uvicorn
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import io
from datetime import datetime, timedelta
import time
import os
import uuid
from passlib.context import CryptContext
from fastapi.responses import JSONResponse
from file_loader_api.file_loader_service import process_file_loader_job

app = FastAPI(title="FAPI_QExec")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Load API keys
with open("api_keys.json", "r", encoding="utf-8") as f:
    _KEYS = json.load(f).get("api_keys", [])

API_KEY_HEADER = APIKeyHeader(name="x-api-key", auto_error=False)


def authenticate(api_key_header: str = Depends(API_KEY_HEADER), authorization: str = Header(None)):
    """Authenticate using Bearer JWT token (preferred) or x-api-key fallback.

    Returns decoded JWT payload or API key string on success, otherwise raises 401.
    """
    # Try Authorization: Bearer <token>
    if authorization:
        try:
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
                secret = os.getenv("JWT_SECRET", "change_me")
                algo = os.getenv("JWT_ALGORITHM", "HS256")
                payload = jwt.decode(token, secret, algorithms=[algo])
                # No server-side revocation: rely solely on token expiry (exp claim)
                return payload
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid JWT token: {e}")

    # Fallback to API key header if provided
    if api_key_header in _KEYS:
        return api_key_header

    raise HTTPException(status_code=401, detail="Invalid or missing credentials")


# Note: token_blacklist / server-side revocation removed. Tokens are invalidated
# only by their expiration (exp claim). Logout is a client-side operation.

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


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None
    roles: Optional[str] = None


# SQL Type Detection
def detect_sql_type(query: str) -> str:
    q = query.strip().lower()
    # Support CTEs that start with WITH (treat as SELECT)
    if q.startswith("with"):
        return "select"
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
        res = conn.execute(text("SELECT query_text, bind_keys, table_name, proc, load_action, email FROM config_table WHERE filename = :f AND query_identifier = :q"), {"f": filename, "q": query_identifier})
        row = res.fetchone()
        if not row:
            return None
        query_text, bind_keys, table_name_col, proc_col, load_action_col, email_col = row[0], row[1], row[2], row[3], row[4], row[5] if len(row) > 5 else None

        cfg = {"query_text": query_text, "bind_keys": bind_keys, "TABLE_NAME": table_name_col, "PROC": proc_col, "LOAD_ACTION": load_action_col, "email": email_col}
        return cfg


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


def _send_result_via_email(cfg: Dict[str, Any], job: Dict[str, Any], result: Dict[str, Any]):
    """Create a temp CSV with the result and send it to cfg['email'] if present.

    This is best-effort: exceptions are logged but not raised to the caller.
    """
    try:
        email_addr = cfg.get("email")
        if not email_addr:
            return

        tf = tempfile.NamedTemporaryFile(delete=False, mode="w", newline="", encoding="utf-8", suffix=".csv")
        try:
            with tf as tmpf:
                data = result.get("data", {})
                cols = data.get("columns") or []
                rows = data.get("rows") or []
                writer = csv.writer(tmpf)
                if cols:
                    writer.writerow(cols)
                    for r in rows:
                        writer.writerow(["" if v is None else v for v in r])
                else:
                    writer.writerow(["job_filename", "query_identifier", "status", "row_count", "message"])
                    writer.writerow([job.get("filename"), job.get("query_identifier"), result.get("status"), data.get("row_count"), data.get("message")])

            # send email
            try:
                subject = f"Bulk job result: {job.get('filename')}:{job.get('query_identifier')}"
                body = f"Bulk job completed. See attached CSV for details."
                send_email(to=email_addr, cc="", subject=subject, body=body, attach_path=tf.name)
                logging.info("Bulk job email sent to %s for %s:%s — attachment=%s", email_addr, job.get('filename'), job.get('query_identifier'), tf.name)
            except Exception as e:
                logging.exception("Failed to send bulk job email to %s: %s", email_addr, e)
        finally:
            try:
                os.unlink(tf.name)
            except Exception:
                pass
    except Exception:
        logging.exception("Unexpected error preparing/sending bulk job email for %s:%s", job.get("filename"), job.get("query_identifier"))


@app.post("/executeConfig")
def execute_config(req: ConfigExecuteRequest, auth=Depends(authenticate)):
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
    result = run_generic_query(cfg["query_text"], [], options, metadata) if not named_params else run_generic_query(cfg["query_text"], named_params, options, metadata)

    # If the configuration row contains an email address, send the result as a CSV attachment
    try:
        email_addr = cfg.get("email")
        if email_addr and result and result.get("status") == "success":
            # Create a temp CSV file with results (rows + columns) or a short summary
            tf = tempfile.NamedTemporaryFile(delete=False, mode="w", newline="", encoding="utf-8", suffix=".csv")
            try:
                with tf as tmpf:
                    data = result.get("data", {})
                    cols = data.get("columns") or []
                    rows = data.get("rows") or []
                    writer = csv.writer(tmpf)
                    if cols:
                        writer.writerow(cols)
                        for r in rows:
                            # ensure each row is a flat sequence
                            writer.writerow(["" if v is None else v for v in r])
                    else:
                        # write a short summary when no tabular data
                        writer.writerow(["message", "row_count"])
                        writer.writerow([data.get("message"), data.get("row_count")])

                # send email with the temp file attached
                try:
                    send_email(to=email_addr, cc="", subject=f"Query result: {req.filename}:{req.query_identifier}", body="Please find attached the query result.", attach_path=tf.name)
                    logging.info("Email sent to %s for config %s:%s — attachment=%s", email_addr, req.filename, req.query_identifier, tf.name)
                except Exception as e:
                    logging.exception("send_email failed: %s", e)
            finally:
                try:
                    os.unlink(tf.name)
                except Exception:
                    pass
    except Exception:
        logging.exception("Error while preparing or sending email for config %s:%s", req.filename, req.query_identifier)

    return result


@app.post("/login")
def login(req: LoginRequest):
    """Authenticate user with username/password and return JWT token."""
    engine = get_engine()
    with engine.connect() as conn:
        res = conn.execute(text("SELECT username, password, roles FROM users WHERE username = :u"), {"u": req.username})
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        db_username, db_password, db_roles = row[0], row[1], row[2]
        # verify password
        try:
            if not pwd_context.verify(req.password, db_password):
                raise HTTPException(status_code=401, detail="Invalid username or password")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid username or password")

    # create token
    secret = os.getenv("JWT_SECRET", "change_me")
    algo = os.getenv("JWT_ALGORITHM", "HS256")
    expires_minutes = int(os.getenv("JWT_EXPIRES_MINUTES", "60"))
    exp = datetime.utcnow() + timedelta(minutes=expires_minutes)
    jti = str(uuid.uuid4())
    payload = {"sub": db_username, "exp": exp, "jti": jti, "roles": db_roles}
    token = jwt.encode(payload, secret, algorithm=algo)

    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat() + "Z"}


@app.post("/logout")
def logout(auth=Depends(authenticate)):
    """Logout endpoint — no server-side token revocation is performed.

    Clients should discard the token. Tokens remain valid until their expiry.
    """
    # auth is the decoded payload; log the logout attempt for auditing
    try:
        subj = auth.get("sub") if isinstance(auth, dict) else None
        logging.info("Logout called for subject=%s", subj)
    except Exception:
        logging.exception("Logout called but failed to read subject")
    return {"status": "success", "message": "Logged out (token remains valid until expiry)"}


@app.post("/registeruser")
def register_user(req: RegisterRequest, api_key: str = Depends(API_KEY_HEADER)):
    """Register a new user. Requires a valid `x-api-key` header from api_keys.json.

    The endpoint hashes the provided password and stores the user in the `users` table.
    Returns created user id on success.
    """
    if not api_key or api_key not in _KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")

    engine = get_engine()
    try:
        with engine.connect() as conn:
            # Check username uniqueness
            existing = conn.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": req.username}).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists")

            # Compute next id
            row = conn.execute(text("SELECT MAX(id) FROM users")).fetchone()
            next_id = (row[0] or 0) + 1

            pw_hash = pwd_context.hash(req.password)

            trans = conn.begin()
            try:
                conn.execute(
                    text("INSERT INTO users (id, username, password, email, phone, roles) VALUES (:id, :u, :p, :e, :ph, :r)"),
                    {"id": next_id, "u": req.username, "p": pw_hash, "e": req.email, "ph": req.phone, "r": req.roles},
                )
                trans.commit()
            except Exception:
                try:
                    trans.rollback()
                except Exception:
                    pass
                raise

    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Failed to register user: %s", e)
        raise HTTPException(status_code=500, detail="Failed to register user")

    logging.info("User registered username=%s id=%s", req.username, next_id)
    return {"status": "success", "user_id": next_id}


@app.post("/executeConfigBulk")
def execute_config_bulk(
    # New contract: accept multiple jobs and multiple files
    # jobs: JSON string, list of objects {"filename":..., "query_identifier":..., "chunk_size": <int>}
    jobs: str = Form(...),
    csv_files: List[UploadFile] = File(...),
    bulk_insert: bool = Form(...),
    parallel: bool = Form(False),
    file_loader: bool = Form(False),
    api_key: str = Depends(authenticate),
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
                    # submit a wrapper that returns (job, cfg, result)
                    futures.append(ex.submit(lambda c=cfg, u=upload, j=job: (j, c, process_file_loader_job(c, u, j.get("filename")))))
                for f in as_completed(futures):
                    job_obj, cfg_obj, res_obj = f.result()
                    # attempt to email if configured
                    try:
                        if cfg_obj and cfg_obj.get("email") and res_obj and res_obj.get("status") == "success":
                            _send_result_via_email(cfg_obj, job_obj, res_obj)
                    except Exception:
                        logging.exception("Error sending email for file_loader job %s:%s", job_obj.get("filename"), job_obj.get("query_identifier"))
                    results.append(res_obj)
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
                res = process_file_loader_job(cfg, upload, job.get("filename"))
                try:
                    if cfg and cfg.get("email") and res and res.get("status") == "success":
                        _send_result_via_email(cfg, job, res)
                except Exception:
                    logging.exception("Error sending email for file_loader job %s:%s", job.get("filename"), job.get("query_identifier"))
                results.append(res)
        return JSONResponse(content={"results": results})

    # If file_loader flag is not set, fall back to original generic CSV-to-config bulk insert
    # process jobs either sequentially or in parallel using existing _process_job helper
    if parallel:
        # run in ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(jobs_list))) as ex:
            futures = []
            for job, upload in zip(jobs_list, csv_files):
                # submit wrapper returning (job, result)
                futures.append(ex.submit(lambda jb=job, up=upload: (jb, _process_job(jb, up))))
            for f in as_completed(futures):
                job_obj, res_obj = f.result()
                # attempt to send email if configured for this job
                try:
                    cfg = fetch_config_query(job_obj.get("filename"), job_obj.get("query_identifier"))
                    if cfg and cfg.get("email") and res_obj and res_obj.get("status") == "success":
                        _send_result_via_email(cfg, job_obj, res_obj)
                except Exception:
                    logging.exception("Error sending email for bulk job %s:%s", job_obj.get("filename"), job_obj.get("query_identifier"))
                results.append(res_obj)
    else:
        for job, upload in zip(jobs_list, csv_files):
            res = _process_job(job, upload)
            try:
                cfg = fetch_config_query(job.get("filename"), job.get("query_identifier"))
                if cfg and cfg.get("email") and res and res.get("status") == "success":
                    _send_result_via_email(cfg, job, res)
            except Exception:
                logging.exception("Error sending email for bulk job %s:%s", job.get("filename"), job.get("query_identifier"))
            results.append(res)

    return JSONResponse(content={"results": results})


# Final API Endpoint
@app.post("/executeQuery")
def execute_query(req: GenericQueryRequest, auth=Depends(authenticate)):
    return run_generic_query(req.query, req.parameters, req.options, req.metadata)

@app.get("/getallItems")
def get_all_items(auth=Depends(authenticate)):
    query = "SELECT * FROM items"
    options = QueryOptions(readonly=True, track_performance=True)
    metadata = QueryMetadata(file_name="getallItems", query_identifier="GET_ALL_ITEMS")
    return run_generic_query(query, [], options, metadata)


class TokenRequest(BaseModel):
    subject: str
    expires_minutes: Optional[int] = 60


@app.post("/token")
def create_token(req: TokenRequest, api_key: str = Depends(API_KEY_HEADER)):
    """Create a short-lived JWT. Requires a valid x-api-key header from api_keys.json.

    Request body: {"subject": "user@example.com", "expires_minutes": 60}
    Returns: {"access_token": "...", "token_type": "bearer", "expires_at": "...Z"}
    """
    if not api_key or api_key not in _KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")

    secret = os.getenv("JWT_SECRET", "change_me")
    algo = os.getenv("JWT_ALGORITHM", "HS256")
    exp = datetime.utcnow() + timedelta(minutes=(req.expires_minutes or 60))
    payload = {"sub": req.subject, "exp": exp}
    token = jwt.encode(payload, secret, algorithm=algo)

    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat() + "Z"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
