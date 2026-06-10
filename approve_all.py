"""Approuve tous les posts et assigne les créneaux de publication."""

import json
from datetime import datetime, timedelta
from pathlib import Path

CAPTIONS_FILE = Path("captions.json")
FIRST_SLOT = datetime(2026, 6, 11, 18, 30)  # jeudi 11 juin 2026, 18h30
PUBLISH_TIME = "18:30"


def load_posts() -> list[dict]:
    if not CAPTIONS_FILE.exists():
        raise SystemExit(f"{CAPTIONS_FILE} introuvable")
    data = json.loads(CAPTIONS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{CAPTIONS_FILE} doit contenir une liste de posts")
    return data


def save_posts(posts: list[dict]) -> None:
    CAPTIONS_FILE.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def next_slot(current: datetime) -> datetime:
    if current.weekday() == 3:  # jeudi → lundi
        return current + timedelta(days=4)
    if current.weekday() == 0:  # lundi → jeudi
        return current + timedelta(days=3)
    raise ValueError(f"Créneau inattendu : {current}")


def iter_slots(count: int) -> list[datetime]:
    slots = []
    current = FIRST_SLOT
    for _ in range(count):
        slots.append(current)
        current = next_slot(current)
    return slots


def approve_all() -> None:
    posts = load_posts()
    if not posts:
        print("Aucun post dans captions.json")
        return

    posts.sort(key=lambda p: p.get("id", 0))
    slots = iter_slots(len(posts))

    for post, slot in zip(posts, slots):
        post["status"] = "approved"
        post["publish_date"] = slot.date().isoformat()
        post["publish_time"] = PUBLISH_TIME

    save_posts(posts)
    print(f"{len(posts)} post(s) approuvé(s) et planifié(s) dans {CAPTIONS_FILE}")
    print(f"Premier créneau : jeudi 11/06/2026 à {PUBLISH_TIME}")
    print(f"Dernier créneau  : {slots[-1].strftime('%A %d/%m/%Y')} à {PUBLISH_TIME}")


if __name__ == "__main__":
    approve_all()
