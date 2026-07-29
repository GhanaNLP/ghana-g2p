"""Command line interface for ghana-g2p."""
from __future__ import annotations

import argparse
import sys

from ghana_g2p.core import GhanaG2P, UnknownLanguage, languages


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ghana-g2p", description=__doc__)
    ap.add_argument("lang", nargs="?", help="language code, name, or ghana-speech config name")
    ap.add_argument("text", nargs="*", help="text to phonemise (default: stdin)")
    ap.add_argument("--grapheme", action="store_true", help="native-orthography units instead of IPA")
    ap.add_argument("--sep", default="", help="separator between units (default: none)")
    ap.add_argument("--list", action="store_true", help="list supported languages")
    ap.add_argument("--info", action="store_true", help="show rule provenance for the language")
    args = ap.parse_args(argv)

    if args.list:
        for info in languages():
            tier = info["tier"]
            mark = " (donor: %s)" % info["rules"] if tier == "donor" else ""
            print(f"{info['code']:6}\t{info['name']}{mark}")
        return 0

    if not args.lang:
        ap.error("a language is required")

    try:
        g = GhanaG2P(args.lang)
    except UnknownLanguage as e:
        print(e, file=sys.stderr)
        return 2

    if args.info:
        print(f"language : {g.info['name']} ({g.code})")
        print(f"family   : {g.info.get('family', '-')}")
        print(f"rules    : {g.rules} ({g.tier})")
        if g.info.get("note"):
            print(f"note     : {g.info['note']}")
        if g.info.get("coverage") is not None:
            print(f"coverage : {g.info['coverage']}")
        return 0

    out = "grapheme" if args.grapheme else "ipa"
    lines = [" ".join(args.text)] if args.text else (l.rstrip("\n") for l in sys.stdin)
    for line in lines:
        print(g.convert(line, out, args.sep).phonemes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
