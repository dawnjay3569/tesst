# Core libraries
from datetime import datetime
from enum import Enum
import os
from typing import Callable, Optional

# External libraries
from dotenv import load_dotenv
import oracledb
import pandas as pd
import redis

# Internal libraries
from RPA_MODULES.common_lib.rpa_data_load import run_data_loads
from RPA_MODULES.common_lib.logging_config import get_logger, set_rpa_module_name, set_rpa_workflow_name, set_rpa_argo_workflow_name, set_rpa_workflow_run_guid

# Load the environment variables
load_dotenv()

# Get a logger for this script
logger = get_logger("rpa_runner.py")
set_rpa_workflow_name(os.getenv("RPA_NAME")) # This should be set from the argo workflow with environment variable
set_rpa_argo_workflow_name(os.getenv("ARGO_WORKFLOW_NAME")) # This should be set from the argo workflow with environment variable
set_rpa_workflow_run_guid(os.getenv("RPA_RUN_GUID")) # This should be set from the argo workflow with environment variable

DB_HOST = os.getenv("INSIGHTS_ORACLE_DB_HOST")
DB_PORT = os.getenv("INSIGHTS_ORACLE_DB_PORT")
DB_SERVICE_NAME = os.getenv("INSIGHTS_ORACLE_DB_SERVICE_NAME")
DB_USERNAME = os.getenv("INSIGHTS_ORACLE_DB_USER")
DB_PASSWORD = os.getenv("INSIGHTS_ORACLE_DB_PASSWORD")

REDIS_HOST = os.getenv("RPA_REDIS_HOST")
REDIS_PORT = int(os.getenv("RPA_REDIS_PORT"))
REDIS_DB = int(os.getenv("RPA_REDIS_DB"))

OLD_RPA_MODULE_SCHEMA = "OI_RTQM_L1"
NEW_RPA_MODULE_SCHEMA = os.getenv("INSIGHTS_ORACLE_DB_USER") # This should be the schema where the new RPA module procedures are stored

# NEW_RPA_MODULE_SCHEMA = "OI_RTQM_L1"#os.getenv("INSIGHTS_ORACLE_DB_USER") # This should be the schema where the new RPA module procedures are stored

class DataLoadMode(Enum):
    NO_LOAD = 0 # Grand queries are not run, only the stored procedure is executed
    LOAD = 1 # Grand queries are run, data is loaded from the database
    FORCE_RELOAD = 2 # Grand queries are run, data is loaded from the database, and the data is reloaded even if it is already loaded in Redis

class RpaModuleProcedureType(Enum):
    OLD = 1 # Old way, runs with grand queries that are looked up in the database
    NEW = 2 # New way, runs with stored procedures that gets data directly from the database
    
def get_oracle_connection() -> oracledb.Connection:
    try:
        dsn = f"{DB_HOST}:{DB_PORT}/{DB_SERVICE_NAME}"
        return oracledb.connect(
            user=DB_USERNAME,
            password=DB_PASSWORD,
            dsn=dsn
        )
    except Exception as e:
        logger.error(f"Error connecting to Oracle: {e}")
        raise

def get_redis_connection() -> redis.Redis:
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
    except Exception as e:
        logger.error(f"Error connecting to Redis: {e}")
        raise

# This method is used here only for testing purposes, as this will be run by the data loading script
def set_load_status_in_redis(dependent_file: str, ttl_seconds: int = 240, redis_client: redis.Redis = None) -> None:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it

    try:
        key = f"rpa_dependent_file_loaded:{dependent_file}"
        redis_client.setex(key, ttl_seconds, "1")  # "1" indicates loaded
        logger.info(f"Set {key} as loaded with TTL {ttl_seconds} seconds")
    except Exception as e:
        logger.error(f"Error setting load status for '{dependent_file}': {e}")
        raise
    finally:
        if created_client:
            redis_client.close()

