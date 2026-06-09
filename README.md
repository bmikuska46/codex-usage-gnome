# Codex GNOME Usage

GNOME top bar indicator for Codex plan usage.

It shows:

- remaining usage in the rolling 5-hour window
- remaining usage in the weekly window
- reset times for both windows
- your account email and plan details

The panel label shows the primary 5-hour remaining percentage.

Tested on Ubuntu 26.04, GNOME 50, and Wayland.

## How it works

This repo has two parts:

- a Python backend that logs in with your OpenAI account, fetches usage from `https://chatgpt.com/backend-api/wham/usage`, and exposes it over D-Bus
- a GNOME Shell extension that reads that D-Bus service and renders the indicator in the top bar

If you already use Codex CLI, existing tokens in `~/.codex/auth.json` or `~/.config/codex/auth.json` are reused automatically. Existing installs in `~/.config/chatgpt-usage/auth.json` are also read automatically.

## Requirements

Install the system packages first:

```bash
sudo apt update
sudo apt install -y git python3-pip python3-gi python3-dbus gir1.2-glib-2.0
```

## Install

Clone the repository and run the installer:

```bash
git clone https://github.com/bmikuska46/codex-usage-gnome.git
cd codex-usage-gnome
chmod +x install.sh
./install.sh
```

The installer will:

- install the Python package with `pip --user`
- copy the GNOME extension into `~/.local/share/gnome-shell/extensions/`
- install the D-Bus service file
- install and start the `systemd --user` service
- try to enable the GNOME extension

On Wayland, log out and back in after installation if the extension does not appear immediately.

## Log in

Start the OAuth flow:

```bash
codex-usage-login
```

This opens your browser, completes login on `localhost:1455`, and stores tokens in:

```text
~/.config/codex-usage/auth.json
```

## Verify It Works

Check the extension:

```bash
gnome-extensions info codex-usage@bmikuska.github.com
```

Check the background service:

```bash
systemctl --user status codex-usage.service
```

Fetch the current usage manually:

```bash
codex-usage --print-usage
```

## Update

To update after pulling new changes:

```bash
cd codex-usage-gnome
git pull
./install.sh
```

## Uninstall

```bash
gnome-extensions disable codex-usage@bmikuska.github.com
rm -rf ~/.local/share/gnome-shell/extensions/codex-usage@bmikuska.github.com
systemctl --user disable --now codex-usage.service
rm -f ~/.config/systemd/user/codex-usage.service
rm -f ~/.local/share/dbus-1/services/com.github.bmikuska.CodexUsage.service
python3 -m pip uninstall codex-usage
```

## Troubleshooting

- If the indicator does not appear on Wayland, log out and back in.
- If the service is not running, restart it with `systemctl --user restart codex-usage.service`.
- If login fails, run `codex-usage-login` again to refresh tokens.

## Security Notes

- Tokens are stored in `~/.config/codex-usage/auth.json`.
- Do not commit or share that file.
- This project uses an undocumented internal ChatGPT web API, so it may break if the upstream API changes.

## License

GPL-3.0-or-later
