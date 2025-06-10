# Use a pre-built Selenium image with Chrome
FROM selenium/standalone-chrome:latest

# Ensure operations requiring root privileges are done as root
USER root

# Explicitly create the /app directory
RUN mkdir /app

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
# Create the virtual environment directory and set ownership
RUN mkdir -p /opt/venv
RUN chown -R seluser:seluser /opt/venv
# Switch to root for permission modifications
USER root
# Create a virtual environment
RUN python -m venv /opt/venv

COPY requirements.txt /app/
RUN /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt


# Install Python dependencies using the virtual environment
# Change ownership of the installed packages to seluser
RUN chown -R seluser:seluser /opt/venv/lib/python*/site-packages
# --- CRITICAL ADDITION: Cleanup on container start ---
# Create a startup script that cleans up and then runs your app
COPY start.sh /usr/local/bin/start.sh

# Make the startup script executable as root
RUN chmod +x /usr/local/bin/start.sh && chown root:root /usr/local/bin/start.sh

# Switch back to seluser for running the application
USER seluser
# Copy the main application file
COPY requirements.txt .
COPY main.py .

# Command to run the startup script, which then runs the FastAPI application.
CMD ["/usr/local/bin/start.sh"]