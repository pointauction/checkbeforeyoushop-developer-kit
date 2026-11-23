#!/usr/bin/env python3
"""Print tracked CheckBeforeYouShop rates for a store (default: Nike)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "python" / "src"))

from cbys.cli import _ArgumentParser, main


if __name__ == "__main__":
    # Keep the example's optional positional store without duplicating the CLI.
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("store", nargs="?", default="nike")
    parser.add_argument("--program")
    parser.add_argument("--fixtures", metavar="DIR")
    args = parser.parse_args()
    command = ["store", args.store]
    if args.program is not None:
        command.extend(["--program", args.program])
    if args.fixtures is not None:
        command.extend(["--fixtures", args.fixtures])
    raise SystemExit(main(command))
