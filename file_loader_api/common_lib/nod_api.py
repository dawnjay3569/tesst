# Core libraries
from datetime import datetime, timedelta
import json
import os
import unicodedata
from urllib import request
import warnings

# External libraries
from dotenv import load_dotenv
import pandas as pd
import requests

# Internal libraries
from RPA_MODULES.common_lib.logging_config import get_logger
from RPA_MODULES.common_lib.oracle_insights import update_sql

#warnings.filterwarnings("ignore")

# Load environment variables
load_dotenv()

# Get a logger for this script
logger = get_logger("nod_api.py")

# NOD Voice First (Multi-search) & Second (Transactional) API Details
api_username = os.getenv("NOD_API_USERNAME")
api_password = os.getenv("NOD_API_PASSWORD")
authentication = os.getenv("NOD_API_AUTHENTICATION_URL")
multiSearchCriteria = os.getenv("NOD_API_MULTI_SEARCH_CRITERIA_URL")
getTransactionDetails = os.getenv("NOD_API_GET_TRANSACTION_DETAILS_URL")

proxy_ = {'http': v for k, v in request.getproxies().items() if k == 'http'}
header = {'content-type': 'application/json'}
get_transaction_details = "serviceprofile={}&transactionId={}&countryCode={}&archivalFlag={}"

# Multi-search API Data Details
db_column_name = {'resellerDomainName': 'RESELLER_DOMAIN_NAME', 'serviceProfile': 'SERVICE_PROFILE', 'country': 'COUNTRY', 'transactionType': 'TRANSACTION_TYPE',
                  'transactionId': 'TRANSACTION_ID', 'currentStatus': 'CURRENT_STATUS', 'telNumberStart': 'TEL_NUMBER_START', 'telNumberEnd': 'TEL_NUMBER_END',
                  'transactionCreationDate': 'TRANSACTION_CREATION_DATE', 'transactionLastUpdateDate': 'TRANSACTION_LAST_UPDATE_DATE', 'countryCode': 'COUNTRY_CODE',
                  'username': 'USERNAME', 'notes': 'NOTES', 'migrationFlag': 'MIGRATION'}
column_name = [
    'SERVICE PROFILE',
    'TRANSACTION_ID',
    'COUNTRY CODE',
    'TRANSACTION_TYPE',
    'TRANS_STATUS',
    'USERNAME',
    'TRANSACTION_DATE',
    'PORTING_DT_TM',
    'PORTING_WINDOW',
    'PORTING_FIRST_NAME',
    'PORTING_LAST_NAME',
    'TELEPHONE_NUMBER_START',
    'TELEPHONE_NUMBER_END',
    'DIFF_RANGE',
    'MAIN_BILLING_NO',
    'CURRENT_PROVIDER',
    'SINGLE_LINE',
    'MULTI_LINE',
    'CUSTOMER_NAME',
    'CREATED_DATE',
    'TRANSACTION_DESC',
    'VAT_NUMBER',
    'POSTAL_CODE',
    'PREMISE_NUMBER',
    'STREET_NAME',
    'CITY',
    'WBCI_USER',
    'WBCI_ID'
]
transaction_lst_to_date = datetime.date(datetime.now()).strftime("%d-%m-%Y")
transaction_lst_frm_date = datetime.date(datetime.now() - timedelta(hours=24)).strftime("%d-%m-%Y")
lst_status_mapping = ['Cancelled', 'Accepted', 'Rejected', 'Expired', 'Delayed', 'Initiate Port In', 'Submitted to operator', 'Firm order commitment',
                      'Customer Feedback Awaited', 'Completed', 'Porting initiated', 'Validation In Progress', 'Confirmed', 'Confirmation awaited', 'In Progress']
request_data = {"pageNo": 1, "limit": 5000, "transactionStatus": lst_status_mapping, "globalSearch": None, "totalCount": None, "searchableProfiles": None,
                "transactionType": ["New Port In"], "transactionLastUpdateFromDate": transaction_lst_frm_date, "transactionLastUpdateToDate": transaction_lst_to_date}


