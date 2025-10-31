# Author: Piotr & Rajesh 
# Date: 2024-06-09
# Project: RPA 2.0 Migration
# Description: Common Siebel RPA library functions for Selenium automation.
# -----------------------------------------------------------------------------


# Core libraries
import time
import os
# External libraries#Rajesh
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select  # @Sumit : 21-July-2025 : import for date pick function
from datetime import datetime  # @Sumit : 21-July-2025 : import for date pick function
from dotenv import load_dotenv

# Internal libraries
# from RPA2FolderStructure.common_lib.rpa_input_data_configuration import *
from RPA_MODULES.common_lib.oracle_insights import update_sql
from RPA_MODULES.common_lib.logging_config import get_logger
from RPA_MODULES.common_lib.selenium_utils import get_webdriver  # Utility for getting WebDriver instance

# Load environment variables from a .env file
load_dotenv()

# Siebel application base URL
SIEBEL_URL = os.getenv("SIEBEL_APP_WEB_URL")

# Get a logger for this script
logger = get_logger("siebel_rpa_lib.py")

# Use remote Selenium Grid driver if set to "true" (case-insensitive)
USE_REMOTE_DRIVER = os.getenv("USE_REMOTE_WEB_DRIVER").lower() == "true"

# Run browser in headless mode if set to "true"
IS_HEADLESS = os.getenv("IS_WEB_DRIVER_HEADLESS").lower() == "true"

# Path to the Chrome WebDriver executable
CHROME_PATH = os.getenv("CHROME_DRIVER_PATH")

# Selenium Grid URL for remote WebDriver execution
SELENIUM_GRID_URL = os.getenv("SELENIUM_GRID_URL")

# Mapping of Siebel field names to their pick query string templates
SIEBEL_FIELD_PICK_QUERY_STRINGS = {
    'Known Errors': '[Defect Number]="<value>"',
    'Applied Solution': '[Name]="<value>"',
    'Ordering Party': '[Party UId]="<value>"',
    'Ordering Party Address': '[COLT Primary Account Loc]="<value>"',
    'Ordering Party Contact': '[COLT Primary Account Number]="<value>"',
    'Network Reference': '[COLT Network Reference]="<value>"',
    'Order Processing User': '[Login Name]="<value>"',
    'Technical Validation User': '[Login Name]="<value>"',
}


# @Sumit: 21-July-2025: added new fields in SIEBEL_FIELD_PICK_QUERY_STRINGS

def save_siebel_record(tmp_driver):
    """
    Saves the current Siebel record using Ctrl+S keyboard shortcut.
    :param tmp_driver: Selenium WebDriver instance
    :return: True if save is successful
    """
    try:
        # Create an ActionChains object to send keyboard shortcuts
        actions = ActionChains(tmp_driver)
        # Press and release Ctrl+S to trigger the save action in Siebel
        actions.key_down(Keys.CONTROL).send_keys('s').key_up(Keys.CONTROL).perform()
        # Wait for Siebel to finish processing the save
        wait_for_siebel_ready(tmp_driver)
        return True
    except Exception as e:
        # Print and raise any exceptions encountered
        print(f"Error saving Siebel record: {e}")
        raise


