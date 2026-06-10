"""Pipeline Instagram — Atlas Luxury Garden."""

import argparse
import sys
from pathlib import Path

from generate_captions import run_generate
from publish import run_publish


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline Instagram — Atlas Luxury Garden",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--generate",
        action="store_true",
        help="Génère les légendes (statut pending_review), sans publier",
    )
    group.add_argument(
        "--publish",
        action="store_true",
        help="Publie un seul post approved (lundi et jeudi à 18h30)",
    )
    args = parser.parse_args()

    if not Path("photos").exists():
        raise SystemExit("Dossier photos/ introuvable")

    if args.generate:
        print("Mode génération")
        run_generate()
    elif args.publish:
        print("Mode publication")
        run_publish()

    print("\n✓ Terminé")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
