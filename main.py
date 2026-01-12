#!/usr/bin/env python3
"""
Nat - The NationBuilder Assistant

Entry point for running Nat interactively or as a single query.

Usage:
    # Interactive mode
    python main.py

    # Single query mode
    python main.py --query "Find person by email john@example.com"

Environment variables (or .env file):
    NATIONBUILDER_SLUG: Your nation's slug
    NATIONBUILDER_API_TOKEN: Your V2 API token
    ANTHROPIC_API_KEY: Your Anthropic API key
    CLAUDE_MODEL: (optional) Model to use, defaults to claude-sonnet-4-20250514
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv


def main() -> None:
    """Main entry point."""
    # Load environment variables from .env file
    load_dotenv()

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Nat - The NationBuilder Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Single query mode: send a query and print the response"
    )
    parser.add_argument(
        "--slug",
        type=str,
        default=os.getenv("NATIONBUILDER_SLUG"),
        help="NationBuilder nation slug (or set NATIONBUILDER_SLUG env var)"
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.getenv("NATIONBUILDER_API_TOKEN"),
        help="NationBuilder V2 API token (or set NATIONBUILDER_API_TOKEN env var)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        help="Claude model to use (default: claude-haiku-4-5-20251001, use --model claude-sonnet-4-5-20250929 for complex queries)"
    )

    args = parser.parse_args()

    # Validate required configuration
    if not args.slug:
        print("Error: NationBuilder slug is required.")
        print("Set NATIONBUILDER_SLUG environment variable or use --slug flag.")
        sys.exit(1)

    if not args.token:
        print("Error: NationBuilder API token is required.")
        print("Set NATIONBUILDER_API_TOKEN environment variable or use --token flag.")
        sys.exit(1)

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is required.")
        print("Get your API key from https://console.anthropic.com/")
        sys.exit(1)

    # Import agent functions (after validation to avoid import errors)
    from src.nat.agent import run_nat_interactive, query_nat

    # Run in appropriate mode
    if args.query:
        # Single query mode
        result = asyncio.run(query_nat(
            prompt=args.query,
            slug=args.slug,
            token=args.token,
            model=args.model
        ))
        print(result)
    else:
        # Interactive mode
        asyncio.run(run_nat_interactive(
            slug=args.slug,
            token=args.token,
            model=args.model
        ))


if __name__ == "__main__":
    main()