# This works on the rpa module procedure name, as it needs to be compatible with the 1.0 system, and this is differentiator for the RPA module name
def set_rpa_running_status_in_redis(rpa_name: str, is_running: bool, redis_client: redis.Redis = None) -> None:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it
        
    try:
        key = f"rpa_running:{rpa_name}"
        #redis_client.set(key, "1" if is_running else "0")  # "1" indicates running
        redis_client.setex(key, 86400, "1" if is_running else "0") 
        logger.info(f"Set {key} flag in Redis: {is_running}")
    except Exception as e:
        logger.error(f"Error setting running flag in Redis for '{rpa_name}': {e}")
        raise
    finally:
        if created_client:
            redis_client.close()

def check_dependent_files_in_redis(dependent_files, redis_client: redis.Redis = None) -> bool:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it
    
    result = True  # Default to True if no files or all are loaded
    try:
        if dependent_files:  # Only check if there are files
            files = dependent_files.split(" ") if isinstance(dependent_files, str) else dependent_files # In db, files are stored as a string separated by space
            for file in files:
                file_key = f"rpa_dependent_file_loaded:{file.strip()}"
                if not redis_client.get(file_key):
                    logger.info(f"Dependent file '{file}' not loaded in Redis.")
                    result = False
                    break
    except Exception as e:
        logger.error(f"Error checking dependent files in Redis: {e}")
        if created_client:
            redis_client.close()
        raise
    if created_client:
        redis_client.close()
    return result

def check_rpa_running_in_redis(rpa_name: str, redis_client: redis.Redis = None) -> bool:
    # Use provided redis_client or create a new one
    created_client = False
    if redis_client is None:
        redis_client = get_redis_connection()
        created_client = True  # Track if we created it so we can close it

    try:
        key = f"rpa_running:{rpa_name}"
        value = redis_client.get(key)
        if value is None:
            logger.info(f"No running status found for '{rpa_name}', assuming not running.")
            return False
        result = value == "1"  # True if "1", False if "0" or anything else
        logger.info(f"RPA '{rpa_name}' is {'running' if result else 'not running'}")
    except Exception as e:
        logger.error(f"Error checking RPA running status for '{rpa_name}': {e}")
        redis_client.close()
        raise
    if created_client:
        redis_client.close()
    return result    

def fetch_stored_procedure_dependant_files(stored_procedure_name) -> dict:
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        query = (
            "SELECT DEPENDENT_FILES "
            f"FROM {NEW_RPA_MODULE_SCHEMA}.RPA_MODULE_PROCEDURE_CONFING "
            "WHERE PROCEDURE_NAME = UPPER(:rpa)"  # Bind variable for safety
        )
        cursor.execute(query, rpa=stored_procedure_name)
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"No RPA found with name '{stored_procedure_name}'")
            
        result = {
            "dependent_files": row[0]
        }

    except Exception as e:
        logger.error(f"Error fetching RPA config for '{stored_procedure_name}': {e}")
        conn.close()
        raise
    
    conn.close()
    return result

# Method to check if the stored procedure has any parameters
def get_procedure_arg_count(cursor, proc_owner, proc_name) -> int:
    query = """
            SELECT COUNT(*)
            FROM ALL_ARGUMENTS
            WHERE OWNER = :owner
              AND OBJECT_NAME = :proc_name
              AND PACKAGE_NAME IS NULL
            """
    cursor.execute(query, owner=proc_owner.upper(), proc_name=proc_name.upper())
    return cursor.fetchone()[0]

# Method to process LOB data types (CLOB/BLOB) to ensure they are readable after fetching from the database
def process_returned_data(value):
    # Handles both CLOB and BLOB by checking for .read()
    if hasattr(value, "read") and callable(value.read):
        return value.read()
    return value

