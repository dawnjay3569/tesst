# Core libraries
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os
import time
import warnings

# External libraries
from dotenv import load_dotenv
import oracledb
import pandas as pd
from pyqvd import QvdTable
import redis

# Internal libraries
from RPA_MODULES.common_lib.logging_config import get_logger
from RPA_MODULES.common_lib import nod_api  # For API source

#from timeit import dummy_src_name
#from qvd import qvd_reader  # For QVD source

# Suppress the pandas warning on only supporting SQLAlchemy, oracledb will work, and it's faster without SQLAlchemy wrapper
warnings.filterwarnings(
    "ignore",
    category=UserWarning
)

# Load environment variables
load_dotenv()

REDIS_HOST = os.getenv("RPA_REDIS_HOST")
REDIS_PASSWORD = os.getenv("RPA_REDIS_PASSWORD")
REDIS_PORT = int(os.getenv("RPA_REDIS_PORT"))
REDIS_USE_SSL = os.getenv("RPA_REDIS_USE_SSL", "false").lower() == "true"
REDIS_DB = int(os.getenv("RPA_REDIS_DB"))

# Get a logger for this script
logger = get_logger("rpa_data_load.py")

def get_database_connection(source) -> oracledb.Connection:
    try:
        dsn = f"{os.getenv(f'{source}_ORACLE_DB_HOST')}:{os.getenv(f'{source}_ORACLE_DB_PORT')}/{os.getenv(f'{source}_ORACLE_DB_SERVICE_NAME')}"
        return oracledb.connect(
            user=os.getenv(f"{source}_ORACLE_DB_USER"),
            password=os.getenv(f"{source}_ORACLE_DB_PASSWORD"),
            dsn=dsn
        )
    except Exception as e:
        logger.error(f"Failed to connect to {source}: {str(e)}")
        raise
    
def get_redis_connection() -> redis.Redis:
    try:
        connection_params = {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": REDIS_DB,
            "ssl": REDIS_USE_SSL,
            "decode_responses": True
        }

        if REDIS_PASSWORD:
            connection_params["password"] = REDIS_PASSWORD

        return redis.Redis(**connection_params) # Passing all parameters from the dictionary

    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise

def fetch_query_config(query_key) ->  dict[str, int] | None:
    logger.info(f"Fetching query config for: {query_key}")
    conn = get_database_connection("RPA")
    try:
        cursor = conn.cursor()
        query = (
            "SELECT FREQUENCY, SOURCE, QUERY, ACTION, PROC "
            "FROM RPA_INPUTS.GRAND_QUERIES "
            "WHERE filename = UPPER(:rpa)"  # Bind variable for safety
        )
        cursor.execute(query, {"rpa": query_key})
        row = cursor.fetchone()

        if not row:
            logger.error(f"Query {query_key} not found in RPA_INPUTS.GRAND_QUERIES")
            raise ValueError(f"Query '{query_key}' not found in RPA_INPUTS.GRAND_QUERIES")

        # Convert CLOB (row[1]) to string if it’s a LOB object
        query_text = row[2].read() if hasattr(row[2], 'read') else row[2]
        result = {
            "data_flow_key": query_key,
            "frequency": row[0],
            "source": row[1],
            "query": query_text,  # Now a string
            "insert_method": row[3],
            "chunk_size": 10000,  # Hardcoded value
            "proc_flag": row[4]
        }
    except Exception as e:
        logger.error(f"Error fetching query config for {query_key}: {str(e)}")
        raise
    finally:
        conn.close()
    return result

def read_from_source(query_config) -> pd.DataFrame | None:
    query_key = query_config["data_flow_key"]
    source = query_config["source"].upper()
    logger.info(f"Reading from {source} for {query_key}...")

    # Oracle sources
    if source in ["SIEBEL", "VOD", "SMARTS", "NETCOOL", "AMN", "INSIGHTS", "KENAN_CU1", "KENAN_CU2", "KENAN_CU3", "KENAN_CU4", "KENAN_CU5", "XTRAC", "RPA"]:
        conn = get_database_connection(source)
        try:
            if query_config["query"]:
                df = pd.read_sql(query_config["query"], conn)
            else:
                raise ValueError(f"No query provided for {source}")
        finally:
            conn.close()
        return df

    # elif source == "QVD":
    #     return qvd_reader.read(query_config["query"] or query_config["table_name"])

    # Qlik source
    elif source == "QVD":
        qvd_file = query_config["query"] or query_config["table_name"]
        qvd_table = QvdTable.from_qvd(qvd_file)
        return qvd_table.to_pandas()

    elif source == "API":
        if query_config["table_name"] == "NOD_VOICE_MULTISEARCH_API":
            return nod_api.read_multisearch_api()
        elif query_config["table_name"] == "NOD_VOICE_TRANSACTION_DETAILS_API":
            return nod_api.read_transaction_api()
        else:
            raise ValueError(f"Unknown API endpoint: {query_config['table_name']}")

    else:
        raise ValueError(f"Unsupported source: {source}")

