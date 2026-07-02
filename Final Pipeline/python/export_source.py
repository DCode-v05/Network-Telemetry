"""Embed the detector source (Python + C) for the dashboard's code viewer.

Writes dashboard/public/data/source.json so the Source page can show the actual
`unified` implementation and let the user toggle Python vs C. Reads the real
files so the viewer never drifts from what runs.

Run:  python export_source.py     (from Final Pipeline/python)
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.normpath(os.path.join(ROOT, "dashboard", "public", "data", "source.json"))

FILES = {
    "python": [
        ("unified_detector.py", "python", os.path.join(ROOT, "python", "unified_detector.py")),
    ],
    "c": [
        ("unified.h", "c", os.path.join(ROOT, "c", "unified.h")),
        ("unified.c", "c", os.path.join(ROOT, "c", "unified.c")),
    ],
    "js": [
        ("unified.js", "javascript", os.path.join(ROOT, "dashboard", "src", "lib", "unified.js")),
    ],
}


def main():
    doc = {}
    for lang, files in FILES.items():
        doc[lang] = []
        for name, hl, path in files:
            code = open(path, encoding="utf-8").read() if os.path.exists(path) else f"// missing: {path}"
            doc[lang].append({"name": name, "lang": hl, "loc": code.count("\n") + 1, "code": code})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}")
    for lang, files in doc.items():
        print(f"  {lang}: " + ", ".join(f"{f['name']} ({f['loc']} loc)" for f in files))


if __name__ == "__main__":
    main()