# @Sumit : 21-July-2025 : added new param new_rec to below function to further use in locate_and_search_siebel_record
def update_siebel_field(tmp_driver, element, field, value, new_rec=None):
    """
    Updates a Siebel field element with the specified value, handling different field types.
    :param tmp_driver: Selenium WebDriver instance
    :param element: WebElement representing the field to update
    :param field: Field name (string)
    :param value: Value to set in the field
    :return: True if update is successful
    """
    try:
        # Get the class and input type of the element for type-specific handling
        ele_class = element.get_attribute("class") if element else None
        input_type = element.get_attribute("type") if element else None

        # Handle autocomplete input fields
        if "ui-autocomplete-input" in ele_class and value:
            # Click the dropdown to show autocomplete options
            dropdown_span = element.find_element(By.XPATH,
                                                 "./following-sibling::span[contains(@class, 'siebui-icon-dropdown')]")
            dropdown_span.click()
            wait_for_siebel_ready(tmp_driver, 1)
            # Find the visible autocomplete list
            ul = tmp_driver.find_element(By.XPATH,
                                         "//ul[contains(@class, 'ui-autocomplete') and not(contains(@style, 'display: none'))]")
            li_items = ul.find_elements(By.TAG_NAME, "li")
            # Click the matching value in the list
            for li in li_items:
                if value.strip().lower() == li.text.strip().lower():
                    li.click()
                    wait_for_siebel_ready(tmp_driver, 2)
                    return True

        # Handle checkbox (boolean) fields
        if "siebui-ctrl-checkbox" in ele_class or input_type == "checkbox":
            is_checked = element.is_selected()
            should_check = bool(value)
            # Click to toggle if current state doesn't match desired state
            if is_checked != should_check:
                element.click()

        # Handle Siebel MVG (multi-value group) popup fields
        elif "siebui-ctrl-mvg" in ele_class:
            # Build the search string for the MVG popup
            field_expr = SIEBEL_FIELD_PICK_QUERY_STRINGS.get(field, f'[{field}]="<value>"')
            search_string = field_expr.replace("<value>", str(value))
            # Open the MVG popup
            dropdown_span = element.find_element(By.XPATH,
                                                 "./following-sibling::span[contains(@class, 'siebui-icon-mvg')]")
            dropdown_span.click()
            # Search for the record in the MVG applet
            locate_and_search_siebel_record(tmp_driver=tmp_driver, search_string=search_string,
                                            new_rec=new_rec)  # @Sumit : 21-July-2025 : calling locate_and_search_siebel_record with new param new_rec
            if not new_rec == "Y":  # @Sumit : 21-July-2025 : added condition to click below button only if not clicked in locate_and_search_siebel_record
                # Click the add button to select the record
                click_or_interact_with_element(tmp_driver,
                                               "//div[contains(@class,'siebui-mvg-btn-modifier')]//button[contains(@class,'siebui-icon-addrecords')]",
                                               action="click", err_handle="Y")
            # Click the OK/close button to confirm selection
            click_or_interact_with_element(tmp_driver,
                                           "//div[contains(@class,'siebui-popup-btm')]//button[contains(@class,'siebui-icon-closeapplet')]",
                                           action="click", err_handle="Y")

        # Handle Siebel pick (lookup) popup fields
        elif "siebui-ctrl-pick" in ele_class:
            # Build the search string for the pick popup
            field_expr = SIEBEL_FIELD_PICK_QUERY_STRINGS.get(field, f'[{field}]="<value>"')
            search_string = field_expr.replace("<value>", str(value))
            # Open the pick popup
            dropdown_span = element.find_element(By.XPATH,
                                                 "./following-sibling::span[contains(@class, 'siebui-icon-pick')]")
            dropdown_span.click()
            # Search for the record in the pick applet
            locate_and_search_siebel_record(tmp_driver=tmp_driver, search_string=search_string)
            # Click the OK/close button to confirm selection
            click_or_interact_with_element(tmp_driver,
                                           "//div[contains(@class,'siebui-popup-btm')]//button[contains(@class,'siebui-icon-pickrecord')]",
                                           action="click", err_handle="Y")

        # @Sumit: 21-July-2025 : Handle Siebel calendar (date picker) fields when the input is disabled
        elif not element.is_enabled() and "siebui-ctrl-date" in ele_class:
            pick_date_from_calendar(tmp_driver, value, element)

        # Handle standard input fields
        else:
            element.clear()
            element.send_keys(value)
        # Wait for Siebel to finish processing the update
        popup_text = check_siebel_popup(tmp_driver)
        if popup_text and "SBL-" in popup_text:
            raise Exception(f"Siebel error: {popup_text}")
        return True
    except Exception as e:
        print(f"Error updating Siebel field '{field}': {e}")
        raise


