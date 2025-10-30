-- SQLite init SQL (idempotent where possible)

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS config_table (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    query_identifier TEXT NOT NULL,
    query_text TEXT NOT NULL,
    bind_keys TEXT,
    UNIQUE(filename, query_identifier)
);

-- idempotent sample config row for bulk insert into items
INSERT INTO config_table (filename, query_identifier, query_text, bind_keys)
SELECT 'ItemsFile', 'INSERT_ITEMS_BULK', 'INSERT INTO items (name, description) VALUES (:name, :description)', 'name,description'
WHERE NOT EXISTS (
    SELECT 1 FROM config_table WHERE filename='ItemsFile' AND query_identifier='INSERT_ITEMS_BULK'
);