def write_to_destination(df, query_config) -> None:
    query_key = query_config["data_flow_key"]
    insert_method = query_config["insert_method"]
    chunk_size = query_config["chunk_size"]
    logger.info(f"Writing {query_key} data to destination...")
    conn = get_database_connection("RPA")
    try:
        cursor = conn.cursor()
        if insert_method == "truncate":
            cursor.execute(f"TRUNCATE TABLE OI_RTQM.{query_key}")

        # Clean DataFrame
        df = df.fillna("").map(str).replace("NaT", "")

        # Prepare column names and placeholders for bulk insert
        columns = ", ".join(df.columns)
        placeholders = ", ".join([f":{i+1}" for i in range(len(df.columns))])
        insert_query = f"INSERT INTO OI_RTQM.{query_key} ({columns}) VALUES ({placeholders})"

        # Convert DataFrame to list of tuples for executemany
        data = [tuple(row) for row in df.itertuples(index=False)]

        # Insert in chunks
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            cursor.executemany(insert_query, chunk)

        conn.commit()
        logger.info(f"Wrote {len(df)} rows to OI_RTQM.{query_key}")
    except Exception as e:
        logger.error(f"Error writing to destination: {str(e)}")
        raise
    finally:
        conn.close()

def set_data_load_running_status_in_redis(query_key: str, is_running: bool, redis_client: redis.Redis = None) -> None:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it

    try:
        key = f"data_load_running:{query_key}"
        #redis_client.set(key, "1" if is_running else "0")  # "1" indicates running
        redis_client.setex(key, 7200, "1" if is_running else "0")
        logger.info(f"Set data flow running flag to {is_running} for {query_key}")
    except Exception as e:
        logger.error(f"Error setting data flow running flag for '{query_key}': {str(e)}")
        raise
    finally:
        if created_client:
            redis_client.close()

def set_load_status_in_redis(dependent_file: str, ttl_seconds: int = 240, redis_client: redis.Redis = None) -> None:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it

    try:
        key = f"rpa_dependent_file_loaded:{dependent_file}"
        if ttl_seconds > 0:
            redis_client.setex(key, ttl_seconds, "1")  # "1" indicates loaded
            logger.info(f"Set data ready status to {ttl_seconds} seconds for {dependent_file}")
        else:
            redis_client.delete(key)
            logger.info(f"Cleared data ready status for {dependent_file}")
    except Exception as e:
        logger.error(f"Error setting data ready status for '{dependent_file}': {str(e)}")
        raise
    finally:
        if created_client:
            redis_client.close()

def delete_load_status_in_redis(dependent_file: str, redis_client: redis.Redis = None) -> None:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it

    try:
        key = f"rpa_dependent_file_loaded:{dependent_file}"
        redis_client.delete(key)
        logger.info(f"Clear data load status flag for: {dependent_file}")
    except Exception as e:
        logger.error(f"Error clearing data load status flag for '{dependent_file}': {str(e)}")
        raise
    finally:
        if created_client:
            redis_client.close()

def check_data_load_running(query_key: str, redis_client: redis.Redis = None) -> bool:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it

    try:
        running_key = f"data_load_running:{query_key}"
        value = redis_client.get(running_key)
        if value is None:
            logger.info(f"No running status found for '{query_key}', assuming data flow is not running.")
            return False
        result = value == "1"  # True if "1", False if "0" or anything else
        logger.info(f"Data load process for '{query_key}' is {'already running' if result else 'currently not running (no interference)'}")
    except Exception as e:
        logger.error(f"Error getting data load running status for '{query_key}': {str(e)}")
        if created_client:
            redis_client.close()
        raise

    if created_client:
        redis_client.close()
    return result

