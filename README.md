Options:
+---------------------+--------+---------+---------------------------------------------------------------+-------------------------------------------------------------+
|       Field         | Type   | Default | Purpose                                                       | When to Use                                                |
+---------------------+--------+---------+---------------------------------------------------------------+-------------------------------------------------------------+
| readonly            | bool   | false   | Allow only SELECT queries. Blocks INSERT/UPDATE/DELETE.       | Secure read-only APIs, reporting dashboards                |
| multi_statement     | bool   | false   | Allow multiple SQL statements in one query (with ;)           | Admin tools, batch operations                              |
| track_performance   | bool   | true    | Return execution time in ms (execution_time_ms in response)   | Performance tracking, debugging                            |
| allow_transaction   | bool   | false   | Run all queries in a DB transaction (all-or-nothing)          | Complex/bulk updates, rollback-safe operations             |
+---------------------+--------+---------+---------------------------------------------------------------+-------------------------------------------------------------+

Sample Request:
{
  "query": "SELECT * FROM users WHERE id = ?",
  "parameters": [1],
  "options": {
    "readonly": true,
    "multi_statement": false,
    "track_performance": true,
    "allow_transaction": false
  },
  "metadata": {
    "file_name": "users_module.sql",
    "query_identifier": "get_user_by_id"
  }
}


Sample Response:
{
  "status": "success",
  "type": "select",
  "data": {
    "columns": ["id", "name", "email"],
    "rows": [[1, "Ravi", "ravi@gmail.com"]],
    "row_count": 1,
    "last_insert_id": null,
    "message": "Query executed successfully"
  },
  "execution_time_ms": 4,
  "metadata": {
    "timestamp": "2025-10-07T15:00:00Z",
    "file_name": "users_module.sql",
    "query_identifier": "get_user_by_id"
  },
  "error": null
}

Error Example:
{
  "status": "error",
  "type": "delete",
  "data": {},
  "error": {
    "code": "HTTPException",
    "message": "Read-only mode: Only SELECT queries allowed.",
    "sql_state": null
  },
  "metadata": {
    "timestamp": "2025-10-07T15:30:00Z",
    "file_name": "Circuit format for IE_Phase3",
    "query_identifier": "USERNAME_CHANGE"
  }
}


Bulk operation
--------------

The API supports bulk inserts via `/executeConfigBulk` which accepts multipart/form-data fields.

Required form fields (multi-job aware):

- `jobs` (text) - JSON array describing one or more jobs (see below)
- `csv_files` (file) - one or more CSV files uploaded as repeated `csv_files` form fields; there must be exactly one CSV file per job and they are matched positionally
- `bulk_insert` (boolean) - must be true
- `parallel` (boolean) - optional; default false

Example CSV (header + rows):

id,name,description,price
101,ItemX,descX,9.99
102,ItemY,descY,19.50

Single-file example (use `csv_files` with one file):

```bash
curl -X POST "http://127.0.0.1:8000/executeConfigBulk" \
  -H "x-api-key: testkey123" \
  -F 'jobs=[{"filename":"ItemsFile","query_identifier":"INSERT_ITEMS_BULK"}]' \
  -F "bulk_insert=true" \
  -F "csv_files=@items.csv;type=text/csv"
```

Server expects `config_table` to have a row like:

```
filename: ItemsFile
query_identifier: INSERT_ITEMS_BULK
bind_keys: name,description,price
query_text: INSERT INTO items (name, description, price) VALUES (:name, :description, :price)
```

Sample success response (single or multi-job): the endpoint returns a top-level object with a `results` array containing one per-job result object. Each job result has the shape shown in the examples below.

Single-job response (wrapped in `results`):

```json
{
  "results": [
    {
      "status":"success",
      "type":"insert",
      "data":{
        "columns":[],
        "rows":[],
        "row_count":3,
        "last_insert_id": 45,
        "message":"3 row(s) affected"
      },
      "execution_time_ms": 45,
      "metadata":{
        "timestamp":"2025-10-14T..Z",
        "file_name":"ItemsFile",
        "query_identifier":"INSERT_ITEMS_BULK"
      },
      "error":null
    }
  ]
}
```

Validation rules
- If `bulk_insert` is not true the endpoint rejects the request.
- Number of `jobs` items must equal number of uploaded `csv_files`.
- CSV must include all columns listed in `bind_keys`.
- Empty values in CSV are treated as NULL.
- Each job's rows are inserted inside a transaction so that job's rows either all commit or none (other jobs are unaffected).

Server logging note: each job run (success or error) is written as a JSON line in `query_logs.log`. Bulk entries include `"bulk": true` and `"rows_affected": <n>`.

Example log line (single-job bulk insert):

