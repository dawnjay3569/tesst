CREATE TABLE items (
  id NUMBER  PRIMARY KEY,
  name VARCHAR2(4000),
  description VARCHAR2(4000),
  price NUMBER
);

-- Users table for authentication
CREATE TABLE users (
  id NUMBER PRIMARY KEY,
  username VARCHAR2(255) UNIQUE NOT NULL,
  password VARCHAR2(2000) NOT NULL, -- store hashed password
  email VARCHAR2(500),
  phone VARCHAR2(50),
  roles VARCHAR2(1000)
);

-- Token blacklist (revoked tokens) to support logout


CREATE TABLE config_table (
  id NUMBER  PRIMARY KEY,
  filename VARCHAR2(4000) NOT NULL,
  query_identifier VARCHAR2(4000) NOT NULL,
  query_text CLOB NOT NULL,
  bind_keys VARCHAR2(4000),
  table_name VARCHAR2(4000),
  proc VARCHAR2(4000),
  load_action VARCHAR2(50),
  email VARCHAR2(500),
  owner VARCHAR2(255),
  comments VARCHAR2(4000)
);
