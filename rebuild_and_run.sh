#!/bin/bash

# Clean up Docker environment
docker system prune -f

# Check if a container ID is provided
if [ -z "$1" ]; then
  echo "Error: Please provide the container ID as a parameter."
  exit 1
fi

CONTAINER_ID="$1"
IMAGE_NAME="my-fastapi-app"
CONTAINER_NAME="my-running-app"

# Stop the container if it's running
echo "Stopping container $CONTAINER_ID..."
docker stop "$CONTAINER_ID"

# Remove the container
echo "Removing container $CONTAINER_ID..."
docker rm "$CONTAINER_ID"

# Build the new image without using cache
echo "Building Docker image $IMAGE_NAME without cache..."
docker build --no-cache -t "$IMAGE_NAME" .

# Run a new container
echo "Running new container $CONTAINER_NAME from image $IMAGE_NAME..."
docker run -d -p 8000:8000 --name "$CONTAINER_NAME" "$IMAGE_NAME"

echo "Done."