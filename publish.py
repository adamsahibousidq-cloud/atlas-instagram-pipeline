"""Publie les posts approuvés sur Instagram via l'API Graph Meta."""

import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

PHOTOS_DIR = Path("photos")
CAPTIONS_FILE = Path("captions.json")
GRAPH_API_VERSION = "v21.0"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
GITHUB_PHOTOS_BASE = (
    "https://raw.githubusercontent.com/adamsahibousidq-cloud/"
    "atlas-instagram-pipeline/main/photos/"
)
TIMEZONE = "Europe/Paris"


def now_local() -> datetime:
    """Heure courante en Europe/Paris (horloge système réglée sur ce fuseau)."""
    return datetime.now()

MONDAY_SLOT = (0, time(18, 30))
THURSDAY_SLOT = (3, time(18, 30))
FIRST_SLOT = datetime(2026, 6, 11, 18, 30)  # jeudi 11 juin 2026, 18h30
PUBLISH_TIME = "18:30"
MIN_DAYS_BETWEEN = 3
MAX_POSTS_PER_WEEK = 2


def load_posts() -> list[dict]:
    if not CAPTIONS_FILE.exists():
        return []
    data = json.loads(CAPTIONS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{CAPTIONS_FILE} doit contenir une liste de posts")
    return data


def save_posts(posts: list[dict]) -> None:
    CAPTIONS_FILE.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_credentials() -> tuple[str, str]:
    token = os.getenv("PAGE_ACCESS_TOKEN")
    ig_id = os.getenv("IG_ACCOUNT_ID")
    if not token or not ig_id:
        raise SystemExit("PAGE_ACCESS_TOKEN et IG_ACCOUNT_ID requis dans .env")
    return token, ig_id


def post_datetime(post: dict) -> datetime | None:
    if not post.get("publish_date") or not post.get("publish_time"):
        return None
    return datetime.fromisoformat(f"{post['publish_date']}T{post['publish_time']}:00")


def format_slot(dt: datetime) -> str:
    days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    label = days[dt.weekday()]
    return f"{label} {dt.strftime('%d/%m/%Y')} à {dt.strftime('%H:%M')}"


def next_slot_from(dt: datetime, *, strict: bool = False) -> datetime:
    """Prochain créneau lundi 18h30 ou jeudi 18h30 à partir de dt."""
    start = dt if strict else dt
    for offset in range(15):
        day = start.date() + timedelta(days=offset)
        for weekday, slot_time in (MONDAY_SLOT, THURSDAY_SLOT):
            if day.weekday() != weekday:
                continue
            candidate = datetime.combine(day, slot_time)
            if strict and candidate <= dt:
                continue
            if not strict and candidate < dt:
                continue
            return candidate
    raise RuntimeError("Impossible de calculer le prochain créneau")


def next_slot_in_sequence(after: datetime) -> datetime:
    """Créneau suivant : jeudi 18h30 → lundi 18h30 → jeudi 18h30…"""
    if after.weekday() == THURSDAY_SLOT[0] and after.time() == THURSDAY_SLOT[1]:
        return after + timedelta(days=4)
    if after.weekday() == MONDAY_SLOT[0] and after.time() == MONDAY_SLOT[1]:
        return after + timedelta(days=3)
    return next_slot_from(after, strict=True)


def last_published_datetime(posts: list[dict]) -> datetime | None:
    published = [
        post_datetime(p)
        for p in posts
        if p.get("status") == "published" and post_datetime(p)
    ]
    return max(published) if published else None


def posts_published_in_week(posts: list[dict], ref: datetime) -> int:
    week_start = ref.date() - timedelta(days=ref.weekday())
    week_end = week_start + timedelta(days=6)
    count = 0
    for post in posts:
        if post.get("status") != "published":
            continue
        dt = post_datetime(post)
        if dt and week_start <= dt.date() <= week_end:
            count += 1
    return count


def assignment_start(posts: list[dict], now: datetime) -> datetime:
    last = last_published_datetime(posts)
    if last:
        return next_slot_in_sequence(last)
    if now < FIRST_SLOT:
        return FIRST_SLOT
    return next_slot_from(now)


def assign_publish_dates(posts: list[dict], now: datetime) -> bool:
    """Assigne les créneaux aux posts approved sans date. Retourne True si modifié."""
    to_schedule = sorted(
        [p for p in posts if p.get("status") == "approved" and not p.get("publish_date")],
        key=lambda p: p.get("id", 0),
    )
    if not to_schedule:
        return False

    slot = assignment_start(posts, now)
    for post in to_schedule:
        post["publish_date"] = slot.date().isoformat()
        post["publish_time"] = PUBLISH_TIME
        slot = next_slot_in_sequence(slot)
    return True


def build_instagram_caption(post: dict) -> str:
    tags = " ".join(f"#{h.lstrip('#')}" for h in post.get("hashtags", []))
    return f"{post['caption']}\n\n{tags}".strip()


def github_photo_url(filename: str) -> str:
    return f"{GITHUB_PHOTOS_BASE}{quote(filename)}"


def create_media_container(
    token: str,
    ig_id: str,
    caption: str,
    image_url: str | None = None,
) -> str:
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_id}/media"
    params = {}
    data = {"access_token": token, "caption": caption}
    if image_url:
        params["image_url"] = image_url
    else:
        data["upload_type"] = "resumable"
        data["media_type"] = "IMAGE"
    response = requests.post(url, params=params, data=data, timeout=60)
    response.raise_for_status()
    container_id = response.json().get("id")
    if not container_id:
        raise RuntimeError(f"Conteneur non créé : {response.text}")
    return container_id


