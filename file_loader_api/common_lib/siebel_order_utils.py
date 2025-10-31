# Internal libraries
from RPA_MODULES.common_lib.logging_config import get_logger
from common_lib.siebel_rpa_lib import *

# External libraries
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException


# Set up logger for logging events and errors
logger = get_logger("siebel_order_utils.py")

# @Sumit : 21-July-2025 : updated the create_service_order_diary function to behave as generic utility
def create_service_order_diary(tmp_driver, service_order_number, vars_dict):
    """
    Create diary entries for a service order in Siebel.
    """
    try:
        # Navigate to Service Order List View
        goto_siebel_view(tmp_driver, 'COLT Service Order List View')
        # Search for the specific service order record
        locate_and_search_siebel_record(tmp_driver, f'[COLT Service Order Num]="{service_order_number}')
        # Open the service order details
        click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Service Order Reference']/a")
        # Switch to the Service Order Diary View
        goto_siebel_view(tmp_driver, 'COLT Service Order Diary View')

        # Step 1: Click the New button to create a diary entry
        click_or_interact_with_element(tmp_driver, "//div[contains(@class,siebui-applet-active)]//*[@aria-label='Diary List Applet:New']")
        # Iterate through the dictionary and update diary fields
        for key, value in vars_dict.items():
            if not value:
                continue
            try:
                # Update the diary field with the provided value
                click_or_interact_with_element(tmp_driver, selector=key, action='update', value=value)
                logger.info(f"Diary entry created for key '{key}' with value '{value}'.")
            except Exception as e:
                logger.error(f"Failed to process '{key}' in diary creation: {e}")
                continue

        # Save the diary record
        save_siebel_record(tmp_driver)
        logger.info(f"Service order diary created for order number: {service_order_number}")
    except Exception as err:
        logger.error(f"Error occurred in create_service_order_diary: {str(err)}")

def update_service_order(tmp_driver, service_order_number, vars_dict):
    """
    Update fields for a service order in Siebel.
    """
    try:
        #Rajesh: 20-July-2025 : added service order number to the log
        # Navigate to Service Order List View if it is not already active. so you need not query the data again
        active_view = tmp_driver.execute_script("SiebelApp.S_App.GetActiveView().GetName()")
        #if active_view != 'COLT Service Order List View' then 
        if active_view != 'COLT Service Order List View':
            goto_siebel_view(tmp_driver, 'COLT Service Order List View')
            locate_and_search_siebel_record(tmp_driver, f'[COLT Service Order Num]="{service_order_number}')
        #click on the service order hyperlink and navigate to service order detail view
        click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Service Order Reference']/a")
        #click on the CRD backdated reason to focus the dates applet in siebel screen.just a random pick thats it.
        click_or_interact_with_element(tmp_driver, "//*[@aria-label='Project Id']",action='click')
        # Iterate through the dictionary and update fields
        for key, value in vars_dict.items():
            if not value:
                continue
            try:
                if key == "Order SubType":
                    # Rajesh: 20-July-2025 : if Order SubType is present then click on the pick icon and create new value then select the value
                    click_or_interact_with_element(tmp_driver, selector=key, action='update', value=value, new_rec="Y")
                else:
                    click_or_interact_with_element(tmp_driver, selector=key, action='update', value=value)
                logger.info(f"Updated '{key}' with value '{value}' for service order '{service_order_number}'.")
            except Exception as e:
                logger.error(f"Failed to update '{key}' for service order: {e}")
                continue

        save_siebel_record(tmp_driver)
        logger.info(f"Service order updated for order number: {service_order_number}")
    except Exception as err:
        logger.error(f"Error occurred in update_service_order: {str(err)}")

def create_customer_order(tmp_driver, vars_dict):
    """
    Create a new customer order in Siebel.
    """
    try:
        click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Name']/a")
        goto_siebel_view(tmp_driver, 'COLT OM SIS OM Customer Account Portal View')
        click_or_interact_with_element(tmp_driver, "//*[@aria-label='Installed Assets List Applet:New']")
        CUS_ORDER = tmp_driver.find_element(By.XPATH, '//*[contains(@aria-labelledby,"COLT_CustOrd_Customer_Order_No_Label")]').get_attribute('value')
        logger.info(f"Customer order created, order no.: {CUS_ORDER}")
    except Exception as err:
        logger.error(f"Error occurred in create_customer_order: {str(err)}")

