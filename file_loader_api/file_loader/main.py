# Core libraries
import ast
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import glob
import socket
import time

# External libraries
from dotenv import load_dotenv
import numpy as np
import pandas as pd

# Internal libraries
from RPA_MODULES.common_lib.logging_config import get_logger, set_rpa_workflow_name, set_rpa_module_name, set_rpa_argo_workflow_name, set_rpa_workflow_run_guid
from RPA_MODULES.common_lib.oracle_insights import update_sql
import fileloaderdecisionmaker
from oracle_oi_rtqm import update_sql_oi_rtqm

# Load environment variables
load_dotenv()

IS_FILELOADER_TEST = os.getenv("IS_FILELOADER_TEST", "True").lower() == "true"

# Get a logger for this script
logger = get_logger("file_loader.py")
set_rpa_module_name("file_loader") # This is set once for the whole module, not per script
set_rpa_workflow_name(os.getenv("RPA_NAME")) # This should be set from the argo workflow with environment variable
set_rpa_argo_workflow_name(os.getenv("ARGO_WORKFLOW_NAME")) # This should be set from the argo workflow with environment variable
set_rpa_workflow_run_guid(os.getenv("RPA_RUN_GUID")) # This should be set from the argo workflow with environment variable

def insert_to_oi_rtqm(data_to_insert, placeholder_list, table_columns, schema_table, action=None, load_action=''):
    try:
        if not str(schema_table).startswith("RPA_INPUTS"):
            # Call the truncate procedure with unqualified table name
            table_only = str(schema_table).split('.')[-1].strip().strip('"')
            try:
                update_sql_oi_rtqm(f"EXEC OI_RTQM.truncate_my_table('{table_only}')")
            except Exception:
                # Fallback to PL/SQL anonymous block
                update_sql_oi_rtqm(f"BEGIN OI_RTQM.truncate_my_table('{table_only}'); END;")
        update_sql_oi_rtqm("insert into " + str(schema_table) + "(" + str(table_columns) +
                           ") values ({value_placeholder_list})".format(value_placeholder_list=placeholder_list),
                           data_to_insert)
        if action and action != "NO_PROC":
            update_sql(action)
    except Exception as e:
        logger.error(f"Error inserting data into {schema_table}: {e}")
        pass

def movefile(filepath, processedpath, file):
    try:
        os.makedirs(processedpath, mode=0o755, exist_ok=True)
        os.chdir(filepath)
        src = os.path.join(filepath, file)
        filename, ext = os.path.splitext(file)
        dst_filename = f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}{ext}"
        dst = os.path.join(processedpath, dst_filename)
        shutil.move(src, dst)
    except Exception as e:
        logger.error(f"Error moving file {file} from {filepath} to {processedpath}: {e}")
        pass

