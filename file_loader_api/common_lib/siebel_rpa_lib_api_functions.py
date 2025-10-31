# Core libraries
import getpass
import os
import re
import requests as rq
import socket
import time
import warnings

# External libraries
#import cx_Oracle as cx
import oracledb
from dotenv import load_dotenv
import pandas as pd

# Internal libraries
from RPA_MODULES.common_lib.oracle_insights import update_sql
from RPA_MODULES.common_lib.logging_config import get_logger

load_dotenv()

# Get a logger for this script
logger = get_logger("siebel_rpa_lib_api_functions.py")

SIEBEL_URL=os.getenv('SIEBEL_APP_API_URL')
SIEBEL_USERNAME=os.getenv('SIEBEL_APP_API_USERNAME')
SIEBEL_PASSWORD=os.getenv('SIEBEL_APP_API_PASSWORD')
SIEBEL_DB_HOSTNAME=os.getenv('SIEBEL_ORACLE_DB_HOST')
SIEBEL_DB_PORT=os.getenv('SIEBEL_ORACLE_DB_PORT')
SIEBEL_DB_SERVICE_NAME=os.getenv('SIEBEL_ORACLE_DB_SERVICE_NAME')
SIEBEL_DB_USERNAME=os.getenv('SIEBEL_ORACLE_DB_USER')
SIEBEL_DB_PASSWORD=os.getenv('SIEBEL_ORACLE_DB_PASSWORD')

warnings.filterwarnings("ignore")

USERID = getpass.getuser()
HOSTNAME = socket.gethostname()

def logging_func(uv, filename, type, message):
    try:
        update_sql(f"""INSERT INTO INSIGHTS.RPA_EXEC_LOG(RPA,FILENAME,UV,SERVER,USERID,MTYPE,MESSAGE) 
        VALUES ('OLO_PORTAL_FUNCTIONS','{filename}','{uv}','{HOSTNAME}','{USERID}','{type}','{message}')""")
    except:
        pass


CRED_SIEBEL = {
    'user': SIEBEL_USERNAME,
    'password': SIEBEL_PASSWORD
}
siebel_url = f"{SIEBEL_URL}/siebel/app/eai_anon/enu?SWEExtSource=SecureWebService&SWEExtCmd=Execute"

CONN_INFO_SIEBEL = {
    'host': SIEBEL_DB_HOSTNAME,
    'port': SIEBEL_DB_PORT,
    'user': SIEBEL_DB_USERNAME,
    'psw': SIEBEL_DB_PASSWORD,
    'service': SIEBEL_DB_SERVICE_NAME,
}
# Mapping of RPA field names to Siebel API XML tags for ticket updates.
# This dictionary is used to convert RPA-side column names to the expected Siebel SOAP API field names.
TICKET_CONVERSION_TO_API = {
    'Ticket Id': 'SRNumber',      # 'Ticket Id' in RPA maps to 'SRNumber' in Siebel XML
    'Description': 'Description', # 'Description' in RPA maps to 'Description' in Siebel XML
}

# Mapping of RPA field names to Siebel API XML tags for activity updates.
# This dictionary is used to convert RPA-side column names to the expected Siebel SOAP API field names.
ACTIVITY_CONVERSION_TO_API = {
    'Activity Id': 'Id',      # 'Activity Id' in RPA maps to 'Id' in Siebel XML
    'Owner':'PrimaryOwnedBy' , # 'Owner' in RPA maps to 'PrimaryOwnedBy' in Siebel XML
    'Service Order Reference' : 'ServiceOrderNum', #'Service Order Reference' in RPA maps to 'ServiceOrderNum' in Siebel XML
}

