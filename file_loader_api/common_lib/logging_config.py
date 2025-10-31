# Core libraries
import atexit
from datetime import datetime, timezone
import logging
import logging.handlers
import os
from queue import Queue
from threading import Thread
from typing import Optional
import uuid
import warnings

# External libraries
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ElasticsearchWarning


# Suppress Elasticsearch warnings (we are getting information on the missing configuration)
warnings.filterwarnings("ignore", category=ElasticsearchWarning)

# Load the environment variables
load_dotenv()

# Elasticsearch config
DEFAULT_BACKEND = "elasticsearch"
DEFAULT_CONFIG = {"url": os.getenv("ELASTIC_LOGGING_CONFIG_CONNECTION_STRING"), "index_name": os.getenv("ELASTIC_LOGGING_CONFIG_INDEX_NAME")}

# Global queue and worker thread
log_queue = Queue()
worker_thread: Optional[Thread] = None # Instead of simple worker_thread = None, we use type hint to indicate that worker_thread can be None or a Thread object to avoid IDE warnings

# Global context for RPA name and run GUID
global_context: dict[str, Optional[str]] = {"rpa_workflow_name": None, "rpa_argo_workflow_name": None,"rpa_module_name": None, "rpa_module_run_guid": None, "rpa_workflow_run_guid": None}


# Custom filter to inject RPA name (Python’s logging module expects filters to be instances of a class that inherits from logging.Filter.)
# logging.Filter syntax mean in Python: A filter is a class that inherits from logging.Filter and implements a filter method. The filter method is called for each log record, and it can modify the record or decide whether to log it.
# Custom filter to inject RPA workflow name
class RpaWorkflowNameFilter(logging.Filter):
    def filter(self, record):
        record.rpa_workflow_name = global_context.get("rpa_workflow_name", "N/A")
        return True

# Custom filter to inject RPA workflow name for Argo Workflows (this is used to identify the workflow in Argo UI)
class RpaArgoWorkflowNameFilter(logging.Filter):
    def filter(self, record):
        record.rpa_argo_workflow_name = global_context.get("rpa_argo_workflow_name", "N/A")
        return True    

# Custom filter to inject RPA name
class RpaModuleNameFilter(logging.Filter):
    def filter(self, record):
        record.rpa_module_name = global_context.get("rpa_module_name", "N/A")
        return True

# Custom filter to inject RPA workflow run GUID (this would be established externally by argo workflow and is used to identify the whole flow)
class RpaWorkflowRunGuidFilter(logging.Filter):
    def filter(self, record):
        record.rpa_workflow_run_guid = global_context.get("rpa_workflow_run_guid", "N/A") #["rpa_module_run_guid"]
        return True

# Custom filter for run GUID
class RpaModuleRunGuidFilter(logging.Filter):
    def filter(self, record):
        if global_context["rpa_module_run_guid"] is None:
            # Generate a new GUID if not already set
            global_context["rpa_module_run_guid"] = str(uuid.uuid4())
        record.rpa_module_run_guid = global_context["rpa_module_run_guid"]
        return True

# Function to set the RPA workflow name
def set_rpa_workflow_name(rpa_workflow_name):
    global_context["rpa_workflow_name"] = rpa_workflow_name
    
# Function to set the RPA argo workflow  name  
def set_rpa_argo_workflow_name(rpa_argo_workflow_name):
    global_context["rpa_argo_workflow_name"] = rpa_argo_workflow_name

# Function to set the RPA name
def set_rpa_module_name(rpa_module_name):
    global_context["rpa_module_name"] = rpa_module_name

# Function to set the RPA runGUID
def set_rpa_workflow_run_guid(rpa_workflow_run_guid):
    global_context["rpa_workflow_run_guid"] = rpa_workflow_run_guid

# Function to set or reset run GUID
def set_rpa_module_run_guid(guid=None):
    global_context["rpa_module_run_guid"] = guid if guid else str(uuid.uuid4())
    return global_context["rpa_module_run_guid"]