if __name__ == "__main__":
    logger.info("Starting file loader script")
    mapping_df = pd.read_excel("Fileloader.xlsb", engine='pyxlsb')
    
    for index, row in mapping_df.iterrows(): # Iterate through each row in the excel sheet
        try: # Get the columns and clean the data
            logger.info(f"Parsing row {index} in Fileloader.xlsb")
            filePath = str(row['PATH'])
            schemaTable = row['TABLE_NAME']
            getColDict = str(row['COLUMN_MAPPING']).replace('nan', '')
            use_columns = str(row['USE_COLUMNS']).replace('nan', '')
            fileName = os.path.basename(filePath)
            filePath = os.path.dirname(filePath)
            logger.info(f"Processing file path: {filePath}, schema table: {schemaTable}, file name: {fileName}")
            try:
                os.chdir(filePath) # Change directory to the file path
                fileList = glob.glob(str(fileName) + "*.*") # List all files in the directory matching the file name pattern
            except Exception as e:
                logger.warning(f"Could not access directory {filePath} or list files: {e}")
                fileList = []
                pass
            if len(fileList) > 0: # If files are found in the directory, process each file
                for file in fileList:
                    try:
                        uniqueFilename = ""
                        var = int((time.time() - os.stat(file).st_mtime) / 3600) # Number of hours since last modification
                        if var > 1: # If files older than 1 hour than move to Unprocessed folder (if not in test mode)
                            if not IS_FILELOADER_TEST:
                                movefile(filePath, os.path.join(filePath, 'Unprocessed'), file)
                        else: # Process files modified within the last hour
                            file_extension = os.path.splitext(file) # Get file extension
                            Filename = Path(file).stem + "_" + str(time.strftime('%Y%m%d%H%M%S', time.gmtime
                            (os.path.getmtime(file)))) + ".xlsx" # Create a unique filename based on modification time
                            uniqueFilename = Path(file).stem + "_" + str((datetime.strptime(
                                time.strftime('%Y%m%d%H%M%S', time.gmtime(os.path.getmtime(file))), "%Y%m%d%H%M%S")
                                                                          + timedelta(hours=5, minutes=30)).strftime("%Y%m%d%H%M%S")) + str(file_extension[1]) # Unique filename with timnezone adjustment for database logging
                            sql = "SELECT UV FROM RPA_INPUTS.EXCEL_LOAD_TO_ORACLE WHERE UV = '" + \
                                  str(uniqueFilename) + "' AND PROCESSINGTIME IS NOT NULL"
                            isDataExist = update_sql(sql)
                            if isDataExist.empty:
                                logDF = pd.DataFrame(columns=["FILENAME", "UV", "SV1", "SV5"])
                                #logDF = logDF.append({'FILENAME': fileName, 'UV': uniqueFilename, 'SV1': schemaTable, 'SV5': str(socket.gethostname())}, ignore_index=True)
                                logDF = pd.concat([logDF, pd.DataFrame([{'FILENAME': fileName, 'UV': uniqueFilename, 'SV1': schemaTable, 'SV5': str(socket.gethostname())}])], ignore_index=True)
                                df = [tuple(x)[1:] for x in logDF.itertuples()]
                                logColumns = ','.join(x for x in logDF.columns)
                                value_placeholder_list = ', '.join(
                                    [':{0}'.format(x + 1) for x in range(len(logDF.columns))])
                                insert_to_oi_rtqm(schema_table='RPA_INPUTS.EXCEL_LOAD_TO_ORACLE', data_to_insert=df,
                                                  placeholder_list=value_placeholder_list, table_columns=logColumns)
                                if file_extension[1].lower() == ".xlsm":
                                    newFile = file.split(".")[0] + ".xls"
                                    if not IS_FILELOADER_TEST:
                                        shutil.copy(os.path.join(filePath, file), os.path.join(filePath, newFile))
                                    file = newFile
                                    fileDF = pd.read_excel(os.path.join(filePath, file), dtype="str", engine='openpyxl')
                                elif file_extension[1].lower() in [".xls",".xlsx"] and 'critical_child_circuit' \
                                        not in file_extension[0].lower():
                                    fileDF = pd.read_excel(os.path.join(filePath, file), dtype="str", engine='openpyxl')

                                elif file_extension[1].lower() in [".xls", ".xlsx"] and 'critical_child_circuit' in \
                                        file_extension[0].lower():
                                    fileDF = pd.read_excel(os.path.join(filePath, file), dtype="str", engine='openpyxl')
                                    try:
                                        fileDF['To'] = fileDF['To'].str.replace(r'\.\d+$', '', regex=True)
                                    except:
                                        pass

                                elif file_extension[1].lower() == ".csv":
                                    if use_columns == '' or use_columns == 'None':
                                        try:
                                            fileDF = pd.read_csv(os.path.join(filePath, file), sep=",", encoding="iso-8859-1")
                                        except:
                                            fileDF = pd.read_csv(os.path.join(filePath, file), sep="\t", encoding="iso-8859-1")
                                    else:
                                        use_columns_list = ast.literal_eval(use_columns)
                                        try:
                                            fileDF = pd.read_csv(os.path.join(filePath, file), sep=",", encoding="iso-8859-1", usecols=use_columns_list)
                                        except:
                                            fileDF = pd.read_csv(os.path.join(filePath, file), sep="\t", encoding="iso-8859-1", usecols=use_columns_list)
                                else:
                                    if not IS_FILELOADER_TEST:
                                        movefile(filePath, os.path.join(filePath, 'Unprocessed'), file)
                                if getColDict == "None" or getColDict == '':
                                    fileDF.columns = fileDF.columns.str.replace(" ", "_")
                                    if not schemaTable=='OI_RTQM.CRM_SCM_BO_RPA_Auto_Ticket_Creation':
                                        fileDF.columns = fileDF.columns.str.replace(".", "")
                                    fileDF.columns = fileDF.columns.str.replace("/", "_")
                                    fileDF.columns = fileDF.columns.str.replace("-", "_")
                                    fileDF = fileDF.replace(np.nan, '').replace('\n', '', regex=True)
                                    fileDF.rename({c: c[1:] for c in fileDF.columns if c.startswith('_')}, axis=1, inplace=True)
                                    #fileDF = fileDF.applymap(str)
                                    fileDF = fileDF.astype(str)
                                    finalInsertColumn = ','.join(['"' + x + '"' for x in fileDF.columns])
                                    data = [tuple(x)[1:] for x in fileDF.itertuples()]
                                    value_placeholder_list = ', '.join(
                                        [':{0}'.format(x + 1) for x in range(len(fileDF.columns))])
                                elif not(getColDict == "None" or getColDict == ''):
                                    colDict = ast.literal_eval(getColDict)
                                    try:
                                        if schemaTable=='OI_RTQM.orange_portal_file_comparison':
                                            fileDF['CommentaireClient'] = fileDF['CommentaireClient'].str.split("//", expand=True)[0]
                                            fileDF['CommentaireClient'] = fileDF['CommentaireClient'] + "//"
                                    except Exception as e:
                                        logger.error(f"Error processing column 'CommentaireClient' in {file}: {e}")
                                        pass
                                    if isinstance(colDict, dict):
                                        fileDF = fileDF.rename(columns=colDict, inplace=False)
                                    elif isinstance(colDict, list):
                                        fileDF.columns = colDict
                                    fileDF = fileDF.replace(np.nan, '').replace('\n', '', regex=True)
                                    #fileDF = fileDF.applymap(str)
                                    fileDF = fileDF.astype(str)
                                    finalInsertColumn = ','.join(['"' + x + '"' for x in fileDF.columns])
                                    data = [tuple(x)[1:] for x in fileDF.itertuples()]
                                    value_placeholder_list = ', '.join(
                                        [':{0}'.format(x + 1) for x in range(len(fileDF.columns))])
                                try:
                                    finalInsertColumn, data, value_placeholder_list = \
                                        fileloaderdecisionmaker.file_loader_decision_maker(
                                            filename=schemaTable.split(".")[-1], final_insert_column=finalInsertColumn,
                                            dataframe=fileDF, workbook_name=file)
                                except Exception as e:
                                    logger.warning(f"Error in file loader decision maker for {file}: {e}")
                                    pass
                                
                                insert_to_oi_rtqm(schema_table=schemaTable, data_to_insert=data,
                                                  placeholder_list=value_placeholder_list,
                                                  table_columns=finalInsertColumn.upper(), action=str(row['PROC']),
                                                  load_action=str(row['LOAD_ACTION']))
                                
                                update_sql(sql="UPDATE RPA_INPUTS.EXCEL_LOAD_TO_ORACLE SET PROCESSINGTIME = "
                                               "systimestamp WHERE UV = '" + str(uniqueFilename) + "'")
                                if not IS_FILELOADER_TEST:
                                    movefile(filePath, os.path.join(filePath, 'Processed'), file)
                                logger.info(f"Successfully processed file: {file}")
                    except FileNotFoundError as e:
                        logger.error(f"File not found: {file}. Error: {e}")
                        continue                  
        except Exception as e:
            logger.error(f"Error processing row {index} in mapping_df: {e}")
            continue