def read_multisearch_api():
    try:
        res_body = {'username': api_username, 'password': api_password}
        
        try:
            r = requests.post(authentication, headers=header, data=json.dumps(res_body))
        except Exception as e:
            logger.warning(f"Direct authentication failed: {e}. Retrying with proxy.")
            try:
                r = requests.post(authentication, headers=header, data=json.dumps(res_body), proxies=proxy_)
            except Exception as e2:
                logger.error(f"Authentication failed with proxy as well: {e2}. Exiting.")
                raise RuntimeError(f"Authentication failed with proxy as well: {e2}")
        
        if not r.status_code == 200:
            logger.error(f"Authentication Failed for {authentication}. User Details: {res_body['username']} and Status Code: {r.status_code}")
            raise RuntimeError(f"Authentication Failed for {authentication}. User Details: {res_body['username']} and Status Code: {r.status_code}")
        
        header['Authorization'] = f'Bearer {list(r.json().values())[0]}'
        request_data["countryCodes"] = ['GB', 'BE', 'ES', 'DE', 'IT', 'FR']
        
        try:
            res = requests.post(multiSearchCriteria, headers=header, data=json.dumps(request_data))
        except Exception as e:
            logger.warning(f"Direct request to {multiSearchCriteria} failed: {e}. Retrying with proxy.")
            try:
                res = requests.post(multiSearchCriteria, headers=header, data=json.dumps(request_data), proxies=proxy_)
            except Exception as e2:
                logger.error(f"Request to {multiSearchCriteria} failed with proxy as well: {e2}. Exiting.")
                raise RuntimeError(f"Request to {multiSearchCriteria} failed with proxy as well: {e2}")
        
        # Checking API Results
        if not res.status_code == 200:
            logger.error(f"Execution Failed for {multiSearchCriteria}. User Details: {res_body['username']} and Status Code: {res.status_code}")
            raise RuntimeError(f"Execution Failed for {multiSearchCriteria}. User Details: {res_body['username']} and Status Code: {res.status_code}")
        
        # Preparing Dataframe to return
        df = pd.DataFrame.from_records(res.json()['searchableProfiles'])
        df = df.map(str)
        df = df[['resellerDomainName', 'serviceProfile', 'country', 'transactionType',
                 'transactionId', 'currentStatus', 'telNumberStart', 'telNumberEnd',
                 'transactionCreationDate', 'transactionLastUpdateDate', 'countryCode',
                 'username', 'notes', 'migrationFlag']]
        df.rename(columns=db_column_name, inplace=True)
        return df
    except Exception as err:
        logger.error(f"Error in read_multisearch_api: {err}")
        


