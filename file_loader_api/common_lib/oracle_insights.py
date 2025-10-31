# Core libraries
import os
#import warnings

# External libraries
#import cx_Oracle
from dotenv import load_dotenv
import oracledb
import pandas as pd
from sqlalchemy import create_engine, text

load_dotenv()

DB_HOST = os.getenv("RPA_ORACLE_DB_HOST")
DB_PORT = int(os.getenv("RPA_ORACLE_DB_PORT"))
DB_SERVICE_NAME = os.getenv("RPA_ORACLE_DB_SERVICE_NAME")
DB_USERNAME = os.getenv("RPA_ORACLE_DB_USER")
DB_PASSWORD = os.getenv("RPA_ORACLE_DB_PASSWORD")

#warnings.filterwarnings("ignore")

# def update_sql_old(sql, data=None):
#     conn = cx_Oracle.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE_NAME)
#     connection = cx_Oracle.connect(user=DB_USERNAME, password=DB_PASSWORD, dsn=conn, encoding='UTF-8', nencoding='UTF-8')
# 
#     cursor = cx_Oracle.Cursor(connection)
#     try:
#         if data is not None:
#             df = cursor.executemany(sql, data)
#         elif sql.upper().startswith('TRUNCATE') or sql.upper().startswith('MERGE') or sql.upper().startswith(
#                 'INSERT') or sql.upper().startswith('UPDATE'):
#             df = cursor.execute(sql)
#         elif sql.upper().startswith('EXEC') or sql.upper().startswith('BEGIN'):
#             sql = 'BEGIN ' + sql.split(" ")[1] + '; END;'
#             df = cursor.execute(sql)
#         else:
#             df = pd.read_sql(sql, con=connection)
#         return df
#     except Exception as err:
#         return err
#     finally:
#         connection.commit()
#         cursor.close()
#         connection.close()
        
# Below is the original method equivalent with the oracledb library
# def update_sql(sql, data=None):
#     connection = None
#     cursor = None
#     try:
#         # Create DSN (Data Source Name)
#         dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE_NAME)
# 
#         # Establish connection
#         connection = oracledb.connect(user=DB_USERNAME, password=DB_PASSWORD, dsn=dsn)
# 
#         # Create cursor
#         cursor = connection.cursor()
# 
#         # Execute SQL based on type
#         if data is not None:
#             # Handle executemany for batch operations
#             cursor.executemany(sql, data)
#             df = None  # No DataFrame returned for executemany
#         elif sql.upper().startswith('TRUNCATE') or sql.upper().startswith('MERGE') or \
#                 sql.upper().startswith('INSERT') or sql.upper().startswith('UPDATE'):
#             # Handle DML operations (INSERT, UPDATE, MERGE, TRUNCATE)
#             cursor.execute(sql)
#             df = None  # No DataFrame returned for DML
#         elif sql.upper().startswith('EXEC') or sql.upper().startswith('BEGIN'):
#             # Handle PL/SQL blocks
#             sql = 'BEGIN ' + sql.split(" ")[1] + '; END;'
#             cursor.execute(sql)
#             df = None  # No DataFrame returned for PL/SQL
#         else:
#             # Handle SELECT queries and return DataFrame
#             df = pd.read_sql_query(sql, con=connection)
# 
#         return df
#     except oracledb.Error as err:
#         # Handle Oracle database errors
#         print(f"Oracle Error: {err}")
#         return err
#     except Exception as err:
#         # Handle other exceptions
#         print(f"Error: {err}")
#         return err
#     finally:
#         # Commit changes and close resources
#         if 'connection' in locals():
#             if cursor is not None:
#                 cursor.close()
#             if connection is not None:
#                 connection.commit()
#                 connection.close()


# Best variant of the original method, with new library, correctly handling LOB columns, and using SQL alchemy for full pandas compatibility
def update_sql(sql, data=None):
    connection = None
    cursor = None
    engine = None
    try:
        # Create DSN for oracledb
        dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE_NAME)
        connection_string = f"oracle+oracledb://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/?service_name={DB_SERVICE_NAME}"
        engine = create_engine(connection_string, echo=False)
        connection = oracledb.connect(user=DB_USERNAME, password=DB_PASSWORD, dsn=dsn)
        cursor = connection.cursor()

        if data is not None:
            cursor.executemany(sql, data)
            df = None
        elif sql.strip().upper().startswith(('TRUNCATE', 'MERGE', 'INSERT', 'UPDATE')):
            cursor.execute(sql)
            df = None
        elif sql.strip().upper().startswith(('EXEC', 'BEGIN')):
            sql = f'BEGIN {sql.split(" ")[1]}; END;'
            cursor.execute(sql)
            df = None
        else:
            # Use oracledb cursor to inspect column types for LOB detection
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            column_types = [desc[1] for desc in cursor.description]

            # Check if any column is a LOB type (CLOB, BLOB, NCLOB)
            has_lob = any(typ in (oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_BLOB, oracledb.DB_TYPE_NCLOB) for typ in column_types)

            if has_lob:
                # Fetch all rows and fully read LOB data into memory
                rows = []
                for row in cursor:
                    # Read LOB data for each cell in the row
                    row_data = []
                    for cell, typ in zip(row, column_types):
                        if typ in (oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_BLOB, oracledb.DB_TYPE_NCLOB):
                            # Read LOB data into memory
                            row_data.append(cell.read() if cell else None)
                        else:
                            row_data.append(cell)
                    rows.append(row_data)
                df = pd.DataFrame(rows, columns=columns)
            else:
                # Use SQLAlchemy for lazy loading (non-LOB columns)
                with engine.connect() as conn:
                    df = pd.read_sql_query(text(sql), con=conn)

        return df
    except oracledb.Error as err:
        print(f"Oracle Error: {err}")
        return err
    except Exception as err:
        print(f"Error: {err}")
        return err
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.commit()
            connection.close()
        if engine is not None:
            engine.dispose()