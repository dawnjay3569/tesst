# File Loader API helper

This folder contains the file loader helper used by the `/executeConfigBulk` endpoint when the `file_loader` flag is set to true.

Files:

- `file_loader_service.py` — Implements the in-memory file loader flow (steps 6–14). Reuses existing helpers in `file_loader` and `common_lib` when available.
- `sample_fileloader_input.csv` — Example CSV to test uploads. Header names should match configured `bind_keys` in `config_table`.

Sample multipart/form-data request (curl):

```bash
curl -X POST "http://127.0.0.1:8000/executeConfigBulk" \
  -H "x-api-key: testkey123" \
  -F 'jobs=[{"filename":"ItemsFile","query_identifier":"INSERT_ITEMS_BULK"}]' \
  -F "csv_files=@sample_fileloader_input.csv;type=text/csv" \
  -F "bulk_insert=true" \
  -F "file_loader=true"
```

Sample success response:

```json
{
  "results": [
    {
      "status": "success",
      "uv": "ItemsFile_20251031...csv",
      "rows_inserted": 3,
      "table": "ITEMS"
    }
  ]
}
```

Notes:
- The service attempts to reuse `insert_to_oi_rtqm`, `update_sql`, and `update_sql_oi_rtqm` from the repository. If those helpers are not available the service falls back to best-effort behavior and logs warnings.
- The `file_loader` flag controls whether the file-loader behavior (per-job processing using the DB config) is executed. If `file_loader=false` the endpoint keeps its original generic CSV-to-config behaviour.