CONVERSION_TO_API = {
    'Ticket_id': 'ServiceRequest',
    'TICKET_ID': 'ServiceRequest',
    'SERVICEREQUEST': 'ServiceRequest',
    'TYPE': 'Type',
    'DESCRIPTION': 'Subject',
    'Description': 'Subject',
    'Comments': 'Description',
    'COMMENTS': 'Description',
    'SUBJECT': 'Subject',
    'ACTIVITY_ID': 'Id',
    'ACTIVITY_NUMBER': 'Id',
    'Activities': 'Id',
    't_owner': 'Owner',
    'Owner': 'PrimaryOwnerId',
    'OLA REASON': 'PrimarySymptomCode',
    'ACT_STATUS': 'SRStatus',
    'ACTIVITY_STATUS': 'SRStatus',
    'STATUS': 'SRStatus',
    'CHNG_ROW_ID': 'ProjectId',
    'CHANGE_ID': 'ProjectId',
    'Tickets': 'SRNumber',
    'Project_Id': 'ProjectId',#Rajesh:19_feb_2025 added for simplification
    'Ticket Id': 'SRNumber',#"Rajesh RPA2 12-june-2025
    'Group': 'TTQueueName',
    'Known_Err': 'ListOfCOLTCCSRIBC_COLTKnownErrors#COLTCCSRIBC_COLTKnownErrors#COLTCCKnownError',
    'KE': 'ListOfCOLTCCSRIBC_COLTKnownErrors#COLTCCSRIBC_COLTKnownErrors#COLTCCKnownError',
    'Known_Error': 'ListOfCOLTCCSRIBC_COLTKnownErrors#COLTCCSRIBC_COLTKnownErrors#COLTCCKnownError',
    'Solution': 'ListOfCOLTCCSRIBC_COLTSolutions#COLTCCSRIBC_COLTSolutions#COLTCCName',
    'Solutions': 'ListOfCOLTCCSRIBC_COLTSolutions#COLTCCSRIBC_COLTSolutions#COLTCCName',
    'TT_ID': 'ServiceRequest',
    'CA_Descr': 'Subject',
    'SCD': 'COLTAsiaReportedResolutionTime',
    'OCN':'AccountLocation',#Rajesh 21-OCT-2024
    'Act_Owner': 'PrimaryOwnedBy',#Rajesh 21-OCT-2024
    'Start':'StartTime',#Rajesh 13-JAN-2025
    'DelayType':'SubType',#Rajesh 13-JAN-2025
    'END_DT':'PlannedCompletion', #Sumit 05-MAR-2025
    'Act_Group': 'ActivityQueueName', #Sugandhini 05-MAY-2025
    'Priority':'Priority', #Sugandhini 05-MAY-2025
    'Assessment Score':'AssessmentScore' #Sugandhini 08-May-2025
}

CONVERT_TO_UI = {
    'SRNUMBER': 'Tickets',
    'SERVICEREQUEST': 'Tickets',
    'TICKET_ID': 'Tickets',
    'TT_ID': 'Tickets',
    't_owner': 'Owner',
    'CA_Descr': 'Description'
}


def build_soap_envelope_activity_update(credentials, body):
    """
    Build the SOAP envelope for Siebel activity update.
    """
    return f'''
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:asi="http://siebel.com/asi/" xmlns:act="http://www.siebel.com/xml/Action_EMR">
            <soapenv:Header>
                <wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/07/secext">
                    <wsse:UsernameToken>
                        <wsse:Username>{credentials['user']}</wsse:Username>
                        <wsse:Password>{credentials['password']}</wsse:Password>
                    </wsse:UsernameToken>
                </wsse:Security>
            </soapenv:Header>
            <soapenv:Body>
                <asi:ActivityUpdateMSO_Input>
                    <act:ListOfActivity>
                        <act:Activity>{body}</act:Activity>
                    </act:ListOfActivity>
                </asi:ActivityUpdateMSO_Input>
            </soapenv:Body>
        </soapenv:Envelope>'''

def build_update_activity_body(fileData, connection=None):
    """
    Build the body for the Siebel activity update SOAP request.
    Handles special case for 'Id' column.
    """
    # fileData is a pandas Series (single row)
    body = ""
    for eValue in fileData.index:
        sTag, mTag, eTag = "<act:", "</act:", ">"
        if eValue == 'Id' and connection is not None and not str(fileData[eValue]).startswith("1-"):
            mapValue = getActivityID(fileData[eValue], connection)
        else:
            mapValue = fileData.get(eValue, "")
        body += sTag + eValue + eTag + str(mapValue) + mTag + eValue + eTag
        if eValue == 'SRStatus':
            body += '<act:DoneFlag>Y</act:DoneFlag>'
    return body