def execute_stored_procedure(owner: str, procedure_name: str, param: str = None) -> pd.DataFrame | None:
    logger.info(f"Started execute_stored_procedure function owner {owner}  and proc {procedure_name}")
    conn = get_oracle_connection()
    logger.info(f"connection established {conn.username}")
    try:
        cursor = conn.cursor()
        
        # Check if the procedure has parameters
        arg_count = get_procedure_arg_count(cursor, owner, procedure_name)

        # Enable DBMS_OUTPUT
        cursor.callproc("dbms_output.enable")
        out_lines = cursor.arrayvar(oracledb.STRING, 100)  # Buffer for up to 100 lines
        num_lines = cursor.var(oracledb.NUMBER)  # Variable for number of lines retrieved
        num_lines.setvalue(0, 100) # Set the number of lines to fetch
        lines = [] # List to store output lines
        
        # Call the stored procedure
        if arg_count == 0:
            # No parameters, call the procedure directly
            cursor.callproc(f"{owner}.{procedure_name}")
            df = None  # No DataFrame to return since no parameters or output
        else:
            # Parameters are not provided, so we run the procedure with null parameters
            if param is None:
                # Call the procedure with NULL input, ignore the output (the old way)
                out_param = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc(f"{owner}.{procedure_name}", (None, out_param))
                df = None
            else:
                # Call with input, expect output, return DataFrame
                out_param = cursor.var(oracledb.DB_TYPE_CURSOR)
                logger.info(f"Executing stored procedure '{procedure_name}' with owner : {owner}")
                cursor.callproc(f"{owner}.{procedure_name}", (param, out_param))
                # Get the result cursor from the output variable
                result_cursor = out_param.getvalue()
                # Fetch data
                data = [
                    tuple(process_returned_data(cell) for cell in row) # Process each cell in the row to handle various data types (e.g., CLOB, BLOB)
                    for row in result_cursor.fetchall() # Iterate over the rows in the result cursor
                ]
                # Get the column names from the result cursor
                columns = [col[0] for col in result_cursor.description]
                # Create a DataFrame from the fetched data
                df = pd.DataFrame(data, columns=columns)

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
            
        for line in lines:
            if isinstance(line, str) and line.startswith('MODIFICATION:'):
                parts = line[len('MODIFICATION:'):].split('|')
                if len(parts) == 3:
                    logger.info(f"Table: {parts[0]}, Rows Affected: {parts[1]}, Operation: {parts[2]}")
            elif isinstance(line, str):
                logger.info(f"DBMS_OUTPUT: {line}")
                
        conn.commit()
        return df
    except Exception as e:
        logger.error(f"Error executing stored procedure {procedure_name}: {e}")
        raise
    finally:
        conn.close()

def run_sql_query(sql_script) -> pd.DataFrame | None:
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_script)
        # Fetch column names
        columns = [desc[0] for desc in cursor.description]
        # Fetch all rows
        rows = cursor.fetchall()
        # Return as DataFrame
        result = pd.DataFrame(rows, columns=columns)
    except Exception as e:
        logger.error(f"Error running SQL query: {e}")
        raise
    finally:
        conn.close()
    return result
    
