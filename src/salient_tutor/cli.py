"""CLI entry point — send a message to the tutor."""

from __future__ import annotations

import argparse
import asyncio
import sys

from salient_tutor.daemon import TutorDaemon


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="salient-tutor",
        description="A spaced-repetition teaching agent on salient-core.",
    )
    parser.add_argument("message", nargs="?", help="Message to send to the tutor.")
    parser.add_argument(
        "--agent",
        default="tutor",
        choices=["tutor", "librarian"],
        help="Which agent to address (default: tutor).",
    )
    parser.add_argument(
        "--work-root",
        default="work",
        help="Working directory for persistent state (default: work).",
    )
    args = parser.parse_args()

    if not args.message:
        parser.print_help()
        sys.exit(1)

    result = asyncio.run(_run(args.agent, args.message, args.work_root))
    print(result)


async def _run(agent: str, message: str, work_root: str) -> str:
    daemon = TutorDaemon(work_root=work_root)
    await daemon.start()
    try:
        return await daemon.prompt(agent, message)
    finally:
        await daemon.stop()


if __name__ == "__main__":
    main()