def update_customer_order(tmp_driver, cust_order_num, vars_dict):
    """
    Update fields for a customer order in Siebel.
    """
    try:
        active_view = tmp_driver.execute_script("SiebelApp.S_App.GetActiveView().GetName()")
        if active_view != 'Order Entry - Line Items Detail View (Sales)':
            goto_siebel_view(tmp_driver, 'Order Entry - All Orders View (Sales)')
            locate_and_search_siebel_record(tmp_driver, f"[Order Number]='{cust_order_num}'")
            click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Siebel Order #']/a")

        for key, value in vars_dict.items():
            if not value:
                continue
            try:
                if key == "Contract":
                    contract_ele = click_or_interact_with_element(tmp_driver, "Contract", action="getelement")
                    pick_icon = contract_ele.find_element(By.XPATH, "./following-sibling::span[contains(@class, 'siebui-icon-pick')]")
                    pick_icon.click()
                    click_or_interact_with_element(tmp_driver, "//div[contains(@class,'siebui-popup-btm')]//button[contains(@class,'siebui-icon-pickrecord')]", action="click", err_handle="Y")
                else:
                    click_or_interact_with_element(tmp_driver, selector=key, action='update', value=value)
                logger.info(f"Updated '{key}' with value '{value}' for customer order '{cust_order_num}'.")
            except Exception as e:
                logger.error(f"Failed to update '{key}' for customer order: {e}")
                continue

        save_siebel_record(tmp_driver)
        logger.info(f"Customer order updated for order number: {cust_order_num}")
    except Exception as err:
        logger.error(f"Error occurred in update_customer_order: {str(err)}")

def create_service_order(tmp_driver, cust_order_num, vars_dict):
    """
    Create a new service order for a given customer order in Siebel.
    """
    try:
        target_product = vars_dict.get('Product Name', '')
        active_view = tmp_driver.execute_script("SiebelApp.S_App.GetActiveView().GetName()")
        if active_view != 'Order Entry - Line Items Detail View (Sales)':
            goto_siebel_view(tmp_driver, 'Order Entry - All Orders View (Sales)')
            locate_and_search_siebel_record(tmp_driver, f"[Order Number]='{cust_order_num}'")
            click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Siebel Order #']/a")
        click_or_interact_with_element(tmp_driver, "//*[contains(@aria-label,'New Service Order')]")

        item_clicked = False
        main_div_xpath = "//div[contains(@class, 'siebui-tile-container') and contains(@class, 'siebui-catalog-grid-layout')]"
        li_elements_xpath = main_div_xpath + "//ul/li"
        next_page_xpath = "//a[@href='#' and contains(@class, 'nextrecordset')]"

        while True:
            wait_for_element(tmp_driver, By.XPATH, main_div_xpath, explicit_wait_time=5, rpa2=True)
            main_div = tmp_driver.find_element(By.XPATH, main_div_xpath)
            if not main_div:
                logger.error("Main catalog container not found.")
                return False

            wait_for_element(tmp_driver, By.XPATH, li_elements_xpath, explicit_wait_time=5, rpa2=True)
            li_elements = tmp_driver.find_elements(By.XPATH, li_elements_xpath)
            if not li_elements:
                logger.warning("No product line items found.")
                return False

            for li in li_elements:
                try:
                    product_name_element = li.find_element(By.CLASS_NAME, "product-name")
                    product_name = product_name_element.text.strip()
                    if product_name == target_product:
                        add_button = li.find_element(By.CLASS_NAME, "add-product")
                        add_button.click()
                        logger.info(f"Clicked on product: {product_name}")
                        item_clicked = True
                        break
                except StaleElementReferenceException:
                    logger.warning("Stale element detected, retrying...")
                    time.sleep(1)
                    continue

            if item_clicked:
                break

            try:
                click_or_interact_with_element(tmp_driver, next_page_xpath)
                logger.info("Clicked next page button, searching again...")
            except NoSuchElementException:
                logger.warning("Next page button not found. Ending search.")
                break

        service_order_ele = click_or_interact_with_element(tmp_driver, "Service Order Reference", action="getelement")
        service_order_value = service_order_ele.get_attribute("title").strip()
        logger.info(f"Service order created with reference: {service_order_value}")

        return item_clicked
    except Exception as e:
        logger.error(f"Error occurred in create_service_order: {str(e)}")

def update_service_order_dates(tmp_driver, service_order_number, vars_dict):
    """
    Update date fields for a service order in Siebel.
    """
    try:
        # Navigate to Service Order List View if it is not already active. so you need not query the data again
        active_view = tmp_driver.execute_script("SiebelApp.S_App.GetActiveView().GetName()")
        #if active_view != 'COLT Service Order List View' then 
        if active_view != 'COLT Service Order List View':
            goto_siebel_view(tmp_driver, 'COLT Service Order List View')
            locate_and_search_siebel_record(tmp_driver, f'[COLT Service Order Num]="{service_order_number}')
        #click on the service order hyperlink and navigate to service order detail view
        click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Service Order Reference']/a")
        goto_siebel_view(tmp_driver, 'COLT Service Order Dates View')
        #click on the CRD backdated reason to focus the dates applet in siebel screen.just a random pick thats it.
        click_or_interact_with_element(tmp_driver, "//*[@aria-label='CRD Backdated Reason']",action='click')
        for key, value in vars_dict.items():
            if not value:
                continue
            try:
                click_or_interact_with_element(tmp_driver, selector=key, action='update', value=value)
                logger.info(f"Updated date field '{key}' with value '{value}' for service order '{service_order_number}'.")
            except Exception as e:
                logger.error(f"Failed to update date field '{key}' for service order: {e}")
                continue

        save_siebel_record(tmp_driver)
        logger.info(f"Service order dates updated for order number: {service_order_number}")
    except Exception as err:
        logger.error(f"Error occurred in update_service_order_dates: {str(err)}")

