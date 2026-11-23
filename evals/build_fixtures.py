"""Build the offline tool corpus. No imports or calls to network clients."""

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "fixtures"
LIVE = FIXTURES / "live-2026-11-22"
SYNTHETIC = FIXTURES / "synthetic"
MERGED = HERE / "fixtures-merged"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build():
    manifest = read(LIVE / "manifest.json")
    requests = {}
    for folder in (LIVE, SYNTHETIC):
        for key, entry in read(folder / "manifest.json")["requests"].items():
            # Namespace copies so overriding one key cannot change another key's file.
            source = folder / entry["file"]
            dest = MERGED / folder.name / entry["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            requests[key] = dict(entry, file=dest.relative_to(MERGED).as_posix())
    manifest.update(
        note="Offline eval corpus with labelled synthetic examples.", requests=requests
    )
    write(MERGED / "manifest.json", manifest)
    return MERGED


if __name__ == "__main__":
    print(build())