def click_or_interact_with_element(driver, selector, filename=None, by=By.XPATH, action="click", value=None,
                                   pre_wait=30, err_handle="N", overridefind=False):
    """
    Interacts with a web element based on the specified action.
    :param driver: Selenium WebDriver instance
    :param selector: The selector string (XPath or label)
    :param filename: Optional filename for logging
    :param by: Selenium By strategy (default: By.XPATH)
    :param action: Action to perform ("click", "update", "getelement")
    :param value: Value to use for update actions
    :param pre_wait: Wait time before action (not used here)
    :param err_handle: Error handling mode ("N" = raise, else print)
    :param overridefind: If True, always use find_element
    :return: True if successful, or the element if "getelement"
    """
    try:
        # Ensure Siebel is ready before interacting
        wait_for_siebel_ready(driver, 2)
        islistapplet = False
        # Locate the element based on action or override flag
        if action == "click" or action == "focus" or overridefind:
            # For click or override, use the provided selector directly
            element = driver.find_element(by, selector)
            # if element lenght is 1 then assign the first element to element variable else assign the list of elements to element variable
            # if len(element) == 1:
            #     element = element[0]
        else:
            # For other actions, try to find by aria-label or aria-roledescription
            element = driver.find_elements(by,
                                           f"//div[contains(@class,'siebui-applet-active')]//*[@aria-label='{selector}']")
            if len(element) == 0:
                element = driver.find_elements(by,
                                               f"//div[contains(@class,'siebui-applet-active')]//*[contains(@aria-label,'{selector}')]")
            if len(element) == 0:
                element = driver.find_elements(
                    by,
                    f"//div[contains(@class,'siebui-applet-active')]//tr[contains(@class,'ui-state-highlight') and contains(@class,'selected-row') and contains(@class,'ui-state-hover')]//*[@aria-roledescription='{selector}']"
                )
                islistapplet = True
            if len(element) == 0:  # @Sumit : 21-July-2025 : added specific search with prefix <body>
                element = driver.find_elements(by,
                                               f"//div[contains(@class,siebui-applet-active)]//*[starts-with(@aria-label, '<body>{selector}')]")

            if not element:  # @Sumit : 21-July-2025 : added a wildcard search based on aria-label
                element = driver.find_elements(by, f"//*[contains(@aria-label, '{selector}')]")

            element = element[0]
        # Perform the requested action
        if action.lower() == "getelement":
            # Return the element for further use
            return element
        if action.lower() == "click":
            # Click the element
            element.click()
        elif action.lower() == "focus":
            # this is required some times in siebel if a tag available in input click on td will bubble the event to a tag we need to avoid that when we are querying else it will change the context
            # focus the element
            # driver.execute_script("arguments[0].focus();", element)
            # driver.execute_script("arguments[0].setAttribute('tabindex', '-1'); arguments[0].focus();", element)
            driver.execute_script("""
              var event = new MouseEvent('click', {
                bubbles: true,
                cancelable: true,
                view: window
              });
              arguments[0].dispatchEvent(event);
            """, element)
        elif action.lower() == "update" and value is not None and value != "":
            # Update the element using the provided value
            if islistapplet:
                # Only proceed if the element does NOT already have an input child
                try:
                    element.find_element(By.TAG_NAME, "input")
                    # Input exists, do nothing special
                except:
                    # No input element, so click to focus and then update
                    element.click()
                element = element.find_element(By.TAG_NAME, "input")
            update_siebel_field(driver, element, selector, value)
        # Wait again for Siebel to be ready after the action
        wait_for_siebel_ready(driver, 2)
        return True
    except Exception as e:
        # Handle errors based on err_handle flag
        if err_handle == "N":
            # Optionally log missing XPath to database
            if filename:
                sql = f"INSERT INTO LOGS.XPATH_NOT_AVAILABLE (filename, xpath) VALUES ('{filename}', '{selector}')"
                try:
                    update_sql(sql)
                except Exception:
                    pass
            raise
        else:
            print(f"Error interacting with element {selector} (action: {action}): {e}")
            raise


