# Use a pre-built Selenium image with Chrome
FROM selenium/standalone-chrome:latest

# Ensure operations requiring root privileges are done as root
USER root

# Set the working directory in the container
WORKDIR /app

# Ensure the seluser has write permissions to the /app directory
RUN chown -R seluser:seluser /app

# Add commands for debugging and checking Chrome/Chromedriver
RUN google-chrome --version
RUN test -x /opt/google/chrome/google-chrome && echo "Chrome binary exists and is executable" || (echo "Chrome binary not found or not executable" && exit 1)

# --- Ensure /tmp has correct permissions and exists for tempfile.mkdtemp ---
# Perform these actions as root before switching to seluser
RUN chmod -R 777 /tmp && \
    mkdir -p /tmp/selenium_profiles /home/seluser/.config/google-chrome && \
    chown -R seluser:seluser /home/seluser/.config

# Create a virtual environment and install dependencies into it as root
RUN chown -R seluser:seluser /opt/venv
RUN python -m venv /opt/venv

# --- CRITICAL ADDITION: Cleanup on container start ---
# Create a startup script that cleans up and then runs your app
COPY start.sh /usr/local/bin/start.sh
# Make the startup script executable as root
RUN chmod +x /usr/local/bin/start.sh && \
 chown root:root /usr/local/bin/start.sh

# Switch to seluser for subsequent commands and running the app
USER seluser

# Copy the requirements file into the container
COPY requirements.txt requirements.txt

# Copy the main application file
COPY main.py .

# Install Python dependencies using the virtual environment
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Command to run the startup script, which then runs the FastAPI application
CMD /usr/local/bin/start.sh