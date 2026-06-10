"""Publie le premier post de captions.json sur Instagram (test, sans contrainte de date/statut)."""

from pathlib import Path

import requests
from dotenv import load_dotenv

from publish import (
    CAPTIONS_FILE,
    GRAPH_API_VERSION,
    IMAGE_EXTENSIONS,
    PHOTOS_DIR,
    build_instagram_caption,
    get_credentials,
    load_posts,
    publish_photo,
)


def fetch_permalink(token: str, media_id: str) -> str:
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
    response = requests.get(
        url,
        params={"fields": "permalink", "access_token": token},
        timeout=60,
    )
    response.raise_for_status()
    permalink = response.json().get("permalink")
    if not permalink:
        raise RuntimeError(f"Permalink introuvable pour media_id {media_id}")
    return permalink


def run_test_publish() -> None:
    load_dotenv()
    token, ig_id = get_credentials()
    posts = load_posts()

    if not posts:
        raise SystemExit(f"Aucun post dans {CAPTIONS_FILE}")

    post = min(posts, key=lambda p: p.get("id", 0))
    photo_path = PHOTOS_DIR / post["photo"]

    if not photo_path.exists():
        raise SystemExit(f"Photo introuvable : {photo_path}")
    if photo_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise SystemExit(f"Format non supporté : {post['photo']}")

    print(f"Test publication du post #{post['id']} ({post['photo']})…")

    caption = build_instagram_caption(post)
    media_id = publish_photo(token, ig_id, photo_path, caption)
    permalink = fetch_permalink(token, media_id)

    print(f"✓ Publié avec succès")
    print(f"  media_id : {media_id}")
    print(f"  URL      : {permalink}")


if __name__ == "__main__":
    run_test_publish()
