# Core libraries
import os
import requests
import base64
import zipfile
import io

# External libraries
from dotenv import load_dotenv
from selenium.webdriver.remote.file_detector import LocalFileDetector
from selenium.webdriver.common.by import By

# Internal libraries
from RPA_MODULES.common_lib.logging_config import get_logger

# Load the environment variables
load_dotenv()

# Get a logger for this script
logger = get_logger("selenium_grid_downloads_helper.py")

SELENIUM_GRID_URL = os.getenv("SELENIUM_GRID_URL")  # Set in your .env

def save_file(file_data, local_file_path):
    try:
        decoded = base64.b64decode(file_data)
        if decoded[:2] == b'PK':  # ZIP file signature
            with zipfile.ZipFile(io.BytesIO(decoded)) as zf:
                for name in zf.namelist():
                    with open(local_file_path, "wb") as f:
                        f.write(zf.read(name))
        else:
            with open(local_file_path, "wb") as f:
                f.write(decoded)
    except Exception as e:
        raise RuntimeError(f"Error saving file: {e}")

def delete_all_files_from_grid(grid_url, session_id):
    try:
        endpoint = f"{grid_url}/session/{session_id}/se/files"
        response = requests.delete(endpoint)
        response.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Error deleting files from grid: {e}")

def list_files(grid_url, session_id):
    try:
        endpoint = f"{grid_url}/session/{session_id}/se/files"
        response = requests.get(endpoint)
        response.raise_for_status()
        return response.json()["value"]["names"]
    except Exception as e:
        raise RuntimeError(f"Error listing files from grid: {e}")

def fetch_file_from_grid(grid_url, session_id, file_name, local_file_path):
    try:
        endpoint = f"{grid_url}/session/{session_id}/se/files"
        payload = {"name": file_name}
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()
        file_data = response.json()["value"]["contents"]
        save_file(file_data, local_file_path) # We need to unzip the file first if it's a zip file
    except Exception as e:
        raise RuntimeError(f"Error fetching file from grid: {e}")

def get_downloaded_files(webdriver, destination_dir=None):
    try:
        session_id = webdriver.session_id
        file_names = list_files(SELENIUM_GRID_URL, session_id)
        #print("Downloaded files:", file_names)
        logger.info(f"Downloaded files: {file_names}")
        if file_names:
            for file_name in file_names:
                local_file = os.path.join(destination_dir, file_name) if destination_dir else file_name
                fetch_file_from_grid(SELENIUM_GRID_URL, session_id, file_name, local_file)
            # Delete all files after fetching  
            delete_all_files_from_grid(SELENIUM_GRID_URL, session_id)
    except Exception as e:
        logger.error(f"Error fetching downloaded files: {e}")

# Test the helper for downloading files from Selenium Grid
# if __name__ == "__main__":
#     from selenium import webdriver
#     from selenium.webdriver.chrome.options import Options
#     import time
#     proxy = "http://appproxy:80"
#     chrome_options = Options()
#     chrome_options.add_experimental_option("prefs", {
#         "download.prompt_for_download": False,
#         "plugins.always_open_pdf_externally": True  # <-- This should download PDFs instead of opening them
#     })
# 
#     chrome_options.add_argument("--disable-extensions")
#     chrome_options.add_argument('--ignore-certificate-errors')
#     chrome_options.add_argument('--ignore-ssl-errors')
#     chrome_options.add_argument('--allow-running-insecure-content')
# 
#     chrome_options.add_argument("--disable-gpu")  # Disable GPU acceleration
#     chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
#     chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
#     chrome_options.add_argument("--remote-debugging-port=9222")  # Enable remote debugging
# 
#     #chrome_options.add_argument("--headless")  # Optional
#     chrome_options.add_argument(f"--proxy-server={proxy}")
#     chrome_options.set_capability("se:downloadsEnabled", True)
# 
#     driver = webdriver.Remote(
#         command_executor=SELENIUM_GRID_URL,
#         options=chrome_options
#     )
# 
#     try:
#         destination_url = fr"C:\Colt\Dev\selenium_download"
# 
#         # Example file to download (replace with your actual attachment URL)
#         file_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
#         driver.get(file_url)
#         time.sleep(5)  # Wait for download
#         get_downloaded_files(driver, destination_url)
# 
#         file_url = "https://github.com/github/gitignore/archive/refs/heads/main.zip"
#         driver.get(file_url)
#         time.sleep(5)  # Wait for download
# 
#         destination_url = fr"C:\Colt\Dev\selenium_download"
#         get_downloaded_files(driver, destination_url)
# 
#     finally:
#         driver.quit()


# # Test the uploading - helper is not needed, we only need to have 'driver.file_detector = LocalFileDetector()' set for the driver
# if __name__ == "__main__":
#     from selenium import webdriver
#     from selenium.webdriver.chrome.options import Options
#     import time
#     proxy = "http://appproxy:80"
#     chrome_options = Options()
#     chrome_options.add_experimental_option("prefs", {
#         "download.prompt_for_download": False,
#         "plugins.always_open_pdf_externally": True  # <-- This should download PDFs instead of opening them
#     })
# 
#     chrome_options.add_argument("--disable-extensions")
#     chrome_options.add_argument('--ignore-certificate-errors')
#     chrome_options.add_argument('--ignore-ssl-errors')
#     chrome_options.add_argument('--allow-running-insecure-content')
# 
#     chrome_options.add_argument("--disable-gpu")  # Disable GPU acceleration
#     chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
#     chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
#     chrome_options.add_argument("--remote-debugging-port=9222")  # Enable remote debugging
# 
#     #chrome_options.add_argument("--headless")  # Optional
#     chrome_options.add_argument(f"--proxy-server={proxy}")
#     chrome_options.set_capability("se:downloadsEnabled", True)
# 
#     driver = webdriver.Remote(
#         command_executor=SELENIUM_GRID_URL,
#         options=chrome_options
#     )
#     #driver.file_detector = LocalFileDetector()
# 
#     try:
#         local_file_path = r"C:\Colt\Dev\selenium_download\dummy.pdf"  # Your test file
#         
#         # driver.get("https://www.w3schools.com/howto/howto_html_file_upload_button.asp")
#         # time.sleep(2)
#         # file_input = driver.find_element(By.ID, "myFile")
#         # file_input.send_keys(local_file_path)
#         # time.sleep(2)
# 
#         # Navigate to the webpage with the file upload form
#         driver.get("https://the-internet.herokuapp.com/upload")  # Example upload page
#         time.sleep(2)
#         
#         # Locate the file input element
#         file_input = driver.find_element(By.ID, "file-upload")  # Adjust ID based on your
#         time.sleep(2)
#         
#         # Send the remote file path to the file input
#         file_input.send_keys(local_file_path)
# 
#         # Submit the form (if needed)
#         driver.find_element(By.ID, "file-submit").click()
#         
#     finally:
#         driver.quit()