def UpdateActivity(fileData):
    time.sleep(.5)
    connstrCO = '{user}/{psw}@{host}:{port}/{service}'.format(
        **CONN_INFO_SIEBEL)
    #connection = cx.connect(connstrCO, encoding="UTF-8", nencoding="UTF-8")
    connection = oracledb.connect(connstrCO)
    body = build_update_activity_body(fileData,connection)
    envelope = build_soap_envelope_activity_update(CRED_SIEBEL, body)
    url = siebel_url
    soap_action = "'document/http://siebel.com/asi/:ActivityUpdateMSO'"
    try:
        textResponseQ1 = send_soap_request(envelope, soap_action, url)
        siebelException = extract_xml_tag_value(textResponseQ1, 'siebelf:errorstack')
        actID = extract_xml_tag_value(textResponseQ1, 'Id')
        if actID.startswith("1-"):
            sStatus = "Success"
        else:
            sStatus = "Failed"
        #import logging
        logger.info(f"Siebel activity update status: {sStatus}, ActivityID: {actID}, Exception: {siebelException}")
    except Exception as e:
        #import logging
        logger.error(f"Error updating Siebel activity: {e}")
        sStatus = "Failed"
    return sStatus

def getActivityID(n, connection):
    qry = """SELECT ROW_ID FROM SIEBEL.S_EVT_ACT where ACTIVITY_UID='{0}'""".format(n)
    df = pd.read_sql(qry, con=connection)
    return df.ROW_ID[0]

def build_soap_envelope_ticket_update(credentials, body):
    """
    Build the SOAP envelope for Siebel ticket update.
    Adds exception handling and raises any exception to the caller.
    """
    try:
        # Construct the SOAP envelope with provided credentials and body
        return f'''
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tic="http://siebel.com/Colt/Ticket" xmlns:col="http://www.oracle.com/xml/ColtSRIIO">
                <soapenv:Header>
                    <wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/07/secext">
                        <wsse:UsernameToken>
                            <wsse:Username>{credentials['user']}</wsse:Username>
                            <wsse:Password>{credentials['password']}</wsse:Password>
                        </wsse:UsernameToken>
                    </wsse:Security>
                </soapenv:Header>
                <soapenv:Body>
                    <tic:UpdateTicket_Input>
                        <col:ListOfColtsriio>
                            <!--Zero or more repetitions:-->
                            <col:ColtCcSrIbc>{body}</col:ColtCcSrIbc>
                        </col:ListOfColtsriio>
                    </tic:UpdateTicket_Input>
                </soapenv:Body>
            </soapenv:Envelope>'''
    except Exception as ex:
        # Raise any exception to be handled by the caller
        raise ex

def build_ticket_body(fileData):
    """
    Build the body for the Siebel ticket update SOAP request.
    Supports fileData as a pandas Series (single row).
    """
    try:
        # If fileData is a Series, use its index and values directly
        body = ""
        for eValue in fileData.index:
            sTag, mTag, eTag = "<col:", "</col:", ">"
            mapValue = fileData[eValue]
            body += sTag + eValue + eTag + str(mapValue) + mTag + eValue + eTag
        return body
    except Exception as ex:
        raise ex

def send_soap_request(envelope, soap_action, url):
    """
    Send the SOAP request and return the response text.
    """
    # Prepare HTTP headers for the SOAP request
    headers = {"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": soap_action}
    try:
        # Send the POST request to the SOAP endpoint with the envelope as payload
        response = rq.post(url=url, data=envelope.encode('utf-8'), headers=headers, verify=False)
        # Raise an exception if the HTTP request returned an unsuccessful status code
        response.raise_for_status()
        # Return the response content as text
        return response.text
    except Exception as e:
        # Log the error and re-raise the exception for the caller to handle
        logger.error(f"SOAP request failed: {e}")
        raise

def extract_xml_tag_value(xml: str, tag: str) -> str:
    """
    Extract the value for a given tag from the XML string.
    Returns the value between <tag> and </tag>.
    Raises any exception to the caller.
    """
    try:
        start = xml.find(f"<{tag}>")
        end = xml.find(f"</{tag}>")
        if start == -1 or end == -1:
            # Tag not found, return empty string
            return ""
        start += len(f"<{tag}>")
        return xml[start:end]
    except Exception as ex:
        # Raise any exception to be handled by the caller
        raise ex

