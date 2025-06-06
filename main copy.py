import os
import time
import logging
import subprocess
import uuid
from typing import Generator, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, ElementClickInterceptedException


app = FastAPI()

# Configure logging for better visibility in Docker logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration for Docker Environment ---
# IMPORTANT: This path is inside the Docker container (Linux). A unique directory will be generated for each run.
# A fresh profile will be created here; it won't carry your desktop browser's login.
# You will likely hit the Google login page.
USER_DATA_DIR_DOCKER = "/tmp/user-data" 

# --- Selenium WebDriver Setup as a FastAPI Dependency ---
def get_chrome_driver_instance() -> Generator[webdriver.Chrome, None, None]:
    """
    Initializes a headless Chrome WebDriver for use within a Docker container.
    Yields the driver for the request and ensures it's quit afterwards.
    """
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless=new") # For newer Chrome headless mode
    chrome_options.add_argument("--no-sandbox") # Essential for Docker/Linux
    chrome_options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems in Docker
    chrome_options.add_argument("--disable-gpu") # Essential for headless
    chrome_options.add_argument("--window-size=1920,1080") # Set explicit window size
    
    # Enable verbose logging for ChromeDriver
    chrome_options.add_argument('--verbose')
    chrome_options.add_argument('--log-path=/tmp/chromedriver.log')
    
    # Options to avoid detection and reduce noise
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--disable-crash-reporter")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--v=0") # Suppress verbose logs
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--disable-blink-features=AutomationControlled') # Avoid detection as automated browser
    chrome_options.add_argument('--disable-site-isolation-trials')
    chrome_options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')

    # IMPORTANT: Specify the Chrome binary location for typical Linux/Colab/Docker installs
    chrome_binary_path = '/opt/google/chrome/google-chrome'
    chrome_options.binary_location = chrome_binary_path

    driver = None
    try:
        logging.info("Attempting to get ChromeDriver path using webdriver_manager...")
        driver_path = ChromeDriverManager().install()
        logging.info(f"ChromeDriver path: {driver_path}")

        # Manually construct the command to launch ChromeDriver with options
        # This allows us to capture stdout/stderr from the ChromeDriver process
        chrome_args = chrome_options.arguments
        command = [driver_path] + ["--port=0"] + chrome_args # --port=0 makes chromedriver pick a random available port

        logging.info(f"Launching ChromeDriver with command: {command}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Wait a moment for ChromeDriver to start and print its output
        time.sleep(2) 

        # Check if ChromeDriver started successfully and capture output
        stdout, stderr = process.communicate(timeout=10) # Add a timeout to avoid hanging
        logging.info(f"ChromeDriver stdout: {stdout.decode()}")
        logging.error(f"ChromeDriver stderr: {stderr.decode()}") # Log stderr as error

        # Now, connect Selenium to the running ChromeDriver instance (assuming it started)
        # This part is more complex and requires parsing the port from ChromeDriver's stdout
        # For simplicity, let's revert to using Service and let Selenium handle the process
        logging.warning("Manual ChromeDriver launch is complex. Reverting to Service for Selenium connection.")
        service = Service(driver_path, service_args=["--verbose", f"--log-path={chrome_options.arguments[-1].split('=')[-1]}"]) # Pass verbose and log-path to service
        driver = webdriver.Chrome(service=service, options=chrome_options) 
        driver.set_page_load_timeout(120) # Increased page load timeout
        logging.info("WebDriver initialized successfully.")
        yield driver # Yield the driver for the request
    except Exception as e:
        logging.error(f"Error during WebDriver setup: {e}", exc_info=True) # Log full traceback
        if driver:
            try:
                driver.quit()
            except Exception as quit_error:
                logging.error(f"Error during driver quit after setup failure: {quit_error}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize WebDriver: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logging.info("WebDriver quit successfully (from finally block).")
            except Exception as e:
                logging.error(f"Error quitting WebDriver in finally block: {e}")


# Dependency to provide the driver to routes
def get_selenium_driver_dependency() -> webdriver.Chrome:
    """
    Dependency resolver for FastAPI to get a Selenium WebDriver instance per request.
    """
    driver_generator = get_chrome_driver_instance()
    return next(driver_generator)


# --- FastAPI Routes ---
@app.get("/")
async def root():
    return {"message": "FastAPI service is running. Use /test, /driver/setup, /execute/query, or /driver/close."}

@app.get("/test")
async def test_endpoint():
 return JSONResponse(content={"message": "Test endpoint working!"})


@app.get("/scrape") # New simple scrape endpoint
async def scrape_website(url: str, driver: webdriver.Chrome = Depends(get_selenium_driver_dependency)):
    try:
        logging.info(f"Scraping: {url}")
        driver.get(url)
        title = driver.title
        return {"title": title}
    except Exception as e:
        logging.error(f"Error scraping {url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scraping failed: {e}")

@app.get("/driver/setup", dependencies=[Depends(get_selenium_driver_dependency)])
async def setup_driver(notebook_id: str, driver: webdriver.Chrome = Depends(get_selenium_driver_dependency)): # Driver dependency added
    """
    Sets up a new driver instance and navigates to the specified NotebookLM URL.
    The driver is automatically managed and closed per request by the dependency.
    """
    try:
        logging.info(f"Navigating to: {notebook_id}")
        driver.get(notebook_id)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        logging.info("Page body loaded.")
        return {"message": "Driver setup successful and navigated to notebook."}
    except Exception as e:
        logging.error(f"Driver setup failed for {notebook_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Driver setup failed: {str(e)}")

@app.get("/execute/query", dependencies=[Depends(get_selenium_driver_dependency)]) # Driver dependency added
async def execute_query(notebook_id: str, llmquery: str, driver: webdriver.Chrome = Depends(get_selenium_driver_dependency)): # Driver dependency added
    """
    Executes a query in NotebookLM and extracts the response.
    """
    extracted_response_text = None 

    try:
        current_page_url = driver.current_url
        if notebook_id not in current_page_url: # Simplified check
            logging.info(f"Current URL is '{current_page_url}'. Navigating to: {notebook_id}")
            driver.get(notebook_id)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            logging.info(f"Successfully navigated to {notebook_id}.")
        else:
            logging.info(f"Already on a page related to notebook URL: {notebook_id} (Current: {current_page_url})")

        # --- Locate input field ---
        # Adjusted selector to be more specific based on common NotebookLM elements
        text_input_selector = (By.XPATH, "//textarea[@aria-label='Ask a question about your sources']") # Use this specifically for NotebookLM
        wait = WebDriverWait(driver, 30) # Increased wait time for elements
        logging.info("Attempting to find input field...")
        input_field = wait.until(EC.element_to_be_clickable(text_input_selector))
        logging.info("Input field found. Clearing and entering query.")
        input_field.clear()
        input_field.send_keys(llmquery)
        logging.info("Query entered successfully.")

        # --- Locate and click submit button ---
        # Using the inspected XPATH:
        submit_button_selector = (By.XPATH, ".//textarea[@aria-label='Ask a question about your sources']/following-sibling::button")
        logging.info("Attempting to find and click the submit button...")
        submit_button_element = wait.until(EC.element_to_be_clickable(submit_button_selector))
        submit_button_element.click()
        logging.info("Submit button clicked.")
        
        # --- Wait for new response ---
        # Look for a common element indicating a new response, like a "Copy" button.
        # This is very fragile if NotebookLM's UI changes!
        # Initial copy button count is often not reliable due to dynamic loading,
        # better to wait for a *new* specific element to appear.
        
        # A more robust approach might be to wait for a specific text or the answer element itself to update.
        # For NotebookLM, look for an element that signifies the AI response is complete.
        # This selector needs to be *carefully* inspected on NotebookLM's actual page after a query.
        # It's highly likely to change.
        answer_element_selector = (By.CSS_SELECTOR, "div.response-container .response-text") # Example: Adjust this based on NotebookLM's HTML
        
        logging.info("Waiting for the AI response to appear...")
        answer_element = wait.until(EC.presence_of_element_located(answer_element_selector))
        extracted_response_text = answer_element.text.strip()
        logging.info(f"Extracted response text: '{extracted_response_text[:100]}...'") # Log first 100 chars


        return JSONResponse(content={"query": llmquery, "extracted_response": extracted_response_text})

    except TimeoutException as te:
        error_message = f"Timeout occurred during query execution: {str(te)}"
        logging.error(error_message, exc_info=True)
        raise HTTPException(status_code=408, detail=error_message)
    except Exception as e:
        error_message = f"An error occurred during query execution: {type(e).__name__} - {str(e)}"
        logging.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)


@app.get("/driver/close", dependencies=[Depends(get_selenium_driver_dependency)]) # Driver dependency added
async def close_driver_endpoint():
    """
    This endpoint is now largely informational. The driver is managed and closed automatically
    by the FastAPI dependency after each request completes.
    """
    logging.info("Close endpoint called. Driver is now managed automatically per request.")
    return JSONResponse(content={"message": "Driver lifecycle managed by FastAPI's dependency injection."})


if __name__ == "__main__":
    # This block is for local development; in Cloud Run/Docker, uvicorn will be started by the CMD in Dockerfile
    import uvicorn
    logging.info("Running Uvicorn locally (if __name__ == '__main__': block).")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False) # reload=False for stability