# @Sumit: 21-July-2025: added 2 new parameters new_rec and value to handle new record addition and update value for expectional mvg fields
def locate_and_search_siebel_record(tmp_driver, search_string, new_rec=None, value=None):
    """
    Locate and search for a record in the Siebel application.
    :param driver: Selenium WebDriver instance
    :param search_string: search string to locate the record example [Siebel Field Name]="<value>"
    """
    try:
        # Print debug info (can be replaced with logging)
        print("Rajesh")

        # Wait until Siebel is ready for interaction
        wait_for_siebel_ready(tmp_driver)

        # Prepare to send keyboard shortcuts
        actions = ActionChains(tmp_driver)

        # @Sumit: 21-July-2025: handle new record addition in MVG list applet and update value for exceptional MVG fields
        if new_rec == "Y":
            new_record_ele_btn = tmp_driver.find_element(By.XPATH,
                                                         "//button[contains(@class, 'siebui-icon-newrecord') and contains(@aria-label, 'Service Order Sub Type')]")
            new_record_ele_btn.click()
            ele = tmp_driver.find_element(By.XPATH, "//td[@class='edit-cell ui-state-highlight']/input")
            update_siebel_field(tmp_driver, ele, "", value, new_rec=None)

        # @Sumit: 21-July-2025: moved generic logic of locate and search to else block
        else:
            # Send ALT+Q to enter query mode in Siebel
            actions.key_down(Keys.ALT).send_keys('q').key_up(Keys.ALT).perform()

            # Wait for Siebel to process the query mode
            wait_for_siebel_ready(tmp_driver)

            # Find the input element in the highlighted editable cell
            ele = tmp_driver.find_element(By.XPATH, "//td[@class='edit-cell ui-state-highlight']/input")

            # If the element is a checkbox or textarea, move to the next input field
            while any(cls in ele.get_attribute("class").split() for cls in
                      ["siebui-ctrl-checkbox", "siebui-ctrl-textarea"]):
                # Send TAB to move to the next input
                ele.send_keys(Keys.TAB)
                wait_for_siebel_ready(tmp_driver)
                ele = tmp_driver.find_element(By.XPATH, "//td[@class='edit-cell ui-state-highlight']/input")
                print("Element has class 'Rajesh'")

            # Enter the search string into the input field
            ele.send_keys(search_string)
            # Press ENTER to execute the search
            ele.send_keys(Keys.ENTER)

            # Wait for Siebel to process the search
            wait_for_siebel_ready(tmp_driver)

        # Find the rows that are highlighted after the search
        rows = tmp_driver.find_elements(By.XPATH,
                                        "//div[contains(@class,'siebui-hilight')]//tr[contains(@class, 'ui-state-highlight')]")

        # If any rows are found, return them; otherwise, return False
        if len(rows) > 0:
            return rows
        else:
            return False
    except Exception as e:
        # Raise any exceptions encountered
        raise


def wait_for_siebel_ready(tmp_driver, explicit_wait_time=2):
    """
    Waits until the Siebel application is ready for interaction by checking the absence of the 'siebui-busy' class
    on the <html> element. This indicates that Siebel is not busy processing.

    :param tmp_driver: Selenium WebDriver instance
    :param explicit_wait_time: Time (in seconds) to wait between checks when Siebel is busy
    :return: True if Siebel is ready
    """
    try:
        flag = False
        while True:
            # Find the <html> element of the page
            html_element = tmp_driver.find_element(By.TAG_NAME, "html")
            # Get the value of the 'class' attribute
            class_attr = html_element.get_attribute("class")
            # If the Siebel UI is busy, indicated by 'siebui-busy' in the class attribute, wait and retry
            if "siebui-busy" in class_attr:
                # Wait for the specified time before checking again
                time.sleep(explicit_wait_time)
            else:
                # Optionally wait a bit more to ensure readiness
                time.sleep(1)
                # Set flag to True to indicate Siebel is ready
                flag = True
                break
        return flag
    except Exception as e:
        # Raise any exceptions encountered for upstream handling
        raise


def validate_ticket_status_and_symptom_date(tmp_driver, search_string):
    """
    Validates the ticket status and updates the 'Symptom Discovered Date Time' field if necessary.
    """
    try:
        # Search for the Siebel record using the provided search string
        if not locate_and_search_siebel_record(tmp_driver=tmp_driver, search_string=search_string):
            # Raise an exception if the record is not found
            raise Exception("siebel_rpa_lib_error: Record not found")

        # XPath for the Status field cell
        element_id = '//td[@aria-roledescription="Status"]'
        # rajesh: below code was there prviously so tried to keep it but with modified xpaths
        # Wait until Siebel is ready before interacting
        if wait_for_siebel_ready(tmp_driver=tmp_driver):
            # Find the Status field cell
            set_update_key1 = tmp_driver.find_element(By.XPATH, element_id)
            # Get the text value of the Status field
            str_updated_val = set_update_key1.text
            # If the status is not in the allowed LIST_STATUS, update the Symptom Discovered Date Time field
            if str_updated_val not in ['Cancelled', 'Done', 'Declined', 'Closed']:
                # Wait again for Siebel to be ready
                if wait_for_siebel_ready(tmp_driver=tmp_driver):
                    # Get the current value of the Symptom Discovered Date Time field
                    sdd_value = tmp_driver.find_element(By.XPATH,
                                                        '//td[@aria-roledescription="Symptom Discovered Date Time"]').text
                    # If the field is empty or too short, update it
                    if len(sdd_value) < 2:
                        # Click the cell to activate the input
                        tmp_driver.find_element(By.XPATH,
                                                '//td[@aria-roledescription="Symptom Discovered Date Time"]').click()
                        # Wait for Siebel to be ready after clicking
                        wait_for_siebel_ready(tmp_driver=tmp_driver)
                        # Find the input element for the field
                        sdd_val = tmp_driver.find_element(By.XPATH,
                                                          '//td[@aria-roledescription="Symptom Discovered Date Time"]/input')
                        # Enter the default date value
                        sdd_val.send_keys('01/1/2003 00:00:00')
        # Return True if the operation completes successfully
        return True
    except Exception as e:
        # Raise any exceptions encountered for upstream handling
        raise


