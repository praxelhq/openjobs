"""Explicit local imports and direct hosted searches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from .greenhouse import fetch_board
from .praxy import search_praxy_jobs
from .store import MAX_FEED_BYTES, open_db, sync_jobs_with_receipt


def main() -> None:
    parser = argparse.ArgumentParser(prog="openjobs")
    commands = parser.add_subparsers(dest="command", required=True)

    imported = commands.add_parser(
        "import-json", help="Import a complete source feed from a JSON array"
    )
    imported.add_argument("path", type=Path)
    imported.add_argument("--source", required=True, help="Stable key for this feed")
    imported.add_argument(
        "--allow-empty",
        action="store_true",
        help="Confirm that an empty feed should close every job",
    )

    greenhouse = commands.add_parser(
        "import-greenhouse", help="Fetch one explicitly selected Greenhouse board"
    )
    greenhouse.add_argument("board_token")
    greenhouse.add_argument("--company", required=True)
    greenhouse.add_argument(
        "--confirm-rights",
        action="store_true",
        help="Confirm you may index/display this board",
    )
    greenhouse.add_argument(
        "--allow-empty",
        action="store_true",
        help="Confirm that an empty board should close every job",
    )

    hosted = commands.add_parser(
        "search-praxy", help="Search one page of Praxy Jobs' hosted API"
    )
    hosted.add_argument("query", nargs="?", default="")
    hosted.add_argument("--country", default="", help="Comma-separated country codes")
    hosted.add_argument("--city", default="")
    hosted.add_argument("--company", default="")
    hosted.add_argument("--source", default="", help="Comma-separated ATS source codes")
    hosted.add_argument("--remote", choices=("only", "exclude"), default="")
    hosted.add_argument("--status", choices=("open", "closed", "all"), default="open")
    hosted.add_argument("--exclude-duplicates", action="store_true")
    hosted.add_argument("--include-description", action="store_true")
    hosted.add_argument("--limit", type=int, default=20)
    hosted.add_argument(
        "--cursor", default="", help="Opaque cursor from the prior page"
    )

    args = parser.parse_args()
    try:
        if args.command == "search-praxy":
            page = search_praxy_jobs(
                query=args.query,
                country=args.country,
                city=args.city,
                company=args.company,
                source=args.source,
                remote=args.remote,
                status=args.status,
                exclude_duplicates=args.exclude_duplicates,
                include_description=args.include_description,
                limit=args.limit,
                cursor=args.cursor,
            )
            print(json.dumps(page, indent=2, sort_keys=True))
            return
        if args.command == "import-json":
            with args.path.open("rb") as feed:
                raw = feed.read(MAX_FEED_BYTES + 1)
            if len(raw) > MAX_FEED_BYTES:
                parser.error(f"JSON feed exceeds {MAX_FEED_BYTES} bytes")
            payload = json.loads(raw)
            if not isinstance(payload, list):
                parser.error("JSON feed must be an array of jobs")
            source, jobs = args.source, payload
        else:
            if not args.confirm_rights:
                parser.error(
                    "Check the board owner's terms, then pass --confirm-rights"
                )
            source = f"greenhouse:{args.board_token}"
            jobs = fetch_board(args.board_token, args.company)
        with open_db() as connection:
            receipt = sync_jobs_with_receipt(
                connection,
                source,
                jobs,
                import_kind=args.command.removeprefix("import-"),
                allow_empty=args.allow_empty,
            )
    except (ValueError, OSError, httpx.HTTPError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