def upload_image(token: str, container_id: str, image_path: Path) -> None:
    file_size = image_path.stat().st_size
    url = f"https://rupload.facebook.com/ig-api-upload/{GRAPH_API_VERSION}/{container_id}"
    with image_path.open("rb") as f:
        response = requests.post(
            url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=f,
            timeout=120,
        )
    response.raise_for_status()


def publish_media(token: str, ig_id: str, container_id: str) -> str:
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_id}/media_publish"
    response = requests.post(
        url,
        params={
            "access_token": token,
            "creation_id": container_id,
        },
        timeout=60,
    )
    response.raise_for_status()
    media_id = response.json().get("id")
    if not media_id:
        raise RuntimeError(f"Publication échouée : {response.text}")
    return media_id


def publish_photo(token: str, ig_id: str, photo: Path, caption: str) -> str:
    image_url = github_photo_url(photo.name)
    container_id = create_media_container(token, ig_id, caption, image_url=image_url)
    return publish_media(token, ig_id, container_id)


def can_publish_now(posts: list[dict], candidate: dict, now: datetime) -> tuple[bool, str]:
    scheduled = post_datetime(candidate)
    if not scheduled:
        return False, "Date de publication manquante"

    if now < scheduled:
        return False, f"Créneau non atteint (prévu le {format_slot(scheduled)})"

    last = last_published_datetime(posts)
    if last:
        delta = now - last
        if delta < timedelta(days=MIN_DAYS_BETWEEN):
            next_allowed = last + timedelta(days=MIN_DAYS_BETWEEN)
            return False, (
                f"Délai minimum de {MIN_DAYS_BETWEEN} jours non respecté "
                f"(prochaine publication possible après le {format_slot(next_allowed)})"
            )

    if posts_published_in_week(posts, now) >= MAX_POSTS_PER_WEEK:
        next_week_slot = next_slot_from(
            datetime.combine(
                now.date() + timedelta(days=7 - now.weekday()),
                time(0, 0),
            )
        )
        return False, (
            f"Limite de {MAX_POSTS_PER_WEEK} publications cette semaine atteinte "
            f"(prochain créneau : {format_slot(next_week_slot)})"
        )

    return True, ""


def next_pending_slot(posts: list[dict], now: datetime) -> datetime | None:
    approved = [
        post_datetime(p)
        for p in posts
        if p.get("status") == "approved" and post_datetime(p)
    ]
    future = sorted(dt for dt in approved if dt and dt > now)
    if future:
        return future[0]

    if any(p.get("status") == "approved" and not p.get("publish_date") for p in posts):
        return assignment_start(posts, now)

    return None


def run_publish() -> None:
    load_dotenv()
    token, ig_id = get_credentials()
    posts = load_posts()
    now = now_local()

    if not posts:
        raise SystemExit(f"Aucun post dans {CAPTIONS_FILE}. Lancez d'abord : python pipeline.py --generate")

    if assign_publish_dates(posts, now):
        save_posts(posts)
        print("Créneaux assignés aux posts approuvés.")

    candidates = sorted(
        [
            p for p in posts
            if p.get("status") == "approved" and post_datetime(p) and post_datetime(p) <= now
        ],
        key=lambda p: (post_datetime(p), p.get("id", 0)),
    )

    if not candidates:
        approved_count = sum(1 for p in posts if p.get("status") == "approved")
        if approved_count == 0:
            print("Aucun post avec le statut approved.")
            return

        nxt = next_pending_slot(posts, now)
        if nxt:
            print(f"Ce n'est pas encore l'heure de publier. Prochaine publication prévue : {format_slot(nxt)}")
        else:
            print("Aucun post approved prêt à être publié.")
        return

    post = candidates[0]
    allowed, reason = can_publish_now(posts, post, now)
    if not allowed:
        print(f"Publication reportée : {reason}")
        return

    photo_path = PHOTOS_DIR / post["photo"]
    if not photo_path.exists():
        raise SystemExit(f"Photo introuvable : {photo_path}")
    if photo_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise SystemExit(f"Format non supporté : {post['photo']}")

    scheduled = post_datetime(post)
    print(f"Publication du post #{post['id']} ({post['photo']}) — créneau {format_slot(scheduled)}")

    caption = build_instagram_caption(post)
    media_id = publish_photo(token, ig_id, photo_path, caption)

    post["status"] = "published"
    post["ig_post_id"] = media_id
    save_posts(posts)

    print(f"✓ Publié avec succès (ig_post_id: {media_id})")

    remaining = sum(1 for p in posts if p.get("status") == "approved")
    if remaining:
        nxt = next_pending_slot(posts, now_local())
        if nxt:
            print(f"Prochaine publication prévue : {format_slot(nxt)}")


if __name__ == "__main__":
    run_publish()
