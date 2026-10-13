"""Command line: ``python -m geosigma {check,build,serve}``."""
from __future__ import annotations

import argparse
import sys
from collections import Counter

from .store import build_database, load_catalogue


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="geosigma")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate all survey and dataset files")
    b = sub.add_parser("build", help="validate, then rebuild build/geosigma.sqlite")
    b.add_argument("--approved-only", action="store_true", help="leave out draft datasets")
    s = sub.add_parser("serve", help="run the web interface")
    s.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    if args.cmd in ("check", "build"):
        cat = load_catalogue()
        print(f"{len(cat.surveys)} surveys, {sum(len(s.sites) for s in cat.surveys)} sites, {len(cat.datasets)} datasets")
        for (lvl, rep), n in sorted(Counter((d.level.value, d.representation.value) for d in cat.datasets).items()):
            print(f"  {lvl} {rep}: {n}")
        for p in cat.problems:
            print("PROBLEM:", p)
        if args.cmd == "build":
            path = build_database(cat, include_drafts=not args.approved_only)
            print("built", path)
        return 1 if cat.problems else 0
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("geosigma.api:app", host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
