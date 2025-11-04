# Core libraries
import os

# External libraries
import oracledb
import pandas as pd
from dotenv import load_dotenv

# Internal libraries
from RPA_MODULES.common_lib.logging_config import get_logger

load_dotenv()

# Prefer standard DB_* vars (see db.py), with fallback to legacy RPA_ORACLE_* names
DB_HOST = os.getenv("DB_HOST") or os.getenv("RPA_ORACLE_DB_HOST")
DB_PORT_STR = os.getenv("DB_PORT") or os.getenv("RPA_ORACLE_DB_PORT")
DB_SERVICE_NAME = os.getenv("DB_SERVICE") or os.getenv("RPA_ORACLE_DB_SERVICE_NAME")
DB_USERNAME = os.getenv("DB_USER") or os.getenv("RPA_ORACLE_DB_USER")
DB_PASSWORD = os.getenv("DB_PASS") or os.getenv("RPA_ORACLE_DB_PASSWORD")

try:
    DB_PORT = int(DB_PORT_STR) if DB_PORT_STR else 1521
except Exception:
    DB_PORT = 1521

# Get a logger for this script
logger = get_logger("oracle_oi_rtqm.py")

def update_sql_oi_rtqm(sql, data=None):
    dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE_NAME)
    connection = oracledb.connect(user=DB_USERNAME, password=DB_PASSWORD, dsn=dsn)
    cursor = connection.cursor()
    try:
        if data is not None:
            df = cursor.executemany(sql, data)
        elif sql.upper().startswith(('TRUNCATE', 'MERGE', 'INSERT', 'UPDATE')):
            df = cursor.execute(sql)
        elif sql.upper().startswith(('EXEC', 'BEGIN')):
            sql = 'BEGIN ' + sql.split(" ")[1] + '; END;'
            df = cursor.execute(sql)
        else:
            df = pd.read_sql(sql, con=connection)
        return df
    except Exception as err:
        #logger.error(f"Error executing SQL: {err}")
        logger.error(f"Error executing SQL: {err} | Row: {data[0] if data and isinstance(data, list) else data}")
        return err
    finally:
        connection.commit()
        cursor.close()
        connection.close()