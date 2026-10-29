from io import BytesIO

import imagehash
from PIL import Image, ImageChops


PHASH_THRESHOLD = 6


def compute_diff(
    image_before: bytes,
    image_after: bytes,
) -> int:
    if not image_before or not image_after:
        raise ValueError("Both before and after screenshots are required.")

    with Image.open(BytesIO(image_before)) as before:
        before_image = before.convert("RGB")

    with Image.open(BytesIO(image_after)) as after:
        after_image = after.convert("RGB")

    if before_image.size != after_image.size:
        after_image = after_image.resize(before_image.size)

    hash_before = imagehash.phash(before_image)
    hash_after = imagehash.phash(after_image)

    return int(hash_before - hash_after)


def verify_screen_change(
    image_before: bytes,
    image_after: bytes,
    threshold: int = PHASH_THRESHOLD,
) -> dict:
    difference = compute_diff(image_before, image_after)
    changed = difference > threshold

    result = {
        "difference": difference,
        "threshold": threshold,
        "screen_changed": changed,
        "status": "changed" if changed else "unchanged",
    }

    print(
        f"[VERIFY] Screen difference: {difference} | "
        f"Threshold: {threshold} | "
        f"Status: {result['status']}"
    )

    return result