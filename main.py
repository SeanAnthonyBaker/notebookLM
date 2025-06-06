import tempfile
from fastapi.responses import JSONResponse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from fastapi import FastAPI, HTTPException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import shutil # Import shutil for directory removal
import time
import os # Import os for path manipulation
import logging # Added for robust logging
import subprocess # Added for robust logging

# --- Configure Logging ---
# Configure root logger for basic output.
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(threadName)s - %(message)s',
    handlers=[logging.StreamHandler()]) # Added a StreamHandler here

# Specific logger for this application
module_logger = logging.getLogger("app.main")
module_logger.setLevel(logging.DEBUG)

# Configure Selenium's own loggers for more detail
selenium_connection_logger = logging.getLogger('selenium.webdriver.remote.remote_connection')
selenium_connection_logger.setLevel(logging.INFO) # Use DEBUG for very verbose wire logs
selenium_client_logger = logging.getLogger('selenium.webdriver.common')
selenium_client_logger.setLevel(logging.DEBUG)


# --- Global Variables ---
driver: webdriver.Chrome | None = None
# Store the user_data_dir created for the current driver session
current_user_data_dir: str | None = None
# temp_user_data_dir_manager is not used globally in this version
# as current_user_data_dir is managed directly.

app = FastAPI()

@app.post("/test")
async def root():
    return {"message": "Hello from your FastAPI app!"}

@app.get("/driver/setup")
async def setup_driver(notebook_id: str):
    global driver, current_user_data_dir
    if driver:
        raise HTTPException(status_code=400, detail="Driver already initialized. Call /driver/close first if you want to re-initialize.")
    
    module_logger.info("Setting up new driver instance (headless mode)...")

    # Use a dedicated directory for user data within the working directory
    user_data_dir_path = "/app/chrome_user_data"
    module_logger.info(f"Ensuring {user_data_dir_path} is clean for new driver session...")
    if os.path.exists(user_data_dir_path):
        module_logger.info(f"Removing existing user data directory: {user_data_dir_path}")
        shutil.rmtree(user_data_dir_path, ignore_errors=True)
    os.makedirs(user_data_dir_path, exist_ok=True) # Create the directory if it doesn't exist

    # Ensure this is created fresh for each session
    try:
        new_user_data_dir = tempfile.mkdtemp(prefix="selenium_profile_", dir="/tmp") # Explicitly use /tmp
        module_logger.info(f"Created temporary user data directory: {new_user_data_dir}")
        current_user_data_dir = new_user_data_dir # Store it globally
    except Exception as tmp_err:
        module_logger.error(f"Failed to create temporary user data directory in /tmp: {tmp_err}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Driver setup failed: Could not create temp user data dir - {str(tmp_err)}")

    options = Options()
    module_logger.debug("ChromeOptions instantiated.")

    # Essential arguments for Docker/headless operation
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")

    # Arguments for enabling Chrome's own verbose logging
    options.add_argument("--enable-logging=stderr")
    options.add_argument("--v=1") # Chrome's own verbosity level

    # User's existing experimental options
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('--disable-blink-features=AutomationControlled')
    
    # Pass the temporary user data directory to Chrome
    options.add_argument(f"--user-data-dir={current_user_data_dir}")
    
    # Capability to enable browser console log retrieval via Selenium client
    options.set_capability("goog:loggingPrefs", {
        "browser": "ALL",
        "driver": "ALL",
        "performance": "ALL"
    })
    module_logger.debug(f"ChromeOptions arguments configured: {options.arguments}")
    module_logger.debug(f"ChromeOptions capabilities configured: {options.capabilities}")

    # --- ChromeDriver Service ---
    chromedriver_executable = "/opt/selenium/chromedriver-136.0.7103.113" # Assumes chromedriver is in PATH
    service_args = [] # No specific extra service args needed for now
    
    service = Service(
        executable_path=chromedriver_executable,
        service_args=service_args,
        log_output=subprocess.STDOUT # Directs ChromeDriver's own logs to stdout
    )
    module_logger.info(f"ChromeDriver service configured with executable: {chromedriver_executable}, args: {service_args}, and log_output to STDOUT.")

    try:
        module_logger.info("Attempting to instantiate webdriver.Chrome with configured service and options.")
        driver = webdriver.Chrome(service=service, options=options)
        module_logger.info(f"webdriver.Chrome instantiated successfully. Driver session ID: {driver.session_id}")
        
        driver.set_page_load_timeout(200)
        
        module_logger.info(f"Navigating to: {notebook_id}")
        driver.get(notebook_id)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        module_logger.info("Page body loaded.")

        # Retrieve and Log Initial Browser Console Logs
        try:
            module_logger.debug("Attempting to retrieve initial browser console logs using driver.get_log('browser').")
            browser_logs = driver.get_log("browser")
            if browser_logs:
                module_logger.info("--- Initial Browser Console Logs ---")
                for entry in browser_logs:
                    module_logger.info(
                        f"  LEVEL: {entry.get('level', 'N/A')} - "
                        f"TIMESTAMP: {entry.get('timestamp', 'N/A')} - "
                        f"MESSAGE: {entry.get('message', 'N/A')}"
                    )
                module_logger.info("--- End of Initial Browser Console Logs ---")
            else:
                module_logger.info("No initial browser console logs were found via driver.get_log('browser').")
        except Exception as log_exc:
            module_logger.warning(f"Could not retrieve initial browser logs via driver.get_log('browser'): {log_exc}", exc_info=True)

        return JSONResponse({"message": "Driver setup successful and navigated to notebook."})
    
    except Exception as e:
        module_logger.error(f"Driver setup failed: {e}", exc_info=True)
        if driver:
            try:
                driver.quit()
            except Exception as quit_error:
                module_logger.error(f"Error during driver quit after setup failure: {quit_error}", exc_info=True)
            driver = None
        
        if current_user_data_dir and os.path.exists(current_user_data_dir):
            try:
                shutil.rmtree(current_user_data_dir)
                module_logger.info(f"Cleaned up temporary user data directory: {current_user_data_dir}")
            except OSError as dir_cleanup_error:
                module_logger.error(f"Error cleaning up user data directory {current_user_data_dir}: {dir_cleanup_error}", exc_info=True)
        current_user_data_dir = None # Reset global variable
        
        raise HTTPException(status_code=500, detail=f"Driver setup failed: {type(e).__name__} - {str(e)}")