def goto_siebel_view(tmp_driver, view_name):
    """
    Navigates to the specified Siebel view using the SiebelApp JavaScript API.

    :param tmp_driver: Selenium WebDriver instance
    :param view_name: Name of the Siebel view to navigate to
    :return: True if navigation is successful
    """
    try:

        # Use JavaScript execution to call Siebel's GotoView function, this is api call to change the view more reliable than clicking on screen tabs
        tmp_driver.execute_script(f"SiebelApp.S_App.GotoView('{view_name}')")
        # Wait for Siebel to finish loading the new view
        wait_for_siebel_ready(tmp_driver, 2)
        # Return True to indicate successful navigation
        return True
    except Exception as e:
        # Raise any exceptions encountered for upstream handling
        raise


def login_to_siebel(module_name=None):
    # Siebel login credentials
    SIEBEL_USERNAME = os.getenv(module_name.upper() + "_USERNAME")
    SIEBEL_PASSWORD = os.getenv(module_name.upper() + "_PASSWORD")
    siebel_user = SIEBEL_USERNAME
    siebel_password = SIEBEL_PASSWORD
    try:
        siebel_url = f"{SIEBEL_URL}/siebel/app/ecommunications/enu?SWECmd=Start"
        # Initialize the WebDriver instance from the utility function
        web_driver=get_webdriver(module_name)
        # # Set up Chrome options
        # chrome_options = webdriver.ChromeOptions()
        # #Rajesh:added for attachment download and transfer to local machine, specifically for RPA's which require downloading files
        # chrome_options.add_experimental_option("prefs", {
        #     "download.prompt_for_download": False,
        #     "plugins.always_open_pdf_externally": True  # <-- This should download PDFs instead of opening them
        # })
        # if IS_HEADLESS:
        #     chrome_options.add_argument("--headless")  # Run Chrome in headless mode

        # chrome_options.add_argument("--disable-extensions")
        # chrome_options.add_argument('--ignore-certificate-errors')
        # chrome_options.add_argument('--ignore-ssl-errors')
        # chrome_options.add_argument('--allow-running-insecure-content')

        # chrome_options.add_argument("--disable-gpu")  # Disable GPU acceleration
        # chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
        # chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
        # chrome_options.add_argument("--remote-debugging-port=9222")  # Enable remote debugging
        # #Rajesh:added for attachment download and transfer to local machine
        # chrome_options.set_capability("se:downloadsEnabled", True)
        # # Use Selenium Grid remote WebDriver instead or local ChromeDriver
        # if not USE_REMOTE_DRIVER:
        #     # web_driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=CHROME_PATH)
        #     service = Service(executable_path=CHROME_PATH)
        #     web_driver = webdriver.Chrome(service=service, options=chrome_options)
        # else:
        #     # web_driver = webdriver.Remote(command_executor=SELENIUM_GRID_URL,options=chrome_options)
        #     web_driver = webdriver.Remote(command_executor=SELENIUM_GRID_URL, options=chrome_options)

        # # Set default zoom level (75%)
        # # web_driver.get('chrome://settings/')
        # # web_driver.execute_script('chrome.settingsPrivate.setDefaultZoom(0.75);')
        # web_driver.execute_cdp_cmd("Emulation.setPageScaleFactor", {"pageScaleFactor": 0.75})

        # Navigate to Siebel URL and maximize window
        web_driver.get(siebel_url)
        web_driver.maximize_window()

        # Perform login actions using cxp
        # Enter the Siebel username in the login form
        click_or_interact_with_element(
            web_driver,
            '//*[@name="SWEUserName"]',  # XPath for the username input field
            by='xpath',
            action='update',  # Action to send keys (enter text)                      # No wait before action
            value=siebel_user,  # The username value to enter
            overridefind=True
        )
        # Enter the Siebel password in the login form
        click_or_interact_with_element(web_driver, '//*[@name="SWEPassword"]', by='xpath', action='update',
                                       value=siebel_password,  # The username value to enter
                                       overridefind=True)
        # click on the sumit button in login form
        click_or_interact_with_element(web_driver, '//div[@class="siebui-login-btn"]/a')
        # time.sleep(2)
        # wait_for_element(web_driver,'','',2)
        try:
            # if web_driver.find_element_by_xpath('//*[@id="statusBar"]'):
            #     err_msg = web_driver.find_element_by_xpath('//*[@id="statusBar"]').text
            #     if 'SBL-UIF' in err_msg:
            #         log_login_error('Siebel', socket.gethostname().upper(), siebel_user + ' ' + getpass.getuser(), err_msg)
            if click_or_interact_with_element(web_driver, '//*[@id="statusBar"]'):
                err_msg = click_or_interact_with_element(web_driver, '//*[@id="statusBar"]').text
                if 'SBL-UIF' in err_msg:
                    raise Exception(f"Siebel login failed: {err_msg}")
        except Exception as e:
            pass
        return web_driver
    except Exception as e:
        print(f"Error encountered: {e}")
        if web_driver is not None:
            web_driver.quit()
        raise


