# Use a pre-built Selenium image with Chrome
FROM selenium/standalone-chrome:latest

# Ensure operations requiring root privileges are done as root
USER root

# Set the working directory in the container
WORKDIR /app

# Ensure the seluser has write permissions to the /app directory
RUN chown -R seluser:seluser /app

# Add write permissions for the group and others to /app - Use with caution!
RUN chmod go+w /app
# Debugging: List files in /usr/local/bin and check permissions of start.sh
RUN ls -l /usr/local/bin/


# Add commands for debugging and checking Chrome/Chromedriver
RUN google-chrome --version
RUN test -x /opt/google/chrome/google-chrome && echo "Chrome binary exists and is executable" || (echo "Chrome binary not found or not executable" && exit 1)

# Copy and install compatible ChromeDriver from local directory
ENV CHROMEDRIVER_VERSION 137.0.7151.68
COPY ./chromedriver /opt/selenium/
RUN chmod +x /opt/selenium/chromedriver

# Copy the persistent Chrome user profile
COPY ./chrome-profile /home/seluser/chrome-profile
# Ensure seluser has ownership and permissions for the profile directory
RUN chown -R seluser:seluser /home/seluser/chrome-profile && chmod -R u+rwx /home/seluser/chrome-profile

# Fix sudo permissions for seluser
RUN chown root:root /usr/bin/sudo && \
    chmod u+s /usr/bin/sudo

# --- Ensure /tmp has correct permissions and exists for tempfile.mkdtemp ---
# Perform these actions as root before switching to seluser
# Note: We are no longer using a temporary profile, so /tmp permissions might be less critical here
RUN chmod -R 777 /tmp && mkdir -p /home/seluser/.config/google-chrome && chown -R seluser:seluser /home/seluser/.config

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