def update_service_order_billing(tmp_driver, service_order_number, vars_dict):
    """
    Update billing fields for a service order in Siebel.
    """
    try:
        goto_siebel_view(tmp_driver, 'COLT Service Order List View')
        locate_and_search_siebel_record(tmp_driver, f'[COLT Service Order Num]="{service_order_number}')
        click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Service Order Reference']/a")
        goto_siebel_view(tmp_driver, 'COLT Service Billing Profile View')

        for key, value in vars_dict.items():
            if not value:
                continue
            try:
                if key in ("Installation Charge", "Recurring Charge"):
                    UpdateBillingValue(tmp_driver, field_1=key, field_2="Amount", val=value)
                elif key == "BCN #":
                    UpdateBillingValue(tmp_driver, field_1="Installation Charge", field_2=key, val=value)
                    UpdateBillingValue(tmp_driver, field_1="Recurring Charge", field_2=key, val=value)
                else:
                    click_or_interact_with_element(tmp_driver, selector=key, action='update', value=value)
                logger.info(f"Updated billing field '{key}' with value '{value}' for service order '{service_order_number}'.")
            except Exception as e:
                logger.error(f"Failed to update billing field '{key}' for service order: {e}")
                continue

        save_siebel_record(tmp_driver)
        logger.info(f"Service order billing updated for order number: {service_order_number}")
    except Exception as err:
        logger.error(f"Error occurred in update_service_order_billing: {str(err)}")

def UpdateBillingValue(tmp_driver, field_1, field_2, val):
    """
    Update billing value for a specific charge and field in Siebel.
    """
    try:
        click_or_interact_with_element(tmp_driver, '//button[@aria-label="Service Charges List Applet:Expand All"]')
        item_clicked = False
        while True:
            max_rows = tmp_driver.find_elements("xpath", '//table[@summary="Service Charges"]/tbody/tr')
            for i in range(1, len(max_rows) + 1):
                row_xpath = f'//table[@summary="Service Charges"]/tbody/tr[{i}]/td'
                cells = tmp_driver.find_elements("xpath", row_xpath)
                found_charge = False
                target_cell = None

                for cell in cells:
                    role_desc = (cell.get_attribute("aria-roledescription") or "").strip().lower()
                    cell_text = cell.text.strip().lower()
                    if role_desc == "charge" and cell_text == f"{field_1}".lower():
                        found_charge = True
                    elif role_desc == f"{field_2}".lower():
                        target_cell = cell

                if found_charge and target_cell:
                    logger.info(f"Match found for charge '{field_1}' and field '{field_2}' in row {i}.")
                    tmp_driver.execute_script("arguments[0].scrollIntoView(true);", target_cell)
                    target_cell.click()
                    item_clicked = True
                    target_cell_input = target_cell.find_element("tag name", "input")
                    target_cell_input.clear()
                    target_cell_input.send_keys(val)
                    target_cell_input.send_keys(Keys.TAB)
                    break
            next_pager = tmp_driver.find_element("xpath",
                "//*[@title='Service Charges List Applet']/form/span/div//div[contains(@class,'siebui-applet-footer')]//td[contains(@id,'next_pager')]")
            if "ui-state-disabled" in next_pager.get_attribute("class").split() or item_clicked:
                break
            else:
                next_pager.click()
        logger.info(f"Billing value updated for charge '{field_1}' and field '{field_2}'.")
        return True
    except Exception as err:
        logger.error(f"Error occurred in UpdateBillingValue: {str(err)}")

def update_service_order_middle_applet_details(tmp_driver, service_order_number, vars_dict):
    """
    Update middle applet details for a service order in Siebel.
    """
    try:
        goto_siebel_view(tmp_driver, 'COLT Service Order List View')
        locate_and_search_siebel_record(tmp_driver, f'[COLT Service Order Num]="{service_order_number}')
        click_or_interact_with_element(tmp_driver, "//td[@aria-roledescription='Service Order Reference']/a")

        for key, value in vars_dict.items():
            if not value:
                continue
            try:
                # Construct dynamic XPath using the key (e.g., "Coverage")
                xpath = (
                    f"//div[@class='colt-save-level']//div[contains(@class, 'colt-attribute') and contains(@class, 'colt-attr-req')]"
                    f"//span[contains(., '{key}')]/following::input[1]"
                )
                click_or_interact_with_element(tmp_driver, selector=xpath, action='update', value=value, overridefind=True)
                logger.info(f"Updated middle applet detail '{key}' with value '{value}' for service order '{service_order_number}'.")
            except Exception as e:
                logger.error(f"Failed to update middle applet detail '{key}' for service order: {e}")
                continue

        save_siebel_record(tmp_driver)
        logger.info(f"Middle applet details updated for service order number: {service_order_number}")
    except Exception as err:
        logger.error(f"Error occurred in update_service_order_middle_applet_details: {str(err)}")