def read_transaction_api():
    try:
        sql = "select distinct sv1 as service_profile, uv as transaction_id,sv2 as country_code, 'Yes' as archivalFlag from rpa_inputs.nod_voice_transaction_details where processed_by is null and length(sv4) > 4"
        data_df = update_sql(sql)
        res_body = {'username': api_username, 'password': api_password}
        r = requests.post(authentication, headers=header, data=json.dumps(res_body))
        
        if not r.status_code == 200:
            logger.error(f"Authentication Failed for {authentication}. User Details: {res_body['username']} and Status Code: {r.status_code}")
            raise RuntimeError(f"Authentication Failed for {authentication}. User Details: {res_body['username']} and Status Code: {r.status_code}")
        
        header['Authorization'] = f'Bearer {list(r.json().values())[0]}'
        final_df = pd.DataFrame(columns=column_name)
        for i in range(len(data_df)):
            current_provider = requests.get(getTransactionDetails, headers=header, params=get_transaction_details
                                            .format(*data_df.iloc[i]))
            current_provider.json()
            if not current_provider.status_code == 200:
                logger.error(f"Some error occurred while fetching data from {getTransactionDetails} API. User Details: {res_body['username']} and Status Code: {current_provider.status_code}")
                raise RuntimeError(f"Some error occurred while fetching data from {getTransactionDetails} API. User Details: {res_body['username']} and Status Code: {current_provider.status_code}")
            
            if current_provider.text.find('query') < 0:
                continue
            country_code = data_df["COUNTRY_CODE"][i].upper()
            for k, l in enumerate(current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList']):
                lst_api_data = [x for x in data_df.iloc[i][:-1]]
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'trans_type' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['trans_type'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'trans_status' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['trans_status'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'username' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['username'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'trans_date' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['trans_date'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'porting_dt_tm' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['porting_dt_tm'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'porting_window' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['porting_window'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'porting_first_name' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['porting_first_name'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'porting_last_name' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['porting_last_name'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'telephoneNumberStart' in \
                        current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'][k]:
                    lst_api_data.append(current_provider.json()[
                                            'queryTransSummaryList'][0]['telephoneNumberList'][k][
                                            'telephoneNumberStart'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'telephoneNumberEnd' in \
                        current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'][k]:
                    lst_api_data.append(current_provider.json()[
                                            'queryTransSummaryList'][0]['telephoneNumberList'][k]['telephoneNumberEnd'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'diffRange' in current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'][k]:
                    lst_api_data.append(current_provider.json()[
                                            'queryTransSummaryList'][0]['telephoneNumberList'][k]['diffRange'])
                if current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'main_billing_no' in current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'][
                    k]:
                    lst_api_data.append(current_provider.json()[
                                            'queryTransSummaryList'][0]['telephoneNumberList'][k]['main_billing_no'])
                elif current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'main_billing_no' in current_provider.json()['queryTransSummaryList'][0]: \
                        lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['main_billing_no'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'current_provider' in \
                        current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'][k]:
                    lst_api_data.append(current_provider.json()[
                                            'queryTransSummaryList'][0]['telephoneNumberList'][k]['current_provider'])
                elif current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'current_provider' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['current_provider'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'single_line' in current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'][k]:
                    lst_api_data.append(current_provider.json()[
                                            'queryTransSummaryList'][0]['telephoneNumberList'][k]['single_line'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'].__len__() > 0 and \
                        'multi_line' in current_provider.json()['queryTransSummaryList'][0]['telephoneNumberList'][k]:
                    lst_api_data.append(current_provider.json()[
                                            'queryTransSummaryList'][0]['telephoneNumberList'][k]['multi_line'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'customer_name' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['customer_name'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'createdDate' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['createdDate'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'trans_desc' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['trans_desc'])
                else:
                    lst_api_data.append('None')
                if country_code == "ES":
                    if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                            'cif_nif' in current_provider.json()['queryTransSummaryList'][0]:
                        cif_nif = unicodedata.normalize('NFD',
                                                        current_provider.json()['queryTransSummaryList'][0][
                                                            'cif_nif']).encode('ascii', 'ignore').decode(
                            "utf-8").title()
                        lst_api_data.append(cif_nif)
                    else:
                        lst_api_data.append('None')
                else:
                    if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                            'vat_number' in current_provider.json()['queryTransSummaryList'][0]:
                        lst_api_data.append(
                            current_provider.json()['queryTransSummaryList'][0]['vat_number'])
                    else:
                        lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'postal_code' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['postal_code'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'premise_number' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['premise_number'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'street_name' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['street_name'])
                else:
                    lst_api_data.append('None')
                if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                        'city' in current_provider.json()['queryTransSummaryList'][0]:
                    lst_api_data.append(current_provider.json()['queryTransSummaryList'][0]['city'])
                else:
                    lst_api_data.append('None')
                if country_code == "DE":
                    if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                            'WBCI Registered user' in current_provider.json()['queryTransSummaryList'][0]:
                        wbci_user = unicodedata.normalize('NFD', current_provider.json()['queryTransSummaryList'][0][
                            'WBCI Registered user']).encode('ascii', 'ignore').decode("utf-8").title()
                        lst_api_data.append(wbci_user)
                    else:
                        lst_api_data.append('None')
                    if current_provider.json()['queryTransSummaryList'].__len__() > 0 and \
                            'WBCI ID' in current_provider.json()['queryTransSummaryList'][0]:
                        wbci_id = unicodedata.normalize('NFD', current_provider.json()['queryTransSummaryList'][0][
                            'WBCI ID']).encode('ascii', 'ignore').decode("utf-8").title()
                        lst_api_data.append(wbci_id)
                    else:
                        lst_api_data.append('None')
                else:
                    lst_api_data.append('None')
                    lst_api_data.append('None')
                data = dict(zip(column_name, lst_api_data))
                #final_df = final_df._append(data, ignore_index=True)
                final_df = pd.concat([final_df, pd.DataFrame([data])], ignore_index=True)
        return final_df
    except Exception as err:
        logger.error(f"Error in read_transaction_api: {err}")


if __name__ == '__main__':
    # Read Multi-search API Data
    multi_search_df = read_multisearch_api()
    if not multi_search_df.empty:
        print(multi_search_df)
    else:
        print("No data found in Multi-search API.")

    # Read Transactional API Data
    transaction_df = read_transaction_api()
    if not transaction_df.empty:
        print(transaction_df)
    else:
        print("No data found in Transactional API.")