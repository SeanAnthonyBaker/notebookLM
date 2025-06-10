#!/bin/bash

# Check if a container ID is provided
if [ -z "$1" ]; then

# Clean up Docker environment
echo "Cleaning up Docker environment..."
docker system prune -f
  echo "Error: Please provide the container ID as a parameter."
  exit 1
fi

CONTAINER_ID="$1"
IMAGE_NAME="my-fastapi-app"
CONTAINER_NAME="my-running-app"
HOST_PORT="8000"
CONTAINER_PORT="$HOST_PORT" # Assuming container port is the same as host port

# Stop the container if it's running (ignore errors if it's not running)
echo "Attempting to stop container $CONTAINER_ID..."
docker stop "$CONTAINER_ID" 2>/dev/null
# Remove the container (ignore errors if it doesn't exist)
echo "Attempting to remove container $CONTAINER_ID..."
docker rm "$CONTAINER_ID" 2>/dev/null
# Remove the container with the fixed name (ignore errors if it doesn't exist)
echo "Attempting to remove container $CONTAINER_NAME..."
docker rm "$CONTAINER_NAME" 2>/dev/null
# Build the new image
echo "Building Docker image $IMAGE_NAME..."
# Aggressively clean up all unused Docker objects, including volumes and build cache
echo "Performing aggressive Docker system prune..."
docker system prune -a -f --volumes
# Explicitly remove the image to force a fresh build
echo "Removing existing image $IMAGE_NAME..."
docker rmi -f "$IMAGE_NAME" 2>/dev/null
docker build --no-cache -t "$IMAGE_NAME" .

# Run a new container
echo "Running new container $CONTAINER_NAME from image $IMAGE_NAME..."
docker run -d -p "$HOST_PORT":"$CONTAINER_PORT" --name "$CONTAINER_NAME" "$IMAGE_NAME"
echo "Done."