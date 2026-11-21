"""Check the frozen benchmark file bytes against the pre-development Git blobs."""
import subprocess
from pathlib import Path

BASE = "5dd0cbce22635c891e704aba851733cc67869dbf"


def main():
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASE, "agent/benchmarks"], text=True).splitlines()
    assert paths
    current = sorted(p.as_posix() for p in Path("agent/benchmarks").rglob("*") if p.is_file())
    if sorted(paths) != current:
        raise ValueError("benchmark file set has changed")
    for path in paths:
        frozen = subprocess.check_output(["git", "rev-parse", f"{BASE}:{path}"]).strip()
        materialized = subprocess.check_output(["git", "hash-object", "--path", path, "--", path]).strip()
        if frozen != materialized:
            raise ValueError("frozen benchmark mismatch: " + path)
    print(len(paths), "frozen files verified")


if __name__ == "__main__":
    main()