# Elasticsearch worker thread
def es_worker(queue, es_client, index_name):
    while True:
        record = queue.get()
        if record is None:
            break
        log_entry = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.msg,
            "logger": record.name,
            "pathname": record.pathname,
            "lineno": record.lineno,
        }
        # Add custom tags if present
        if hasattr(record, "rpa_workflow_name"):
            log_entry["rpa_workflow_name"] = record.rpa_workflow_name
        if hasattr(record, "rpa_argo_workflow_name"):
            log_entry["rpa_argo_workflow_name"] = record.rpa_argo_workflow_name
        if hasattr(record, "rpa_module_name"):
            log_entry["rpa_module_name"] = record.rpa_module_name
        if hasattr(record, "rpa_workflow_run_guid"):
            log_entry["rpa_workflow_run_guid"] = record.rpa_workflow_run_guid
        if hasattr(record, "rpa_module_run_guid"):
            log_entry["rpa_module_run_guid"] = record.rpa_module_run_guid
        try:
            es_client.index(index=index_name, body=log_entry)
        except Exception as e:
            print(f"Failed to send log to Elasticsearch: {e}")
        queue.task_done()

# Function to set up logging
def setup_logging(backend=DEFAULT_BACKEND, config=None):
    if config is None:
        config = DEFAULT_CONFIG
    global worker_thread
    if worker_thread is not None:
        return None # Already configured

    # Configure the queue handler
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.addFilter(RpaWorkflowNameFilter())  # Add filter, so we can inject the RPA workflow name
    queue_handler.addFilter(RpaArgoWorkflowNameFilter())  # Add filter for Argo workflow name
    queue_handler.addFilter(RpaModuleNameFilter())  # Add filter, so we can inject the RPA name
    queue_handler.addFilter(RpaWorkflowRunGuidFilter())  # Add filter for run GUID
    queue_handler.addFilter(RpaModuleRunGuidFilter())  # Add filter for run GUID

    # Set up the Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")) # Formatter only for console logging

    # Set up the backend-specific worker
    if backend == "elasticsearch":
        es_client = Elasticsearch([config.get("url")])
        index_name = config.get("index_name")
        #worker_thread = Thread(target=es_worker, args=(log_queue, es_client, index_name))
        try:
            # Check if Elasticsearch is available
            if not es_client.ping():
                raise ConnectionError("Elasticsearch server is unavailable.")
            worker_thread = Thread(target=es_worker, args=(log_queue, es_client, index_name))
        except Exception as e:
            print(f"Warning: {e}. Falling back to console logging.")
            backend = "console"  # Fallback to console logging
    # elif backend == "azure":
    #     connection_string = config.get("connection_string")
    #     worker_thread = Thread(target=azure_worker, args=(log_queue, connection_string))  
    elif backend == "console":
        worker_thread = None  # No worker thread needed for console logging     
    else:
        raise ValueError("Unsupported backend. Use 'elasticsearch' or 'loki'.")

    if worker_thread:
        worker_thread.daemon = True  # Exit when main program exits
        worker_thread.start()

    # Register shutdown_logging to automatically shut down logging on exit
    atexit.register(shutdown_logging)

    # Return a logger factory function
    def get_logger_factory(name):
        logger = logging.getLogger(name)
        if not logger.handlers:  # Avoid duplicate handlers
            logger.setLevel(logging.INFO)
            logger.addHandler(queue_handler)
            logger.addHandler(console_handler)
        return logger

    return get_logger_factory

# Function to shut down logging, ensuring all logs are processed
def shutdown_logging():
    global worker_thread
    if worker_thread is not None: # Check if thread exists
        log_queue.put(None)  # Signal worker to stop
        worker_thread.join() # Safe to call join now, warning in IDE is misleading
        worker_thread = None

# Automatically initialize logging on module import
# Comment out this line to revert to manual initialization
get_logger = setup_logging(backend=DEFAULT_BACKEND, config=DEFAULT_CONFIG)        