```
{"timestamp":"2025-10-14T06:24:18.077972Z","file_name":"ItemsFile","query_identifier":"INSERT_ITEMS_BULK","query":"INSERT INTO items (name, description, price) VALUES (:name, :description, :price)","parameters":"CSV rows, chunks=1","status":"success","execution_time_ms":4,"bulk":true,"rows_affected":5}
```


Multi-job bulk upload (simple explanation)
----------------------------------------

Added a multi-job bulk endpoint so a single API call can submit several bulk-insert jobs at once. Each job points to a `filename` + `query_identifier` (these identify the stored INSERT query in `config_table`) and is paired with one uploaded CSV file. The server processes each job (streaming CSV, chunking executemany) and returns an aggregated result.

How it works (simple):
- Client sends a multipart/form-data POST to `/executeConfigBulk`.
- The request includes a `jobs` form field (JSON array) describing each job and one or more `csv_files` attachments — there must be exactly one CSV file per job and they are matched positionally.
- The server validates each job's config exists and that the stored query is an INSERT. It then streams the CSV, validates header columns match `bind_keys`, and uses `executemany` in chunks to load rows inside a transaction.
- The response contains a `results` array with one entry per job describing success/failure, rows affected, timing and any error messages.

Jobs JSON format (example):

```
[ 
  { "filename": "ItemsFile", "query_identifier": "INSERT_ITEMS_BULK", "chunk_size": 100 },
  { "filename": "OtherFile", "query_identifier": "INSERT_OTHER_BULK" }
]
```

Fields:
- `filename` (string): the filename key used to look up the query in `config_table`.
- `query_identifier` (string): the identifier used to look up the query.
- `chunk_size` (optional int): number of rows per executemany chunk (default: 1000 if not provided).

Example curl (two jobs, two files):

```bash
curl -v -X POST "http://127.0.0.1:8000/executeConfigBulk" \
  -H "x-api-key: testkey123" \
  -F 'jobs=[{"filename":"ItemsFile","query_identifier":"INSERT_ITEMS_BULK","chunk_size":100}]' \
  -F "bulk_insert=true" \
  -F "parallel=false" \
  -F "csv_files=@/full/path/to/csv1.csv;type=text/csv" \
  -F "csv_files=@/full/path/to/csv2.csv;type=text/csv"
```

Postman note: use Body → form-data. Add a Text field named `jobs` with the JSON array text. Upload CSV files using the `csv_files` key as File entries (repeat `csv_files` for each file).

Sample response (successful job):

```json
{
  "results": [
    {
      "status": "success",
      "type": "insert",
      "data": {
        "columns": [],
        "rows": [],
        "row_count": 5,
        "last_insert_id": 123,
        "message": "5 row(s) affected in 1 chunks"
      },
      "execution_time_ms": 40,
      "metadata": { "file_name": "ItemsFile", "query_identifier": "INSERT_ITEMS_BULK" },
      "error": null
    }
  ]
}
```

Important caveats and tips
- The endpoint only accepts INSERT queries for bulk jobs — other SQL types are rejected for safety.
- SQLite has limited write concurrency. Setting `parallel=true` may not improve throughput with SQLite; consider a server DB (Postgres/MySQL) for high-concurrency bulk loads.
- The server streams CSV and chunks rows to avoid high memory usage. For extremely large files you may want to increase chunk_size or upload files in parts.
- If a job fails, that job is rolled back (it does not affect other jobs). The response includes success/error per job.

SQLite-specific notes and examples
--------------------------------

If you run the app with SQLite (default when `DATABASE_URL` is not set), a few small differences apply:

- The project will use a local `data.db` file in the project root.
- `last_insert_id` for single inserts and bulk inserts is retrieved via `last_insert_rowid()` when available.
- SQLite serializes writes; setting `parallel=true` will not speed up bulk inserts — keep `parallel=false` for SQLite.

PowerShell example (single CSV upload using the provided helper):

```powershell
# runs upload_bulk.ps1 which posts to /executeConfigBulk
.\upload_bulk.ps1 -ApiKey 'testkey123' -CsvPath '.\sample1.csv'
```

Curl example (single job, SQLite):

```bash
curl -v -X POST "http://127.0.0.1:8000/executeConfigBulk" \
  -H "x-api-key: testkey123" \
  -F 'jobs=[{"filename":"ItemsFile","query_identifier":"INSERT_ITEMS_BULK","chunk_size":100}]' \
  -F "bulk_insert=true" \
  -F "csv_files=@./sample1.csv;type=text/csv" \
  -F "parallel=false"
```

Sample successful job result (SQLite):

