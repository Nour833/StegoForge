"""scripts/make_sbom.py — CycloneDX SBOM from installed distributions.

No extra dependencies (importlib.metadata only). Emits CycloneDX 1.5 JSON
to stdout (redirect to sbom.cdx.json). Includes tool version + generation time.
Usage: python scripts/make_sbom.py > sbom.cdx.json
"""
from __future__ import annotations

import datetime
import json
from importlib import metadata


def main() -> int:
    try:
        tool_ver = metadata.version("stegoforge")
    except metadata.PackageNotFoundError:
        tool_ver = "unknown"
    components = []
    for dist in sorted(metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = dist.metadata["Name"] or "unknown"
        if name.lower() == "stegoforge":
            continue
        components.append({
            "type": "library",
            "bom-ref": f"{name}@{dist.version}",
            "name": name,
            "version": dist.version,
        })
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "component": {"type": "application", "name": "stegoforge", "version": tool_ver},
            "tools": [{"name": "scripts/make_sbom.py"}],
        },
        "components": components,
    }
    print(json.dumps(sbom, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
