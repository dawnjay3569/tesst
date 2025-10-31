# Core libraries
import time
import os


# External libraries
from dotenv import load_dotenv
from selenium.webdriver.common.keys import Keys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Internal libraries
from RPA_MODULES.common_lib.logging_config import get_logger
# Get a logger for this script
logger = get_logger("selenium_utils.py")
# Load the environment variables
load_dotenv()

# Use remote Selenium Grid driver if set to "true" (case-insensitive)
USE_REMOTE_DRIVER = os.getenv("USE_REMOTE_WEB_DRIVER").lower() == "true"

# Run browser in headless mode if set to "true"
IS_HEADLESS = os.getenv("IS_WEB_DRIVER_HEADLESS").lower() == "true"

# Path to the Chrome WebDriver executable
CHROME_PATH = os.getenv("CHROME_DRIVER_PATH")

# Selenium Grid URL for remote WebDriver execution
SELENIUM_GRID_URL = os.getenv("SELENIUM_GRID_URL")

def get_webdriver(applicationname):
    """
    Initialize and return a Selenium WebDriver instance.

    Args:
        applicationname: Name of the application (for logging purposes).

    Returns:
        Selenium WebDriver instance.
    """
    try:
        logger.info(f"Initializing WebDriver for mdoule: {applicationname}")

        # Set up Chrome options
        chrome_options = webdriver.ChromeOptions()
        #Rajesh:added for attachment download and transfer to local machine, specifically for RPA's which require downloading files
        chrome_options.add_experimental_option("prefs", {
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True  # <-- This should download PDFs instead of opening them
        })
        logger.debug("Created ChromeOptions object.")

        if IS_HEADLESS:
            chrome_options.add_argument("--headless")
            logger.info("Enabled headless mode for Chrome.")

        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")
        logger.debug("Added Chrome options for browser configuration.")
        #Rajesh:added for attachment download and transfer to local machine
        chrome_options.set_capability("se:downloadsEnabled", True)
        # Use Selenium Grid remote WebDriver or local ChromeDriver
        if not USE_REMOTE_DRIVER:
            logger.info(f"Using local ChromeDriver at path: {CHROME_PATH}")
            service = Service(executable_path=CHROME_PATH)
            web_driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            logger.info(f"Using remote Selenium Grid at URL: {SELENIUM_GRID_URL}")
            web_driver = webdriver.Remote(command_executor=SELENIUM_GRID_URL, options=chrome_options)

        # Set default zoom level (75%)
        logger.debug("Setting default page scale factor to 0.75.")
        web_driver.execute_cdp_cmd("Emulation.setPageScaleFactor", {"pageScaleFactor": 0.75})

        logger.info(f"WebDriver initialization successful for : {applicationname}")
        return web_driver
    except Exception as e:
        logger.error(f"Error initializing WebDriver for {applicationname}: {e}")
        return None

def click_element(driver, selector, wait=2, filename=None, by=By.XPATH, 
                  action="click", value=None, pre_wait=30, err_handle="N"):
    """
    Interact with a web element using Selenium WebDriver.

    Args:
        driver: Selenium WebDriver instance.
        selector: The selector string to locate the element.
        wait: Time to wait after performing the action (in seconds).
        filename: Optional filename for screenshots (not used here).
        by: Selenium By strategy (default: By.XPATH).
        action: Action to perform: "click", "send", "actionchain", "value", etc.
        value: Value to send if action is "send" or "actionchain".
        pre_wait: Max wait time for element to be clickable.
        err_handle: Error handling flag (not used here).

    Returns:
        True if action is successful, value/text if requested, False otherwise.
    """
    try:
        logger.info(f"Waiting for element '{selector}' by '{by}' (timeout: {pre_wait}s)")
        wait_obj = WebDriverWait(driver, pre_wait)
        # Wait until the element is clickable
        element = wait_obj.until(EC.element_to_be_clickable((by, selector)))
        logger.info(f"Element found: '{selector}' (action: {action})")

        if action.lower() == "click":
            element.click()
            logger.info(f"Clicked element: '{selector}'")
        elif action.lower() in ["send", "actionchain"]:
            try:
                element.clear()
                logger.info(f"Cleared element: '{selector}'")
            except Exception as e:
                logger.warning(f"Error clearing element {selector}: {e}")
            current_value = element.get_attribute("value")
            if current_value:
                # Remove existing value
                element.send_keys(Keys.BACKSPACE * 50 + Keys.DELETE * 50)
                logger.info(f"Cleared existing value for element: '{selector}'")
            element.send_keys(value)
            logger.info(f"Sent keys '{value}' to element: '{selector}'")
            if action.lower() == "actionchain":
                webdriver.ActionChains(driver).send_keys(Keys.ENTER).perform()
                logger.info(f"Performed ActionChain ENTER on element: '{selector}'")
        elif action.lower()=="getelement":
            return element
        # This will return list of  elements
        elif action.lower()=="list of elements":
            elements = wait_obj.until(EC.presence_of_all_elements_located((by, selector)))
            return elements
        # As discussed with Rajesh to keep things generic
        # Please don't pass ["value", "innertext", "title", "id", "text"]
        # Do the operations from your side

        # elif action.lower() == "value":
        #     val = element.get_attribute("value")
        #     logger.info(f"Got value '{val}' from element: '{selector}'")
        #     return val
        # elif action.lower() == "innertext":
        #     val = element.get_attribute("innerText")
        #     logger.info(f"Got innerText '{val}' from element: '{selector}'")
        #     return val
        # elif action.lower() == "title":
        #     val = element.get_attribute("title")
        #     logger.info(f"Got title '{val}' from element: '{selector}'")
        #     return val
        # elif action.lower() == "id":
        #     val = element.get_attribute("id")
        #     logger.info(f"Got id '{val}' from element: '{selector}'")
        #     return val
        # elif action.lower() == "text":
        #     val = element.text
        #     logger.info(f"Got text '{val}' from element: '{selector}'")
        #     return val

        time.sleep(wait)  # Wait for any UI updates
        return True
    except Exception as e:
        logger.error(f"Error interacting with element {selector} (action: {action}): {e}")
        raise e
        # return False