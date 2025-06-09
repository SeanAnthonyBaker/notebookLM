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

# --- Global Variables ---
driver: webdriver.Chrome | None = None
service_obj: Service | None = None
# Store the user_data_dir created for the current driver session
current_user_data_dir: str | None = None
CHROMEDRIVER_PATH = "chromedriver"
app = FastAPI()

@app.post("/test")
async def root():
    return {"message": "Hello from your FastAPI app!"}

@app.get("/driver/setup")
async def setup_driver(notebook_id: str):
    global driver, service_obj, current_user_data_dir
    if driver:
        raise HTTPException(status_code=400, detail="Driver already initialized. Call /driver/close first if you want to re-initialize.")

    # Create a temporary directory for user data
    try:
        temp_dir = tempfile.mkdtemp(prefix='chrome_user_data_')
        print(f"Created temporary user data directory: {temp_dir}")
        # Copy the contents of 'chrome-profile' into the temporary directory
        shutil.copytree('chrome-profile', temp_dir, dirs_exist_ok=True)
        print(f"Copied contents from 'chrome-profile' to '{temp_dir}'")
        current_user_data_dir = temp_dir # Store the temporary directory path
    except Exception as e:
        print(f"Failed to create or copy to temporary user data directory: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to set up user data directory: {e}")

    options = Options()
    # --- ADDED FOR HEADLESS MODE ---
    options.add_argument("--headless=new") # For the new headless mode (Chrome 109+)
    # options.add_argument("--headless") # Older headless mode, use if 'new' causes issues

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('--disable-blink-features=AutomationControlled')
    # Often good practice for headless: set a default window size as headless doesn't have one naturally
    options.add_argument("--window-size=1920,1080")
    # Disable GPU for headless environments as it might not be available
    options.add_argument("--disable-gpu")

    # Required for some environments when running headless
    options.add_argument("--disable-extensions")

    # --- CRITICAL FIX: Pass the temporary user data directory to Chrome ---
    options.add_argument(f"--user-data-dir={current_user_data_dir}")
    # Consider also adding a specific profile directory if needed, e.g.,
    # options.add_argument(f"--profile-directory=Default") # Often works with --user-data-dir

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(200)
        print(f"Navigating to: {notebook_id}")
        driver.get(notebook_id)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print("Page body loaded.")
        return {"message": "Driver setup successful and navigated to notebook."}
    except Exception as e:
        print(f"Driver setup failed: {e}")
        if driver:
            try:
                driver.quit()
            except Exception as quit_error:
                print(f"Error during driver quit after setup failure: {quit_error}")
            driver = None

        # --- CRITICAL FIX: Clean up the temporary user data directory on failure ---
        if current_user_data_dir and os.path.exists(current_user_data_dir):
            try:
                shutil.rmtree(current_user_data_dir)
                print(f"Cleaned up temporary user data directory: {current_user_data_dir}")
            except OSError as dir_cleanup_error:
                print(f"Error cleaning up user data directory {current_user_data_dir}: {dir_cleanup_error}")
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
            print(f"Current URL is '{current_page_url}'. Navigating to: {notebook_id}")
            driver.get(notebook_id)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            print(f"Successfully navigated to {notebook_id}.")
        else:
            print(f"Already on a page related to notebook URL: {notebook_id} (Current: {current_page_url})")

        text_input_selector = (By.XPATH, "//input[@placeholder='Start typing...'] | //textarea[@placeholder='Start typing...']")
        wait = WebDriverWait(driver, 30)
        print(f"Attempting to find input field with placeholder 'Start typing...'")
        input_field = wait.until(EC.element_to_be_clickable(text_input_selector))
        print(f"Input field found. Clearing and entering query: '{llmquery}'")
        input_field.clear()
        input_field.send_keys(llmquery)
        print("Query entered into the text field successfully.")

        generic_copy_button_selector = (By.XPATH, "//button[contains(@aria-label, 'Copy')]")
        initial_copy_buttons = driver.find_elements(*generic_copy_button_selector)
        initial_count = len(initial_copy_buttons)
        print(f"Initial 'Copy' button count: {initial_count}")

        submit_button_selector = (By.XPATH, "//button[@aria-label='Submit' or @type='submit' or @aria-label='Send' or contains(@class,'send-button-class')]")
        print(f"Attempting to find and click the submit button using selector: {submit_button_selector}")
        submit_button_element = wait.until(EC.element_to_be_clickable(submit_button_selector))
        submit_button_element.click()
        print("Submit button clicked.")

        print("Waiting for the number of 'Copy' buttons to increase (indicates new response)...")
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
        print(f"Number of generic 'Copy' buttons has increased from {initial_count} to: {current_generic_button_count}. New response detected.")

        action_message = f"Query submitted, new response detected. Generic copy button count changed from {initial_count} to {current_generic_button_count}."
        new_button_details = {}

        # JavaScript to get XPath (defined here as it will be used once for the final log)
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
                if (idx > 0 || (idx === 0 && hasNextSiblingWithSameTag)) {
                    nodeName += "[" + (idx + 1) + "]";
                }
                path = "/" + nodeName + path;
            }
            return path;
        }
        return getElementXPath(arguments[0]);
        """

        if all_generic_copy_buttons_after_increase:
            # The newly added button is typically the last one in the list
            new_button = all_generic_copy_buttons_after_increase[-1]
            print("\n--- Processing the newly added 'Copy' button ---")

            try:
                button_aria_label = new_button.get_attribute('aria-label')
                button_text_content = new_button.text.strip()
                print(f"  Name (Aria-Label): {button_aria_label if button_aria_label else 'N/A'}")
                if button_text_content:
                    print(f"  Name (Inner Text): '{button_text_content}'")
                new_button_details['aria_label'] = button_aria_label
                new_button_details['text_content'] = button_text_content

                button_xpath = driver.execute_script(js_get_xpath, new_button)
                print(f"  Generated XPath: {button_xpath if button_xpath else 'N/A'}")
                new_button_details['xpath'] = button_xpath

                # Scroll the new button into view, using 'false' to align to bottom
                print(f"  Scrolling to make button '{button_aria_label if button_aria_label else 'newly added Copy button'}' visible...")
                driver.execute_script("arguments[0].scrollIntoView(false);", new_button)
                time.sleep(1) # Small pause after scroll to allow rendering

                # Wait for the button to be clickable explicitly before attempting to click
                print("  Waiting for the new copy button to be clickable...")
                wait.until(EC.element_to_be_clickable(new_button))
                print("  New copy button is now clickable.")

                is_displayed_after_scroll = new_button.is_displayed()
                is_clickable_after_scroll = True # Confirmed by WebDriverWait

                print(f"  Is Displayed (after scroll): {is_displayed_after_scroll}")
                print(f"  Is Clickable (after scroll): {is_clickable_after_scroll}")
                new_button_details['is_displayed_after_scroll'] = is_displayed_after_scroll
                new_button_details['is_clickable_after_scroll'] = is_clickable_after_scroll

                # --- Attempt to extract the actual response text directly from the DOM ---
                try:
                    # Using a RELATIVE XPath from new_button to its ancestor mat-card, then to mat-card-content
                    # This is generally more robust than absolute XPaths for dynamic content.
                    text_content_xpath_relative = "./ancestor::mat-card[1]/mat-card-content"
                    print(f"  Attempting to extract text using relative XPath: {text_content_xpath_relative}")
                    # Wait for the text element to be present within the new_button's context
                    response_text_element = new_button.find_element(By.XPATH, text_content_xpath_relative)
                    extracted_response_text = response_text_element.text.strip()
                    print(f"  Extracted response text from DOM: '{extracted_response_text[:100]}...'") # Print first 100 chars
                except Exception as text_extract_err:
                    print(f"  Warning: Could not extract response text directly from DOM using relative XPath: {text_extract_err}")
                    extracted_response_text = None # Ensure it's None if extraction fails

                if is_displayed_after_scroll and is_clickable_after_scroll:
                    print("  Button is visible and clickable. Attempting to click...")
                    try:
                        new_button.click() # Attempt standard click first
                        print("  New copy button clicked successfully (native click).")
                        action_message += " Newly added copy button details printed, scrolled into view, and clicked."
                    except ElementClickInterceptedException as click_err:
                        print(f"  Native click intercepted: {click_err.msg}. Attempting JavaScript click...")
                        driver.execute_script("arguments[0].click();", new_button)
                        print("  New copy button clicked successfully (JavaScript click).")
                        action_message += " Newly added copy button details printed, scrolled into view, and clicked (via JS)."
                        new_button_details['error'] = f"ElementClickInterceptedException (resolved with JS click): {click_err.msg}"
                    except Exception as generic_click_error:
                        print(f"  Error during click: {type(generic_click_error).__name__} - {generic_click_error}. Not clicked.")
                        action_message += f" Newly added copy button details printed and scrolled into view, but click failed: {type(generic_click_error).__name__}."
                        new_button_details['error'] = f"Error during click: {type(generic_click_error).__name__} - {generic_click_error}"
                else:
                    print("  Warning: Button might not be fully visible or clickable after scroll attempt. Not clicking.")
                    action_message += " Newly added copy button details printed; scroll attempt made but not clicked due to visibility/clickability."

            except StaleElementReferenceException:
                stale_msg = "Error: The new copy button became stale before it could be processed or clicked."
                print(f"  {stale_msg}")
                action_message += f" {stale_msg}"
                new_button_details['error'] = stale_msg
            except Exception as e_attr:
                attr_err_msg = f"Error processing/clicking button: {type(e_attr).__name__} - {e_attr}"
                print(f"  {attr_err_msg}")
                action_message += f" {attr_err_msg}"
                new_button_details['error'] = attr_attr_msg
            print("--- End of new button details ---\n")
        else:
            action_message += " No new copy buttons found in the list to detail (this shouldn't happen if count increased)."

        # Return the extracted text along with other details
        return {
            "message": action_message,
            "initial_generic_copy_button_count": initial_count,
            "final_generic_copy_button_count": current_generic_button_count,
            "query_submitted": llmquery,
            "new_button_details": new_button_details,
            "extracted_response_text": extracted_response_text # This will now contain the scraped text
        }

    except TimeoutException as te:
        error_message = f"Timeout occurred during query execution: {str(te)}"
        print(error_message)
        raise HTTPException(status_code=408, detail=error_message)
    except Exception as e:
        error_message = f"An error occurred during query execution: {type(e).__name__} - {str(e)}"
        print(error_message)
        raise HTTPException(status_code=500, detail=error_message)

@app.get("/driver/close")
async def close_driver():
    global driver, service_obj, current_user_data_dir
    closed_driver = False
    closed_service = False # This variable is unused since service_obj isn't explicitly stopped
    if driver:
        print("Closing WebDriver...")
        try:
            driver.quit()
            driver = None
            closed_driver = True
            print("WebDriver closed successfully.")
        except Exception as e:
            print(f"Error during driver.quit(): {e}")
            driver = None # Ensure driver is set to None even if quit fails
    else:
        print("Close driver requested, but WebDriver was not initialized or already closed.")

    # --- CRITICAL FIX: Always clean up the temporary user data directory when driver is closed ---
    if current_user_data_dir and os.path.exists(current_user_data_dir):
        try:
            shutil.rmtree(current_user_data_dir)
            print(f"Cleaned up temporary user data directory: {current_user_data_dir}")
        except OSError as e:
            print(f"Error cleaning up user data directory {current_user_data_dir}: {e}")
    current_user_data_dir = None # Reset global variable

    if closed_driver: # Only check closed_driver, as service_obj isn't explicitly managed
        return {"message": "Driver closed."}
    else:
        return {"message": "Driver was not initialized or already closed."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)