#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_UUID="codex-usage@bmikuska.github.com"
EXT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/${EXT_UUID}"
SERVICE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/dbus-1/services"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
LOCAL_BIN="${HOME}/.local/bin"

echo "==> Installing Python package"
python3 -m pip install --user "${ROOT}"

echo "==> Removing legacy installation paths"
rm -f "${SERVICE_DIR}/com.github.bmikuska.ChatGptUsage.service"
systemctl --user disable --now chatgpt-usage.service >/dev/null 2>&1 || true
rm -f "${SYSTEMD_DIR}/chatgpt-usage.service"

echo "==> Installing GNOME Shell extension"
mkdir -p "${EXT_DIR}"
cp -r "${ROOT}/extension/"* "${EXT_DIR}/"

echo "==> Installing D-Bus service file"
mkdir -p "${SERVICE_DIR}"
sed "s|%h/.local/bin/codex-usage|${LOCAL_BIN}/codex-usage|g" \
    "${ROOT}/data/com.github.bmikuska.CodexUsage.service" \
    > "${SERVICE_DIR}/com.github.bmikuska.CodexUsage.service"

echo "==> Installing systemd user service"
mkdir -p "${SYSTEMD_DIR}"
cp "${ROOT}/data/codex-usage.service" "${SYSTEMD_DIR}/"
systemctl --user daemon-reload
systemctl --user enable --now codex-usage.service

echo "==> Enabling GNOME extension"
if ! gnome-extensions enable "${EXT_UUID}"; then
    echo "Warning: could not enable extension (try again after logging out)."
fi

echo ""
echo "Installation complete."
echo ""
echo "Next steps:"
echo "  1. Log out and back in (required on Wayland after install or extension errors)."
echo "  2. Log in:  codex-usage-login"
echo "  3. Verify:  gnome-extensions info ${EXT_UUID}  (State should be ACTIVE)"
echo "  4. On X11 only: restart GNOME Shell from Alt+F2 → r"
