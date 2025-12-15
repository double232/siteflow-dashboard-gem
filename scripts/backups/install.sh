#!/bin/bash
# SiteFlow Backup System Installation Script
# Run as root on the webserver

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.env"

echo "=== SiteFlow Backup System Installation ==="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root"
    exit 1
fi

# Load config if exists
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo "ERROR: config.env not found. Copy config.env.example to config.env and configure it."
    exit 1
fi

# Install required packages
echo "[1/7] Installing required packages..."
apt-get update -qq
apt-get install -y -qq cifs-utils jq curl

# Install restic if not present
if ! command -v restic &> /dev/null; then
    echo "[2/7] Installing restic..."
    apt-get install -y -qq restic
else
    echo "[2/7] Restic already installed: $(restic version)"
fi

# Create mount point
echo "[3/7] Creating mount point..."
mkdir -p "${NAS_MOUNT}"

# Create credentials file template if not exists
echo "[4/7] Setting up NAS credentials..."
if [[ ! -f "${NAS_CRED_FILE}" ]]; then
    cat > "${NAS_CRED_FILE}" << 'EOF'
username=your_nas_username
password=your_nas_password
domain=WORKGROUP
EOF
    chmod 600 "${NAS_CRED_FILE}"
    echo "  Created ${NAS_CRED_FILE} - EDIT THIS FILE with your NAS credentials!"
else
    echo "  ${NAS_CRED_FILE} already exists"
fi

# Add fstab entry if not present
echo "[5/7] Configuring /etc/fstab..."
FSTAB_ENTRY="//${NAS_IP}/${NAS_SHARE} ${NAS_MOUNT} cifs credentials=${NAS_CRED_FILE},vers=3.1.1,_netdev,nofail,serverino,uid=0,gid=0,file_mode=0600,dir_mode=0700 0 0"

if ! grep -q "${NAS_MOUNT}" /etc/fstab; then
    echo "${FSTAB_ENTRY}" >> /etc/fstab
    echo "  Added fstab entry"
else
    echo "  fstab entry already exists"
fi

# Mount the share
echo "[6/7] Mounting NAS share..."
if mountpoint -q "${NAS_MOUNT}"; then
    echo "  Already mounted"
else
    if mount "${NAS_MOUNT}"; then
        echo "  Mounted successfully"
    else
        echo "  WARNING: Mount failed. Check credentials in ${NAS_CRED_FILE}"
        echo "  You may need to edit the credentials and run: mount ${NAS_MOUNT}"
    fi
fi

# Initialize restic repository
echo "[7/7] Initializing restic repository..."
if [[ ! -f "${RESTIC_PASSWORD_FILE}" ]]; then
    # Generate a random password
    openssl rand -base64 32 > "${RESTIC_PASSWORD_FILE}"
    chmod 600 "${RESTIC_PASSWORD_FILE}"
    echo "  Generated restic password in ${RESTIC_PASSWORD_FILE}"
    echo "  IMPORTANT: Back up this password securely!"
fi

if [[ -d "${RESTIC_REPO}" ]] && restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" snapshots &>/dev/null; then
    echo "  Restic repository already initialized"
else
    mkdir -p "$(dirname "${RESTIC_REPO}")"
    if restic -r "${RESTIC_REPO}" --password-file "${RESTIC_PASSWORD_FILE}" init; then
        echo "  Restic repository initialized at ${RESTIC_REPO}"
    else
        echo "  WARNING: Failed to initialize restic repository"
        echo "  Ensure NAS is mounted and try: restic -r ${RESTIC_REPO} --password-file ${RESTIC_PASSWORD_FILE} init"
    fi
fi

# Create directories
mkdir -p "${LOG_DIR}"
mkdir -p "${RUN_DIR}"

# Make scripts executable
chmod +x "${SCRIPT_DIR}"/*.sh

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit ${NAS_CRED_FILE} with your NAS username/password"
echo "2. Run: mount ${NAS_MOUNT}"
echo "3. Copy systemd units: cp ${SCRIPT_DIR}/systemd/* /etc/systemd/system/"
echo "4. Enable timers: systemctl enable --now siteflow-backup-db.timer siteflow-backup-uploads.timer"
echo ""
echo "Test backup manually:"
echo "  ${SCRIPT_DIR}/backup_db.sh"
echo "  ${SCRIPT_DIR}/backup_uploads.sh"
