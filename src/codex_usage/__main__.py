from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex usage monitor service")
    parser.add_argument(
        "--login",
        action="store_true",
        help="Run OAuth login and exit",
    )
    parser.add_argument(
        "--print-usage",
        action="store_true",
        help="Fetch and print current usage JSON",
    )
    args = parser.parse_args()

    if args.login:
        from .auth import login_cli

        login_cli()
        return

    if args.print_usage:
        import json

        from .api import get_usage

        print(json.dumps(get_usage().to_variant(), indent=2))
        return

    from .dbus_service import run_dbus_service

    run_dbus_service()


if __name__ == "__main__":
    main()