def run_rpa(rpa_module_name: str, main_func: Callable[[pd.DataFrame | None], None], rpa_module_procedure_name: str, procedure_type: RpaModuleProcedureType = RpaModuleProcedureType.OLD, procedure_parameter: str = None, data_load_mode: DataLoadMode = DataLoadMode.LOAD, input_df: pd.DataFrame = None) -> None:
    set_rpa_module_name(rpa_module_name)

    if input_df is not None:
        logger.info(f"Starting RPA module: {rpa_module_name} with provided DataFrame.")
        main_func(input_df)
        logger.info(f"Finished executing main method for RPA module '{rpa_module_name}' with provided DataFrame.")
        return
    
    # If no RPA name is provided, raise an error and log
    if not rpa_module_procedure_name:
        logger.error("RPA module procedure name is not provided. Exiting.")
        raise ValueError("RPA module procedure name must be provided.")
    
    logger.info(f"Starting RPA module: {rpa_module_name} with procedure: {rpa_module_procedure_name} and type: {procedure_type.name}")
    
    if procedure_parameter:
        logger.info(f"Procedure parameter provided: {procedure_parameter}")
    else:
        logger.info("No procedure parameter provided, running without parameters.")
        
    redis_client = get_redis_connection()
    
    # Check if the data load mode is not the default
    if data_load_mode != DataLoadMode.LOAD:
        logger.info(f"Data load mode changed to: {data_load_mode.name}")

    try:
        # Check if RPA module with using selected procedure is already running
        logger.info(f"Checking in Redis if RPA module using procedure '{rpa_module_procedure_name}' is already running")
        if check_rpa_running_in_redis(rpa_module_procedure_name, redis_client):
            logger.warning(f"Exiting to prevent RPA module using '{rpa_module_procedure_name}' from running at the same time.")
            return
        
        # Set RPA module running status to True (this uses procedure name as the flag in Redis, so it is compatible with the 1.0 system)
        # Keep in mind this would not let the same procedure with different parameters run at the same time
        set_rpa_running_status_in_redis(rpa_module_procedure_name, True, redis_client)
        
        # Get RPA config data from the database only for OLD procedure type
        dependent_files = None
        if procedure_type != RpaModuleProcedureType.NEW:
            logger.info(f"Fetching dependent files (grand queries) for stored procedure: {rpa_module_procedure_name}")
            dependent_files = fetch_stored_procedure_dependant_files(rpa_module_procedure_name)["dependent_files"] # Tables that need to be loaded before running the RPA
        
        # Load RPA module procedure dependencies from (grand queries)
        if data_load_mode != DataLoadMode.NO_LOAD and dependent_files and (procedure_type.value != RpaModuleProcedureType.NEW):
            logger.info(f"Loading dependent files for RPA module stored procedure '{rpa_module_procedure_name}'")
            files = dependent_files.split(" ") if isinstance(dependent_files, str) else dependent_files # In db, files are stored as a string separated by space
            run_data_loads(files, force_reload=(data_load_mode == DataLoadMode.FORCE_RELOAD))
        
        # Execute the stored procedure based on the procedure type
        if procedure_parameter is None:
            logger.info(f"Executing stored procedure '{rpa_module_procedure_name}' without parameters")
        else:
            logger.info(f"Executing stored procedure '{rpa_module_procedure_name}' with parameter: {procedure_parameter}")

        stage_start = datetime.now()
        # Depending on the procedure type, select the appropriate schema for the stored procedure (OLD or NEW)
        proc_schema = NEW_RPA_MODULE_SCHEMA if procedure_type == RpaModuleProcedureType.NEW else OLD_RPA_MODULE_SCHEMA
        df = execute_stored_procedure(proc_schema, rpa_module_procedure_name.upper(), procedure_parameter)
        logger.info(f"Stored procedure '{rpa_module_procedure_name}' execution took {(datetime.now() - stage_start).total_seconds()} seconds")
        
        # Log the DataFrame rows count
        if df is not None:
            logger.info(f"Stored procedure {rpa_module_procedure_name} returned {len(df)} rows.")
        else:
            logger.info("Stored procedure returned no rows.")
        
        logger.info(f"Executing main method for RPA module '{rpa_module_procedure_name}'")
        main_func(df)  # Execute the RPA logic
        
        logger.info(f"Finished executing main method for RPA module '{rpa_module_procedure_name}'")
        
    except Exception as e:
        logger.error(f"RPA module '{rpa_module_name}' with procedure '{rpa_module_procedure_name}' failed: {e}")
        raise
    finally:
        try:
            set_rpa_running_status_in_redis(rpa_module_procedure_name, False, redis_client)
        except Exception as e:
            logger.error(f"Error setting module procedure: '{rpa_module_procedure_name}' as not running: {e}")
        redis_client.close()


# if __name__ == "__main__":
#     # test the RPA runner with a dummy main function
#     def dummy_main(df: pd.DataFrame | None):
#         if df is not None:
#             print(f"Dummy main function received DataFrame with {len(df)} rows.")
#         else:
#             print("Dummy main function received no DataFrame.")
# 
#     try:
#         run_rpa(
#             rpa_module_name="siebel_ticket_creator",
#             main_func=dummy_main,
#             rpa_module_procedure_name="UT_KE_SOLN_PROC",
#             procedure_type=RpaModuleProcedureType.NEW,
#             data_load_mode=DataLoadMode.LOAD
#         )
#     except Exception as e:
#         print(f"Error running RPA: {e}")