def check_data_loaded(query_key: str, redis_client: redis.Redis = None) -> bool:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True
    try:
        loaded_key = f"rpa_dependent_file_loaded:{query_key}"
        value = redis_client.get(loaded_key)
        if value is None:
            logger.info(f"No data load status flag found in Redis for '{query_key}', assuming data is not loaded.")
            return False
        result = value == "1"
        ttl = redis_client.ttl(loaded_key)
        logger.info(f"Data for '{query_key}' is {'already loaded' if result else 'not loaded'}, TTL: {ttl} seconds")
    except Exception as e:
        logger.error(f"Error checking data loaded status for '{query_key}': {str(e)}")
        if created_client:
            redis_client.close()
        raise
    
    if created_client:
        redis_client.close()    
    return result

def execute_data_flow(query_key, force_reload: bool = False):
    logger.info(f"Executing data flow for '{query_key}'")

    start_time = datetime.now()
    redis_client = get_redis_connection()

    # query_config = {}  # Initialize safely before try

    try:
        # Check if data load is already running
        if check_data_load_running(query_key, redis_client):
            logger.info(f"Exiting data load process to avoid duplicate execution for {query_key}")
            return "running"

        # Check if already loaded
        if not force_reload and check_data_loaded(query_key, redis_client):
            logger.info(f"Data for {query_key} is already loaded.")
            return "loaded"

        # Delete load status in Redis
        delete_load_status_in_redis(query_key, redis_client)
        
        # Set running status in Redis
        set_data_load_running_status_in_redis(query_key, True, redis_client)


        logger.info(f"Starting data load process for {query_key}")
        # Fetch query configuration
        query_config = fetch_query_config(query_key)

        # Read data
        stage_start = datetime.now()
        data_df = read_from_source(query_config)
        logger.info(f"Data read for {query_key} took {(datetime.now() - stage_start).total_seconds()} seconds")

        # If data is not empty, proceed to write
        if not data_df.empty:
            # Log rows count
            logger.info(f"Table: OI_RTQM.{query_key}, Rows Affected: {len(data_df)}, Operation: Initial Query Load")
            stage_start = datetime.now()
            write_to_destination(data_df, query_config)
            logger.info(f"Data write for {query_key} took {(datetime.now() - stage_start).total_seconds()} seconds")
        else:
            logger.info(f"Data read for {query_key} is empty, skipping write.")
            
        # Optional: Call stored procedure if specified
        if query_config["proc_flag"] == "proc":
            stage_start = datetime.now()
            conn = get_database_connection("RPA")
            try:
                logger.info(f"Calling stored procedure for {query_key}")
                cursor = conn.cursor()
                
                # Enable DBMS_OUTPUT
                cursor.callproc("dbms_output.enable")
                out_lines = cursor.arrayvar(oracledb.STRING, 100)  # Buffer for up to 100 lines
                num_lines = cursor.var(oracledb.NUMBER)  # Variable for number of lines retrieved
                num_lines.setvalue(0, 100) # Set the number of lines to fetch
                lines = [] # List to store output lines

                # Call the stored procedure
                cursor.callproc(f"OI_RTQM_L1.{query_key}_proc")
                
                # Fetch output from DBMS_OUTPUT
                while True:
                    # Call the procedure to get lines
                    cursor.callproc("dbms_output.get_lines", [out_lines, num_lines])
                    
                    # Get the number of lines retrieved
                    num_lines_value = int(num_lines.getvalue())
                    if num_lines_value == 0:
                        break  # No more lines to fetch

                    # Append the retrieved lines to the result
                    fetched_lines = out_lines.getvalue()[:num_lines_value]
                    lines.extend(fetched_lines)

                # Log or process the dbms output (optional, exists only in some procedures)
                for line in lines:
                    if isinstance(line, str) and line.startswith('MODIFICATION:'):
                        parts = line[len('MODIFICATION:'):].split('|')
                        if len(parts) == 3:
                            logger.info(f"Table: {parts[0]}, Rows Affected: {parts[1]}, Operation: {parts[2]}")
                    elif isinstance(line, str):
                        logger.info(f"DBMS_OUTPUT: {line}")
                conn.commit()
            finally:
                conn.close()
            logger.info(f"Running OI_RTQM_L1.{query_key}_PROC stored procedure took {(datetime.now() - stage_start).total_seconds()} seconds")


        # Set load status flag inRedis
        stage_start = datetime.now()
        set_load_status_in_redis(query_key, query_config["frequency"] * 60, redis_client)

        # Log success
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Data load for {query_key} took {duration} seconds")
        
        # If data is empty, return "empty" if not returning "loaded"
        if data_df.empty:
            logger.warning(f"Data load for {query_key} is empty. Marking as loaded.")
            return "empty"
        else:
            logger.info(f"Data load for {query_key} is loaded.")
            return "loaded"

    except Exception as e:
        end_time = datetime.now()
        logger.error(f"Error in {query_key}: {str(e)}")
        logger.error(f"Data load for {query_key} took {end_time - start_time} seconds, before error")
        # Set load status in Redis to failed
        set_load_status_in_redis(query_key, 0, redis_client)
        return "failed"
    
    finally:
        # Set running status in Redis
        try:
            set_data_load_running_status_in_redis(query_key, False, redis_client)
        except Exception as e:
            logger.error(f"Error clearing running status for '{query_key}': {str(e)}")    
            
