"""Génère des légendes Instagram pour Atlas Luxury Garden via Claude."""

import base64
import json
import os
import re
from io import BytesIO
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from PIL import Image

PHOTOS_DIR = Path("photos")
CAPTIONS_FILE = Path("captions.json")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_WIDTH = 2048
JPEG_QUALITY = 85

BRAND_CONTEXT = """
Tu rédiges des légendes Instagram pour Atlas Luxury Garden, hôtel boutique de luxe
dans la vallée de Ouirgane, au pied de l'Atlas, à une heure de Marrakech.

L'établissement propose 8 suites dans un cadre naturel et raffiné, entre jardins,
montagne et hospitalité marocaine contemporaine. Clientèle européenne et marocaine,
30-70 ans, en quête d'authenticité, de sérénité et d'expériences mémorables.

Ton : élégant, chaleureux, évocateur — jamais commercial ou criard.
Langue : français.
Légende : 2 à 4 phrases, sans hashtags dans le texte.
Hashtags : exactement 15 à 20 hashtags pertinents (luxe, Maroc, Ouirgane, Marrakech,
voyage, boutique hotel, Atlas, etc.), sans le symbole #.
N'invente pas de services non visibles sur la photo.
""".strip()


def load_posts() -> list[dict]:
    if CAPTIONS_FILE.exists():
        data = json.loads(CAPTIONS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    return []


def save_posts(posts: list[dict]) -> None:
    CAPTIONS_FILE.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_photos() -> list[Path]:
    if not PHOTOS_DIR.exists():
        raise FileNotFoundError(f"Dossier introuvable : {PHOTOS_DIR}")
    return sorted(
        p for p in PHOTOS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def resize_image_for_api(path: Path) -> bytes:
    """Redimensionne et compresse une image (< 10 Mo, max 2048 px, JPEG 85 %)."""
    with Image.open(path) as img:
        img = img.convert("RGB")

        if img.width > MAX_IMAGE_WIDTH:
            ratio = MAX_IMAGE_WIDTH / img.width
            new_height = round(img.height * ratio)
            img = img.resize((MAX_IMAGE_WIDTH, new_height), Image.Resampling.LANCZOS)

        quality = JPEG_QUALITY
        while quality >= 50:
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            data = buffer.getvalue()
            if len(data) < MAX_IMAGE_BYTES:
                return data
            quality -= 5

        scale = 0.85
        while scale >= 0.3:
            new_width = max(1, round(img.width * scale))
            new_height = max(1, round(img.height * scale))
            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            resized.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            data = buffer.getvalue()
            if len(data) < MAX_IMAGE_BYTES:
                return data
            scale -= 0.1

    raise ValueError(f"Impossible de réduire {path.name} sous 10 Mo")


def encode_image(path: Path) -> tuple[str, str]:
    data = resize_image_for_api(path)
    encoded = base64.standard_b64encode(data).decode("ascii")
    return "image/jpeg", encoded


def parse_generation_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    caption = data.get("caption", "").strip()
    hashtags = [h.lstrip("#").strip() for h in data.get("hashtags", []) if h.strip()]
    if not caption:
        raise ValueError("Légende vide dans la réponse Claude")
    if not (15 <= len(hashtags) <= 20):
        raise ValueError(f"Attendu 15-20 hashtags, reçu {len(hashtags)}")
    return {"caption": caption, "hashtags": hashtags}


def generate_post_content(client: anthropic.Anthropic, photo: Path) -> dict:
    media_type, data = encode_image(photo)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"{BRAND_CONTEXT}\n\n"
                            f"Photo : {photo.name}\n\n"
                            "Réponds uniquement en JSON valide, sans texte autour :\n"
                            '{"caption": "...", "hashtags": ["tag1", "tag2", ...]}'
                        ),
                    },
                ],
            }
        ],
    )
    return parse_generation_response(response.content[0].text)


def next_post_id(posts: list[dict]) -> int:
    if not posts:
        return 1
    return max(p.get("id", 0) for p in posts) + 1


def existing_photos(posts: list[dict]) -> set[str]:
    return {p["photo"] for p in posts}


def run_generate() -> None:
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY manquant dans .env")

    client = anthropic.Anthropic(api_key=api_key)
    posts = load_posts()
    known = existing_photos(posts)
    photos = list_photos()

    if not photos:
        print("Aucune photo trouvée dans photos/")
        return

    created = 0
    for photo in photos:
        if photo.name in known:
            print(f"  ignoré (déjà généré) : {photo.name}")
            continue

        print(f"  génération : {photo.name}")
        content = generate_post_content(client, photo)
        posts.append(
            {
                "id": next_post_id(posts),
                "photo": photo.name,
                "caption": content["caption"],
                "hashtags": content["hashtags"],
                "publish_date": None,
                "publish_time": None,
                "status": "pending_review",
                "ig_post_id": None,
            }
        )
        created += 1

    save_posts(posts)
    print(f"\n{created} nouveau(x) post(s) enregistré(s) dans {CAPTIONS_FILE}")


if __name__ == "__main__":
    run_generate()