@app.get("/execute/query")
async def execute_query(notebook_id: str, llmquery: str):
    global driver
    if not driver:
        raise HTTPException(status_code=400, detail="Driver not initialized. Please call /driver/setup first.")
        
    extracted_response_text = None # Initialize variable to hold the extracted text

    try:
        current_page_url = driver.current_url
        if notebook_id not in current_page_url:
            module_logger.info(f"Current URL is '{current_page_url}'. Navigating to: {notebook_id}")
            driver.get(notebook_id)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            module_logger.info(f"Successfully navigated to {notebook_id}.")
        else:
            module_logger.info(f"Already on a page related to notebook URL: {notebook_id} (Current: {current_page_url})")

        text_input_selector = (By.XPATH, "//input | //textarea")
        wait = WebDriverWait(driver, 30)
        module_logger.info(f"Attempting to find input field with placeholder 'Start typing...'")
        input_field = wait.until(EC.element_to_be_clickable(text_input_selector))
        module_logger.info(f"Input field found. Clearing and entering query: '{llmquery}'")
        input_field.clear()
        input_field.send_keys(llmquery)
        module_logger.info("Query entered into the text field successfully.")

        generic_copy_button_selector = (By.XPATH, "//button[contains(@aria-label, 'Copy')]")
        initial_copy_buttons = driver.find_elements(*generic_copy_button_selector)
        initial_count = len(initial_copy_buttons)
        module_logger.info(f"Initial 'Copy' button count: {initial_count}")

        submit_button_selector = (By.XPATH, "//button")
        module_logger.info(f"Attempting to find and click the submit button using selector: {submit_button_selector}")
        submit_button_element = wait.until(EC.element_to_be_clickable(submit_button_selector))
        submit_button_element.click()
        module_logger.info("Submit button clicked.")

        module_logger.info("Waiting for the number of 'Copy' buttons to increase (indicates new response)...")
        def _check_copy_button_increase(d):
            elements = d.find_elements(*generic_copy_button_selector)
            if len(elements) > initial_count:
                return elements
            return False

        all_generic_copy_buttons_after_increase = WebDriverWait(driver, 60, poll_frequency=1).until(
            _check_copy_button_increase,
            message=f"Timeout: Number of generic 'Copy' buttons did not increase from {initial_count} within 60 seconds. A new response might not have appeared."
        )

        current_generic_button_count = len(all_generic_copy_buttons_after_increase)
        module_logger.info(f"Number of generic 'Copy' buttons has increased from {initial_count} to: {current_generic_button_count}. New response detected.")

        action_message = f"Query submitted, new response detected. Generic copy button count changed from {initial_count} to {current_generic_button_count}."
        new_button_details = {}

        js_get_xpath = """
        function getElementXPath(elt) {
            let path = "";
            for (; elt && elt.nodeType === Node.ELEMENT_NODE; elt = elt.parentNode) {
                let idx = 0;
                let sibling = elt.previousSibling;
                while (sibling) {
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === elt.tagName) {
                        idx++;
                    }
                    sibling = sibling.previousSibling;
                }
                let nodeName = elt.tagName.toLowerCase();
                let hasNextSiblingWithSameTag = false;
                sibling = elt.nextSibling;
                while (sibling) {
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === elt.tagName) {
                        hasNextSiblingWithSameTag = true;
                        break;
                    }
                    sibling = sibling.nextSibling;
                }
                if (idx > 0 |
| (idx === 0 && hasNextSiblingWithSameTag)) {
                    nodeName += "[" + (idx + 1) + "]";
                }
                path = "/" + nodeName + path;
            }
            return path;
        }
        return getElementXPath(arguments);
        """

        if all_generic_copy_buttons_after_increase:
            new_button = all_generic_copy_buttons_after_increase[-1]
            module_logger.info("\n--- Processing the newly added 'Copy' button ---")

            try:
                button_aria_label = new_button.get_attribute('aria-label')
                button_text_content = new_button.text.strip()
                module_logger.info(f"  Name (Aria-Label): {button_aria_label if button_aria_label else 'N/A'}")
                if button_text_content:
                    module_logger.info(f"  Name (Inner Text): '{button_text_content}'")
                new_button_details['aria_label'] = button_aria_label
                new_button_details['text_content'] = button_text_content

                button_xpath = driver.execute_script(js_get_xpath, new_button)
                module_logger.info(f"  Generated XPath: {button_xpath if button_xpath else 'N/A'}")
                new_button_details['xpath'] = button_xpath
                
                module_logger.info(f"  Scrolling to make button '{button_aria_label if button_aria_label else 'newly added Copy button'}' visible...")
                driver.execute_script("arguments.scrollIntoView(false);", new_button)
                time.sleep(1) 

                module_logger.info("  Waiting for the new copy button to be clickable...")
                wait.until(EC.element_to_be_clickable(new_button))
                module_logger.info("  New copy button is now clickable.")

                is_displayed_after_scroll = new_button.is_displayed()
                is_clickable_after_scroll = True 

                module_logger.info(f"  Is Displayed (after scroll): {is_displayed_after_scroll}")
                module_logger.info(f"  Is Clickable (after scroll): {is_clickable_after_scroll}")

                new_button_details['is_displayed_after_scroll'] = is_displayed_after_scroll
                new_button_details['is_clickable_after_scroll'] = is_clickable_after_scroll
                
                try:
                    text_content_xpath_relative = "./ancestor::mat-card[1]/mat-card-content"
                    module_logger.info(f"  Attempting to extract text using relative XPath: {text_content_xpath_relative}")
                    response_text_element = new_button.find_element(By.XPATH, text_content_xpath_relative)
                    extracted_response_text = response_text_element.text.strip()
                    module_logger.info(f"  Extracted response text from DOM: '{extracted_response_text[:100]}...'")
                except Exception as text_extract_err:
                    module_logger.warning(f"  Warning: Could not extract response text directly from DOM using relative XPath: {text_extract_err}")
                    extracted_response_text = None

                if is_displayed_after_scroll and is_clickable_after_scroll:
                    module_logger.info("  Button is visible and clickable. Attempting to click...")
                    try:
                        new_button.click() 
                        module_logger.info("  New copy button clicked successfully (native click).")
                        action_message += " Newly added copy button details printed, scrolled into view, and clicked."
                    except webdriver.exceptions.ElementClickInterceptedException as click_err: # More specific exception
                        module_logger.warning(f"  Native click intercepted: {click_err.msg}. Attempting JavaScript click...")
                        driver.execute_script("arguments.click();", new_button)
                        module_logger.info("  New copy button clicked successfully (JavaScript click).")
                        action_message += " Newly added copy button details printed, scrolled into view, and clicked (via JS)."
                        new_button_details['error'] = f"ElementClickInterceptedException (resolved with JS click): {click_err.msg}"
                    except Exception as generic_click_error:
                        module_logger.error(f"  Error during click: {type(generic_click_error).__name__} - {generic_click_error}. Not clicked.", exc_info=True)
                        action_message += f" Newly added copy button details printed and scrolled into view, but click failed: {type(generic_click_error).__name__}."
                        new_button_details['error'] = f"Error during click: {type(generic_click_error).__name__} - {generic_click_error}"
                else:
                    module_logger.warning("  Warning: Button might not be fully visible or clickable after scroll attempt. Not clicking.")
                    action_message += " Newly added copy button details printed; scroll attempt made but not clicked due to visibility/clickability."

            except webdriver.exceptions.StaleElementReferenceException: # More specific exception
                stale_msg = "Error: The new copy button became stale before it could be processed or clicked."
                module_logger.error(f"  {stale_msg}", exc_info=True)
                action_message += f" {stale_msg}"
                new_button_details['error'] = stale_msg
            except Exception as e_attr:
                attr_err_msg = f"Error processing/clicking button: {type(e_attr).__name__} - {e_attr}"
                module_logger.error(f"  {attr_err_msg}", exc_info=True)
                action_message += f" {attr_err_msg}"
                new_button_details['error'] = attr_err_msg
            module_logger.info("--- End of new button details ---\n")
        else:
            action_message += " No new copy buttons found in the list to detail (this shouldn't happen if count increased)."

        return {
            "message": action_message,
            "initial_generic_copy_button_count": initial_count,
            "final_generic_copy_button_count": current_generic_button_count,
            "query_submitted": llmquery,
            "new_button_details": new_button_details,
            "extracted_response_text": extracted_response_text
        }

    except webdriver.exceptions.TimeoutException as te: # More specific exception
        error_message = f"Timeout occurred during query execution: {str(te)}"
        module_logger.error(error_message, exc_info=True)
        raise HTTPException(status_code=408, detail=error_message)
    except Exception as e:
        error_message = f"An error occurred during query execution: {type(e).__name__} - {str(e)}"
        module_logger.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)