def run_data_loads(query_keys: list[str], force_reload: bool = False) -> None:
    redis_client = get_redis_connection()
    max_attempts = 3
    timeout_seconds = 300  # 5 minutes per task
    attempts = {key: 0 for key in query_keys}
    try:
        while True:
            pending_keys = set(k for k, v in attempts.items() if v < max_attempts)
            if not pending_keys:
                logger.error("All data loads exceeded max attempts - aborting.")
                break
            with ThreadPoolExecutor(max_workers=len(pending_keys) or 1) as executor:
                futures = {executor.submit(execute_data_flow, key, force_reload): key for key in pending_keys}
                logger.info(f"Tasks submitted: {len(futures)}")
                for future in as_completed(futures):
                    query_key = futures[future]
                    logger.info(f"Waiting for data load completion for {query_key}")
                    try:
                        status = future.result(timeout=timeout_seconds)
                        if status == "running":
                            while check_data_load_running(query_key, redis_client):
                                time.sleep(5)
                            logger.info(f"{query_key} completed externally.")
                        elif status in ["loaded", "empty"]:
                            logger.info(f"{query_key} returned status: {status}")
                            pending_keys.discard(query_key)
                        elif status == "failed":
                            logger.error(f"{query_key} failed - will retry.")
                            attempts[query_key] += 1
                        else:
                            logger.info(f"{query_key} completed with status: {status}")
                            pending_keys.discard(query_key)
                    except TimeoutError:
                        logger.error(f"{query_key} exceeded {timeout_seconds}s - marking as failed.")
                        attempts[query_key] += 1

            still_pending = []
            for query_key in query_keys:
                # loaded_key = f"rpa_dependent_file_loaded:{query_key}"
                # if redis_client.get(loaded_key) != "1":
                if not check_data_loaded(query_key, redis_client):
                    if attempts[query_key] < max_attempts:
                        logger.info(f"{query_key} not loaded - attempt {attempts[query_key] + 1}/{max_attempts}")
                        still_pending.append(query_key)
                    else:
                        logger.error(f"{query_key} not loaded after {max_attempts} attempts.")
                else:
                    logger.info(f"{query_key} confirmed loaded.")
            if not still_pending:
                break
            pending_keys = set(still_pending)
            logger.info(f"Retrying {len(pending_keys)} pending keys: {pending_keys}")
    finally:
        redis_client.close()

def parse_dbms_output(lines):
    output_data = []
    for line in lines:
        if line and line.startswith('MODIFICATION:'):
            parts = line[len('MODIFICATION:'):].split('|')
            if len(parts) == 3:
                # Unescape delimiters (if using escape_delimiter in procedure)
                table_name = parts[0].replace('||', '|')
                try:
                    rows_affected = int(parts[1])
                except ValueError:
                    logger.error(f"Invalid rows_affected in line: {line}")
                    continue
                operation_type = parts[2].replace('||', '|')
                output_data.append({
                    "table_name": table_name,
                    "rows_affected": rows_affected,
                    "operation_type": operation_type
                })
                logger.info(f"Parsed output: Table: {table_name}, Rows Affected: {rows_affected}, Operation: {operation_type}")
            else:
                logger.error(f"Invalid format in line: {line}")
        elif line:
            logger.info(f"DBMS_OUTPUT: {line}")  # Log other output lines
    return output_data