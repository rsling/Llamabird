#!/usr/bin/env bash
#
# Llamabird Daemon Installation Script
#
# This script installs and configures the Llamabird daemon as a systemd user service.
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}======================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "  $1"
}

# Get script directory (where Llamabird is installed)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
SERVICE_FILE="$HOME/.config/systemd/user/llamabird.service"

print_header "LLAMABIRD DAEMON INSTALLATION"

# Check if virtual environment exists
if [ ! -f "$VENV_PYTHON" ]; then
    print_error "Virtual environment not found at: $VENV_PYTHON"
    print_info "Please create a virtual environment first:"
    print_info "  python3 -m venv venv"
    print_info "  venv/bin/pip install -r requirements.txt"
    exit 1
fi

print_success "Virtual environment found"

# Step 1: Install/update dependencies
print_header "1. Installing Dependencies"

print_info "Installing watchdog for file monitoring..."
"$VENV_PYTHON" -m pip install -q watchdog>=3.0.0

if [ $? -eq 0 ]; then
    print_success "Dependencies installed"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Step 2: Regenerate configuration
print_header "2. Updating Configuration"

if [ -f "$SCRIPT_DIR/config.json" ]; then
    print_info "Backing up existing config.json..."
    cp "$SCRIPT_DIR/config.json" "$SCRIPT_DIR/config.json.backup"
    print_success "Backup created: config.json.backup"
fi

print_info "Regenerating config.json with daemon settings..."
cd "$SCRIPT_DIR"
"$VENV_PYTHON" discover.py > /dev/null

if [ $? -eq 0 ]; then
    print_success "Configuration updated"
else
    print_error "Failed to regenerate configuration"
    exit 1
fi

# Step 3: Create systemd service file
print_header "3. Creating systemd Service"

# Create systemd user directory if it doesn't exist
mkdir -p "$HOME/.config/systemd/user"

# Generate service file from template
print_info "Generating service file..."
sed -e "s|LLAMABIRD_PATH|$SCRIPT_DIR|g" \
    -e "s|VENV_PYTHON|$VENV_PYTHON|g" \
    "$SCRIPT_DIR/llamabird.service.template" > "$SERVICE_FILE"

if [ $? -eq 0 ]; then
    print_success "Service file created: $SERVICE_FILE"
else
    print_error "Failed to create service file"
    exit 1
fi

# Step 4: Reload systemd and enable service
print_header "4. Enabling systemd Service"

print_info "Reloading systemd daemon..."
systemctl --user daemon-reload

if [ $? -ne 0 ]; then
    print_error "Failed to reload systemd daemon"
    exit 1
fi

print_info "Enabling Llamabird service..."
systemctl --user enable llamabird.service

if [ $? -eq 0 ]; then
    print_success "Service enabled (will start at login)"
else
    print_error "Failed to enable service"
    exit 1
fi

# Step 5: Show usage instructions
print_header "INSTALLATION COMPLETE"

print_success "Llamabird daemon has been installed successfully!"

echo ""
print_info "Configuration:"
print_info "  • Mode: auto (file watching with debouncing)"
print_info "  • Debounce: 30 seconds"
print_info "  • Log file: $SCRIPT_DIR/llamabird_daemon.log"
echo ""

print_info "To start the daemon now:"
print_info "  ${GREEN}systemctl --user start llamabird${NC}"
echo ""

print_info "To check daemon status:"
print_info "  ${GREEN}systemctl --user status llamabird${NC}"
echo ""

print_info "To view live logs:"
print_info "  ${GREEN}journalctl --user -u llamabird -f${NC}"
echo ""

print_info "To stop the daemon:"
print_info "  ${GREEN}systemctl --user stop llamabird${NC}"
echo ""

print_info "To disable autostart:"
print_info "  ${GREEN}systemctl --user disable llamabird${NC}"
echo ""

print_warning "The daemon will start automatically at your next login."
print_warning "To start it immediately, run: systemctl --user start llamabird"

echo ""
