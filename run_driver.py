import logging
import subprocess
import tempfile # For TemporaryDirectory
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Ensure logging is configured as shown in Section 2.5
module_logger = logging.getLogger("app.chromedriver_setup_robust")

def setup_chromedriver_robust():
    module_logger.info("Initiating ROBUST Chromedriver setup.")
    # Path to Chromedriver: Assumed to be in PATH if managed by Nix.
    # Otherwise, specify the full path: e.g., '/nix/store/.../bin/chromedriver'
    chromedriver_executable = "chromedriver"

    # Temporary directory for user data (optional, but good for isolation if needed)
    # Using TemporaryDirectory ensures it's cleaned up automatically.
    # If a persistent profile is NOT needed, it's often best to OMIT --user-data-dir
    # and let ChromeDriver manage its own temporary profile.
    temp_user_data_dir_manager = None
    user_data_dir_path = None

    try:
        options = Options()
        module_logger.debug("ChromeOptions instantiated.")

        # Essential arguments
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions") # Good practice for automation

        # Verbose logging from Chrome browser itself
        options.add_argument("--enable-logging=stderr")
        options.add_argument("--v=1") # Verbosity level for Chrome's logs

        # --- Optional: Custom User Data Directory ---
        # If you absolutely need a custom user data dir, manage it with TemporaryDirectory
        # create_custom_user_data_dir = False # Set to True to enable
        # if create_custom_user_data_dir:
        #     try:
        #         # Create in /tmp, assuming /tmp is writable by seluser
        #         temp_user_data_dir_manager = tempfile.TemporaryDirectory(prefix="chrome_user_data_", dir="/tmp")
        #         user_data_dir_path = temp_user_data_dir_manager.name
        #         options.add_argument(f"--user-data-dir={user_data_dir_path}")
        #         module_logger.info(f"Using temporary user data directory: {user_data_dir_path}")
        #     except Exception as tmp_err:
        #         module_logger.error(f"Failed to create temporary user data directory: {tmp_err}", exc_info=True)
        #         # Proceed without custom user_data_dir or raise, depending on requirements
        # else:
        # module_logger.info("Not using a custom --user-data-dir; ChromeDriver will use its default temporary profile.")
        module_logger.info("Omitting --user-data-dir; ChromeDriver will use its default temporary profile.")


        # Enable browser log retrieval
        options.set_capability("goog:loggingPrefs", {
            "browser": "ALL", "driver": "ALL", "performance": "ALL"
        })
        module_logger.debug(f"ChromeOptions arguments: {options.arguments}")
        module_logger.debug(f"ChromeOptions capabilities: {options.capabilities}")

        service_args =
        service = Service(
            executable_path=chromedriver_executable,
            service_args=service_args,
            log_output=subprocess.STDOUT # Direct ChromeDriver's logs to stdout
        )
        module_logger.info(f"ChromeDriver service configured with args: {service_args} and log_output to STDOUT.")

        module_logger.info("Attempting to instantiate webdriver.Chrome.")
        driver = webdriver.Chrome(service=service, options=options)
        module_logger.info(f"webdriver.Chrome instantiated successfully. Session ID: {driver.session_id}")

        try:
            browser_logs = driver.get_log("browser")
            if browser_logs:
                module_logger.info("--- Initial Browser Console Logs (via driver.get_log) ---")
                for entry in browser_logs:
                    module_logger.info(f"  LEVEL: {entry.get('level')} - MSG: {entry.get('message')}")
                module_logger.info("--- End of Initial Browser Console Logs ---")
            else:
                module_logger.info("No initial browser console logs found via driver.get_log('browser').")
        except Exception as log_exc:
            module_logger.warning(f"Could not retrieve browser logs immediately after start: {log_exc}", exc_info=True)

        # To keep the temporary directory alive if created, the 'temp_user_data_dir_manager'
        # would need to be returned or its lifecycle managed by a class holding the driver.
        # For this example, if it were created, it would be cleaned up when this function exits.
        # This is why omitting --user-data-dir is often simpler if persistence isn't key.
        return driver

    except Exception as e:
        module_logger.error(f"CRITICAL ERROR during Chromedriver setup: {e}", exc_info=True)
        # If user_data_dir_path was created and an error occurs, it will be cleaned up
        # by TemporaryDirectory's __exit__ method if temp_user_data_dir_manager goes out of scope.
        raise
    finally:
        # Explicitly clean up if TemporaryDirectory object was created and needs manual handling
        # (though context manager behavior is usually sufficient).
        # if temp_user_data_dir_manager:
        #     try:
        #         temp_user_data_dir_manager.cleanup()
        #         module_logger.info(f"Cleaned up temporary user data directory: {user_data_dir_path}")
        #     except Exception as cleanup_err:
        #         module_logger.warning(f"Error cleaning up temporary user data directory {user_data_dir_path}: {cleanup_err}")
        pass