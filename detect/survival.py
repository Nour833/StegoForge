"""
detect/survival.py - Platform survivability profiles and simulation helpers.
"""
from dataclasses import dataclass
import io

from PIL import Image


@dataclass(frozen=True)
class PlatformProfile:
    name: str
    recompress_to_jpeg: bool
    jpeg_quality: int
    max_dimension: int
    strips_exif: bool
    preferred_method: str
    requires_wet_paper: bool
    notes: str


PROFILES = {
    "twitter": PlatformProfile(
        name="twitter",
        recompress_to_jpeg=True,
        jpeg_quality=85,
        max_dimension=4096,
        strips_exif=True,
        preferred_method="dct",
        requires_wet_paper=True,
        notes="Twitter recompresses most uploads to JPEG.",
    ),
    "instagram": PlatformProfile(
        name="instagram",
        recompress_to_jpeg=True,
        jpeg_quality=82,
        max_dimension=1080,
        strips_exif=True,
        preferred_method="dct",
        requires_wet_paper=True,
        notes="Instagram aggressively resizes and recompresses photos.",
    ),
    "telegram": PlatformProfile(
        name="telegram",
        recompress_to_jpeg=False,
        jpeg_quality=95,
        max_dimension=4096,
        strips_exif=False,
        preferred_method="lsb",
        requires_wet_paper=False,
        notes="Telegram preserves files if sent as file attachment.",
    ),
    "discord": PlatformProfile(
        name="discord",
        recompress_to_jpeg=False,
        jpeg_quality=92,
        max_dimension=4096,
        strips_exif=False,
        preferred_method="dct",
        requires_wet_paper=False,
        notes="Discord frequently preserves originals for file uploads.",
    ),
    "whatsapp": PlatformProfile(
        name="whatsapp",
        recompress_to_jpeg=True,
        jpeg_quality=78,
        max_dimension=1600,
        strips_exif=True,
        preferred_method="dct",
        requires_wet_paper=True,
        notes="WhatsApp applies strong JPEG recompression on images.",
    ),
    "facebook": PlatformProfile(
        name="facebook",
        recompress_to_jpeg=True,
        jpeg_quality=80,
        max_dimension=2048,
        strips_exif=True,
        preferred_method="dct",
        requires_wet_paper=True,
        notes="Facebook recompresses and strips metadata on most uploaded images.",
    ),
    "tiktok": PlatformProfile(
        name="tiktok",
        recompress_to_jpeg=True,
        jpeg_quality=76,
        max_dimension=1920,
        strips_exif=True,
        preferred_method="dct",
        requires_wet_paper=True,
        notes="TikTok applies strong recompression and metadata stripping.",
    ),
    "linkedin": PlatformProfile(
        name="linkedin",
        recompress_to_jpeg=True,
        jpeg_quality=84,
        max_dimension=2048,
        strips_exif=True,
        preferred_method="dct",
        requires_wet_paper=True,
        notes="LinkedIn typically recompresses social-feed images.",
    ),
    "reddit": PlatformProfile(
        name="reddit",
        recompress_to_jpeg=False,
        jpeg_quality=90,
        max_dimension=4096,
        strips_exif=True,
        preferred_method="dct",
        requires_wet_paper=False,
        notes="Reddit may preserve originals in some flows but previews are often recompressed.",
    ),
    "signal": PlatformProfile(
        name="signal",
        recompress_to_jpeg=False,
        jpeg_quality=92,
        max_dimension=4096,
        strips_exif=True,
        preferred_method="lsb",
        requires_wet_paper=False,
        notes="Signal preserves attachments more reliably than in-chat photo mode.",
    ),
}

ALIASES = {
    "x": "twitter",
    "fb": "facebook",
}


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def normalize_platform(name: str) -> str:
    key = (name or "").strip().lower()
    key = ALIASES.get(key, key)
    if key not in PROFILES:
        raise ValueError(
            f"Unsupported platform '{name}'. Choose one of: {', '.join(sorted(PROFILES))}"
        )
    return key


def suggest_encode_profile(target: str) -> PlatformProfile:
    return PROFILES[normalize_platform(target)]


def simulate_platform_pipeline(file_bytes: bytes, filename: str, profile: PlatformProfile) -> tuple[bytes, dict]:
    ext = ""
    if "." in filename:
        ext = filename[filename.rfind("."):].lower()

    if ext not in IMAGE_EXTS:
        return file_bytes, {
            "simulated": False,
            "reason": "non-image carrier; no local recompression simulation applied",
        }

    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    original_size = img.size

    max_dim = profile.max_dimension
    if max(img.size) > max_dim:
        ratio = max_dim / float(max(img.size))
        resized = (max(1, int(img.size[0] * ratio)), max(1, int(img.size[1] * ratio)))
        img = img.resize(resized, Image.LANCZOS)

    out = io.BytesIO()
    output_ext = ext

    if profile.recompress_to_jpeg:
        output_ext = ".jpg"
        img.save(out, format="JPEG", quality=profile.jpeg_quality, subsampling=0)
    else:
        if ext in (".jpg", ".jpeg"):
            img.save(out, format="JPEG", quality=95, subsampling=0)
            output_ext = ".jpg"
        else:
            img.save(out, format="PNG")
            output_ext = ".png"

    return out.getvalue(), {
        "simulated": True,
        "original_size": original_size,
        "post_size": img.size,
        "output_ext": output_ext,
        "profile": profile.name,
        "jpeg_quality": profile.jpeg_quality if profile.recompress_to_jpeg else None,
    }