```json
{
  "results": [
    {
      "status": "success",
      "type": "insert",
      "data": {
        "columns": [],
        "rows": [],
        "row_count": 3,
        "last_insert_id": 12,
        "message": "3 row(s) affected in 1 chunks"
      },
      "execution_time_ms": 45,
      "metadata": { "file_name": "ItemsFile", "query_identifier": "INSERT_ITEMS_BULK" },
      "error": null
    }
  ]
}
```

Validation recap (SQLite)
- Ensure `csv_files` header names match `bind_keys` declared in `config_table`.
- Keep chunk_size modest (100-1000) to avoid large memory spikes.


Environment and Oracle notes
----------------------------

This project now supports configuring the database connection via a `.env` file. An example is provided in `.env.example`. For Oracle, populate the `.env` file with your credentials or set `DATABASE_URL`.

To initialize the Oracle database (create tables and insert sample rows), run:

```bash
python db_init.py
```

Note: `db_init.py` executes `init_db.sql` using SQLAlchemy and assumes the `.env` contains the correct connection values. Do not commit your real `.env` with secrets — use `.env.example` for sharing.

Additional recent changes
------------------------

- JWT authentication: the API accepts a Bearer JWT in the `Authorization` header (preferred) or the legacy `x-api-key` header as a fallback. Configure `JWT_SECRET` and optionally `JWT_ALGORITHM` (default HS256) via environment variables.

- CTE support: queries that start with `WITH` (common table expressions) are treated as `SELECT` queries and accept named parameters like other parameterized queries.

- Email notification: `config_table` now supports an `email` column. When the `/executeConfig` endpoint runs a configured query and the config row contains an email address, the server will generate a temporary CSV file of the result (or a short summary) and send it to that address using the included `executive_mailer` helper. The temp file is removed after sending.

- Bulk-job email notifications: `/executeConfigBulk` also sends per-job email notifications when the corresponding `config_table` row contains an `email` address. Each successful job will generate a temporary CSV summary/rows file and send it as an attachment to the configured address.


Authentication and user management (login/logout)
------------------------------------------------

- Database tables: `users` was added to `init_db.sql`. The `users` table stores `username`, hashed `password`, `email`, `phone`, and `roles`.

- Login: POST `/login` accepts JSON {"username": "<user>", "password": "<password>"} and returns a JWT access token (Bearer). The token `exp` uses `JWT_EXPIRES_MINUTES` environment variable (default 60).

- Logout: POST `/logout` (Bearer token required) is provided as a convenience auditing endpoint but does not perform server-side token revocation. Clients should discard tokens on logout; tokens remain valid until their `exp`.

- Protected endpoints: All primary endpoints (`/executeQuery`, `/executeConfig`, `/executeConfigBulk`, etc.) validate the presented token signature and expiry. If you prefer API-key based access, you can still pass `x-api-key` as a fallback.

Creating a user (example)
-------------------------

The repository does not expose a public user-creation endpoint by default. To create a user you can insert a row into `users` using a small Python helper to hash the password correctly. Example:

```python
from passlib.context import CryptContext
from db import get_engine
from sqlalchemy import text
pwd = CryptContext(schemes=["bcrypt"]).hash("MyS3cret")
engine = get_engine()
with engine.connect() as conn:
  conn.execute(text("INSERT INTO users (id, username, password, email, phone, roles) VALUES (:id, :u, :p, :e, :ph, :r)"), {"id": 1, "u": "alice", "p": pwd, "e":"alice@example.com", "ph":"+1000000000", "r":"admin"})
```

After creating the user, call the `/login` endpoint to obtain a JWT.


New endpoints and behaviors (recent additions)
---------------------------------------------

- GET `/profile/{username}` (protected): returns the user profile for the given username (id, username, email, phone, roles, created_at) but does NOT return the password. Requires a valid Bearer token or a valid API key; normal users may only retrieve their own profile unless they have the `admin` role.

- POST `/forgot_password` (protected by `x-api-key`): accepts JSON {"username": "...", "email": "..."}. If the username exists and the email matches the stored address, the API generates a random 8-character temporary password, hashes and stores it in the `users` table, and emails the temporary password to the user. The user must login and change the password after first use.

- Token expiry and human-readable times: JWT tokens now include an `exp` numeric timestamp and an `exp_human` ISO-8601 string in the payload. Responses that return `expires_at` use the human-readable ISO string. When a token has expired the API responds with HTTP 401 and the message "Token expired, please re-login".

- Rotating logs: server logging now uses a rotating file handler. Configure `LOG_FILE`, `LOG_MAX_BYTES`, and `LOG_BACKUP_COUNT` via environment variables to control rotation. Default: `query_logs.log`, 5MB max, 5 backups.

These changes were added to improve observability, user self-service flows, and production readiness.