@app.get("/driver/close")
async def close_driver():
    global driver, current_user_data_dir
    closed_driver = False
    if driver:
        module_logger.info("Closing WebDriver...")
        try:
            driver.quit()
            driver = None
            closed_driver = True
            module_logger.info("WebDriver closed successfully.")
        except Exception as e:
            module_logger.error(f"Error during driver.quit(): {e}", exc_info=True)
            driver = None # Ensure driver is set to None even if quit fails
    else:
        module_logger.info("Close driver requested, but WebDriver was not initialized or already closed.")
    
    if current_user_data_dir and os.path.exists(current_user_data_dir):
        try:
            shutil.rmtree(current_user_data_dir)
            module_logger.info(f"Cleaned up temporary user data directory: {current_user_data_dir}")
        except OSError as e:
            module_logger.error(f"Error cleaning up user data directory {current_user_data_dir}: {e}", exc_info=True)
    current_user_data_dir = None # Reset global variable

    if closed_driver:
        return JSONResponse({"message": "Driver closed."})
    else:
        return JSONResponse({"message": "Driver was not initialized or already closed."})

if __name__ == "__main__":
    import uvicorn
    # Basic logging config for uvicorn if not already handled by a richer config
    uvicorn_log_config = uvicorn.config.LOGGING_CONFIG
    uvicorn_log_config["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    uvicorn_log_config["formatters"]["access"]["fmt"] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
    
    module_logger.info("Starting FastAPI application with Uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_config=uvicorn_log_config)