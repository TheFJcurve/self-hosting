#!/bin/bash

# Nextcloud AIO Reset Script
# WARNING: This will DELETE ALL DATA associated with your AIO instance!

set -e  # Exit on error

echo "================================================"
echo "Nextcloud AIO Instance Reset Script"
echo "================================================"
echo ""
echo "WARNING: This will DELETE ALL DATA!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read -r

echo ""
echo "Step 1: Stopping all AIO containers..."
echo "----------------------------------------"

# Stop mastercontainer
if docker ps -a --format '{{.Names}}' | grep -q "nextcloud-aio-mastercontainer"; then
    echo "Stopping nextcloud-aio-mastercontainer..."
    docker stop nextcloud-aio-mastercontainer 2>/dev/null || true
fi

# Stop domaincheck container if running
if docker ps -a --format '{{.Names}}' | grep -q "nextcloud-aio-domaincheck"; then
    echo "Stopping nextcloud-aio-domaincheck..."
    docker stop nextcloud-aio-domaincheck 2>/dev/null || true
fi

# Stop any other AIO containers
echo "Checking for other running AIO containers..."
AIO_CONTAINERS=$(docker ps --format '{{.Names}}' | grep "nextcloud-aio" || true)
if [ -n "$AIO_CONTAINERS" ]; then
    echo "Found running AIO containers:"
    echo "$AIO_CONTAINERS"
    echo "Stopping them..."
    echo "$AIO_CONTAINERS" | xargs -r docker stop
else
    echo "No running AIO containers found."
fi

echo ""
echo "Step 2: Verifying no AIO containers are running..."
echo "----------------------------------------"
RUNNING=$(docker ps --format '{{.Names}}' | grep "nextcloud-aio" || true)
if [ -n "$RUNNING" ]; then
    echo "ERROR: Some AIO containers are still running:"
    echo "$RUNNING"
    echo "Please stop them manually and run this script again."
    exit 1
else
    echo "✓ No AIO containers running."
fi

echo ""
echo "Step 3: Checking stopped containers..."
echo "----------------------------------------"
docker ps --filter "status=exited"

echo ""
echo "Step 4: Removing stopped containers..."
echo "----------------------------------------"
docker container prune -f
echo "✓ Stopped containers removed."

echo ""
echo "Step 5: Removing docker network..."
echo "----------------------------------------"
if docker network ls | grep -q "nextcloud-aio"; then
    docker network rm nextcloud-aio 2>/dev/null || echo "Network already removed or in use."
    echo "✓ Network removed."
else
    echo "✓ Network already removed."
fi

echo ""
echo "Step 6: Checking dangling volumes..."
echo "----------------------------------------"
docker volume ls --filter "dangling=true"

echo ""
echo "Step 7: Removing dangling volumes..."
echo "----------------------------------------"
docker volume prune --filter all=1 -f
echo "✓ Dangling volumes removed."

echo ""
echo "Step 8: Checking for remaining AIO volumes..."
echo "----------------------------------------"
AIO_VOLUMES=$(docker volume ls --format '{{.Name}}' | grep "nextcloud" || true)
if [ -n "$AIO_VOLUMES" ]; then
    echo "Found remaining AIO volumes:"
    echo "$AIO_VOLUMES"
    echo ""
    echo "Do you want to remove these volumes? (yes/no)"
    read -r CONFIRM
    if [ "$CONFIRM" = "yes" ]; then
        echo "$AIO_VOLUMES" | xargs -r docker volume rm
        echo "✓ Volumes removed."
    else
        echo "⚠ Volumes kept. You may need to remove them manually."
    fi
else
    echo "✓ No AIO volumes found."
fi

echo ""
echo "Step 9: Checking for custom NEXTCLOUD_DATADIR..."
echo "----------------------------------------"
echo "If you configured a custom NEXTCLOUD_DATADIR, you need to clean it manually."
echo "Common locations:"
echo "  - /mnt/ncdata"
echo "  - Check your docker-compose.yaml for NEXTCLOUD_DATADIR"
echo ""
echo "Do you have a custom datadir to remove? (yes/no)"
read -r HAS_DATADIR
if [ "$HAS_DATADIR" = "yes" ]; then
    echo "Enter the full path to your datadir:"
    read -r DATADIR_PATH
    if [ -d "$DATADIR_PATH" ]; then
        echo "Found directory: $DATADIR_PATH"
        echo "Do you want to DELETE this directory? (Type 'DELETE' to confirm)"
        read -r CONFIRM_DELETE
        if [ "$CONFIRM_DELETE" = "DELETE" ]; then
            sudo rm -rf "$DATADIR_PATH"
            echo "✓ Custom datadir removed."
        else
            echo "⚠ Datadir kept."
        fi
    else
        echo "Directory not found: $DATADIR_PATH"
    fi
fi

echo ""
echo "Step 10: Optional - Remove all Docker images..."
echo "----------------------------------------"
echo "Do you want to remove ALL unused Docker images? (yes/no)"
read -r REMOVE_IMAGES
if [ "$REMOVE_IMAGES" = "yes" ]; then
    docker image prune -a -f
    echo "✓ Docker images removed."
else
    echo "⚠ Docker images kept."
fi

echo ""
echo "================================================"
echo "Reset Complete!"
echo "================================================"
echo ""
echo "You can now start fresh with:"
echo "  cd $(pwd)"
echo "  docker compose up -d"
echo ""
echo "Or follow the official installation guide at:"
echo "  https://github.com/nextcloud/all-in-one"
echo ""
