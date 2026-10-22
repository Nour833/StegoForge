"""web/blueprints/forms — shared detector-toggle parsing for web routes."""
from __future__ import annotations

TOGGLE_KEYS = ["chi2", "rs", "exif", "blind", "ml", "fingerprint", "binary"]


def parse_detector_flags(form) -> dict[str, bool]:
    """Parse detector toggles with 'all-on-by-default, explicit-opt-out' semantics."""
    explicit = any(k in form for k in TOGGLE_KEYS)
    out: dict[str, bool] = {}
    for k in TOGGLE_KEYS:
        if k not in form:
            out[k] = not explicit
        else:
            out[k] = str(form.get(k, "")).strip().lower() in {"1", "true", "yes", "on"}
    return out