def update_ticket(fileData):
    """
    Update a Siebel ticket using SOAP API.
    Modularized for clarity and reusability.
    Logs success and failure with different logger functions.
    """
    try:
        time.sleep(1)  # Wait to avoid rapid-fire requests
        body = build_ticket_body(fileData)  # Build SOAP body from ticket data
        envelope = build_soap_envelope_ticket_update(CRED_SIEBEL, body)  # Build SOAP envelope
        url = siebel_url
        soap_action = "'document/http://siebel.com/Colt/Ticket:UpdateTicket'"
        sStatus=True
        try:
            # Send SOAP request and get response
            textResponseQ1 = send_soap_request(envelope, soap_action, url)
            siebelException = extract_xml_tag_value(textResponseQ1, 'siebelf:errorstack')  # Extract error if any
            ticketID = extract_xml_tag_value(textResponseQ1, 'SRNumber')  # Extract ticket ID from response
            if ticketID.startswith("1-"):
                logger.info(f"Siebel API ticket update SUCCESS: TicketID: {ticketID}")
            else:
                logger.warning(f"Siebel API ticket update FAILED: TicketID: {ticketID}, Exception: {siebelException}")
                sStatus = False
        except Exception as e:
            # Log errors during SOAP request or response processing
            logger.error(f"Error sending SOAP request or processing response: {e}")
            sStatus = False
    except Exception as ex:
        # Log any other exceptions in the update_ticket function
        logger.error(f"Exception in update_ticket: {ex}")
        sStatus = False
        
    return sStatus

def build_soap_envelope_activity_insert(credentials, body, is_web_update=False):
    """
    Build the SOAP envelope for Siebel activity insert.
    Handles special footer for 'Web Update' type.
    """
    if is_web_update:
        footer = '''<act:ListOfRelatedContact>\n<act:RelatedContact>\n<act:ContactId>1-10VCW5P</act:ContactId>\n</act:RelatedContact>\n</act:ListOfRelatedContact>'''
    else:
        footer = ''
    return f'''
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:asi="http://siebel.com/asi/" xmlns:act="http://www.siebel.com/xml/Action_EMR">
            <soapenv:Header>
                <wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/07/secext">
                    <wsse:UsernameToken>
                        <wsse:Username>{credentials['user']}</wsse:Username>
                        <wsse:Password>{credentials['password']}</wsse:Password>
                    </wsse:UsernameToken>
                </wsse:Security>
            </soapenv:Header>
            <soapenv:Body>
                <asi:ActivityInsertMSO_Input>
                    <act:ListOfActivity>
                        <act:Activity>{body}{footer}</act:Activity>
                    </act:ListOfActivity>
                </asi:ActivityInsertMSO_Input>
            </soapenv:Body>
        </soapenv:Envelope>'''

def build_create_activity_body(fileData, colName, nRows):
    """
    Build the body for the Siebel activity insert SOAP request.
    Skips empty or 'Missing Value' fields and sanitizes XML input.
    """
    import re
    fileData.fillna("Missing Value", inplace=True)
    body = ""
    for eValue in colName:
        sTag, mTag, eTag = "<act:", "</act:", ">"
        mapValue = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\x85\xA0-\uD7FF\uE000-\uFFFD\u10000-\u10FFFF]', '', str(fileData.loc[nRows, eValue]))
        if mapValue == "Missing Value" or mapValue == '':
            continue
        body += f"\n\t\t\t\t\t{sTag}{eValue}{eTag}{mapValue}{mTag}{eValue}{eTag}"
    return body

def create_activity(lenCol, fileData, colName, nRows):
    """
    Create a Siebel activity using SOAP API.
    Modularized for clarity and reusability.
    """
    #import logging
    import re
    import time
    time.sleep(1)
    sStatus = "Failed"
    if fileData.shape[0] > 0:
        try:
            body = build_create_activity_body(fileData, colName, nRows)
            is_web_update = False
            try:
                if 'Type' in fileData.columns and fileData.at[nRows, 'Type'] == 'Web Update':
                    is_web_update = True
            except Exception:
                pass
            envelope = build_soap_envelope_activity_insert(CRED_SIEBEL, body, is_web_update)
            #logger_func('11', 'CA_TO_DO', 'INFO', envelope)
            url = siebel_url
            soap_action = "'document/http://siebel.com/asi/:ActivityInsertMSO'"
            textResponse = send_soap_request(envelope, soap_action, url)
            actID = extract_xml_tag_value(textResponse, 'Id')
            siebelException = extract_xml_tag_value(textResponse, 'siebelf:errorstack')
            if actID.startswith("1-"):
                sStatus = "Success"
            else:
                sStatus = "Failed"
            logger.info(f"Siebel activity create status: {sStatus}, ActivityID: {actID}, Exception: {siebelException}")
        except Exception as e:
            logger.error(f"Error creating Siebel activity: {e}")
            sStatus = "Failed"
    return sStatus