def logout_siebel(tmp_driver):
    try:
        # Click the Siebel toolbar settings button to open the menu
        # cxp(tmp_driver, 'siebui-toolbar-settings', 0, 'web_login', 'id')
        # Click the logout button in the toolbar menu
        # cxp(tmp_driver, 'tb_item_4', 0, 'web_login', 'id')

        # Trigger Ctrl+Shift+X keyboard shortcut to log out in siebel application
        actions = ActionChains(tmp_driver)
        actions.key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys('x').key_up(Keys.SHIFT).key_up(
            Keys.CONTROL).perform()
    except:
        pass


def check_siebel_popup(tmp_driver):
    """
    Checks if a Siebel popup is displayed and returns its text if available.
    :param tmp_driver: Selenium WebDriver instance
    :return: Text of the popup if displayed, otherwise None
    """
    try:
        # Find the popup element by ID
        popup_element = tmp_driver.find_element(By.ID, "_sweview_popup")
        # Check if the popup is displayed
        if popup_element.is_displayed():
            popup_text = popup_element.text
            btn_accept = click_or_interact_with_element(tmp_driver, by=By.ID, selector="btn-accept")
            btn_accept.click()
            return popup_text
    except Exception as e:
        # If no popup is found or an error occurs, return None
        return None


# @Sumit : 21-July-2025 : Added below date-pick function
def pick_date_from_calendar(driver, value, element):
    """
    Selects a date from a Siebel calendar popup using the provided value.

    :param driver: Selenium WebDriver instance
    :param value: Date string in format "YYYY-MM-DD HH:MM:SS"
    :param element: WebElement for the date input field
    :return: True if date selection is successful, False otherwise
    """
    try:
        logger.info(f"Attempting to pick date '{value}' from calendar.")
        # Parse the input date string to a datetime object
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        day = str(dt.day)  # Day as string (no leading zero)
        month_index = dt.month - 1  # Month dropdown uses zero-based index
        year = str(dt.year)

        logger.debug(f"Parsed date: year={year}, month_index={month_index}, day={day}")

        # Locate and click the calendar icon next to the input element
        calendar_icon = element.find_element(By.XPATH, "following-sibling::span[contains(@class, 'siebui-icon-date')]")
        calendar_icon.click()
        logger.info("Clicked calendar icon.")

        # Wait for the calendar popup to appear
        wait_for_siebel_ready(driver, 2)
        calendar_popup = driver.find_element(By.CLASS_NAME, "ui-datepicker")
        logger.info("Calendar popup appeared.")

        # Select the year from the dropdown
        year_dropdown = calendar_popup.find_element(By.CLASS_NAME, "ui-datepicker-year")
        Select(year_dropdown).select_by_visible_text(year)
        logger.info(f"Selected year: {year}")

        # Select the month from the dropdown
        month_dropdown = calendar_popup.find_element(By.CLASS_NAME, "ui-datepicker-month")
        Select(month_dropdown).select_by_index(month_index)
        logger.info(f"Selected month index: {month_index}")

        # Click the day in the calendar
        day_element = calendar_popup.find_element(By.XPATH, f".//a[text()='{day}']")
        day_element.click()
        logger.info(f"Selected day: {day}")

        return True

    except Exception as e:
        # Log error and return False if any step fails
        logger.error(f"[Error] Failed to pick date '{value}': {e}")
        return False

