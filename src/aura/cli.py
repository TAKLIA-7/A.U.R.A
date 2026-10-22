"""AURA CLI entry point."""
from __future__ import annotations
import sys
import os
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aura",
        description="AURA — Agent Control Plane: Interception, Risk Assessment, and Observability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aura              Launch the interactive TUI
  aura --mock       Force mock mode (no API keys needed)
  aura --version    Show version

Environment Variables:
  GOOGLE_API_KEY          Gemini API key
  AURA_JEV_MOCK_MODE      Set to 'false' to use real JEV
  AURA_JEV_ENDPOINT       Real JEV API endpoint
  AURA_JEV_API_KEY        JEV API key
        """,
    )
    parser.add_argument("--version", action="version", version="AURA 0.1.0")
    parser.add_argument("--mock", action="store_true", help="Force mock mode for all providers")
    parser.add_argument("--no-color", action="store_true", help="Disable color output")
    parser.add_argument("--data-dir", default=None, help="Override data directory")
    args = parser.parse_args()

    if args.mock:
        os.environ["AURA_JEV_MOCK_MODE"] = "true"
    if args.no_color:
        os.environ["AURA_NO_COLOR"] = "true"
    if args.data_dir:
        os.environ["AURA_DATA_DIR"] = args.data_dir

    # Load config and ensure dirs
    from aura.config import get_config
    cfg = get_config()

    # Show startup banner in non-TUI mode
    try:
        from aura.app import AURAApp
        app = AURAApp()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nAURA startup error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
