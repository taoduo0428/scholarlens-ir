"""Match a pinned application-image scan to Debian 13's per-advisory package records."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
from urllib.request import urlopen

from tools.research_eval.inputs import ROOT


def lookup(cve):
    if not re.fullmatch(r"CVE-\d{4}-\d{4,8}", cve):
        raise ValueError("invalid advisory identifier")
    url = "https://security-tracker.debian.org/tracker/" + cve
    with urlopen(url, timeout=15) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000 or response.url != url:
            raise ValueError("unexpected tracker response")
    source = None
    records = []
    for table in re.findall(r"<table\b[^>]*>(.*?)</table>", body.decode("utf8"), re.S):
        if "<th>Source Package</th><th>Release</th><th>Version</th><th>Status</th>" not in table:
            continue
        for tr in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.S)
            if len(cells) != 4:
                continue
            if cells[0]:
                package = re.search(r'href="/tracker/source-package/([\w.+-]+)"', cells[0])
                source = package[1] if package else None
            channel, version, status = (unescape(re.sub(r"<[^>]+>", "", s)).strip() for s in cells[1:])
            if source:
                records.extend(dict(source=source, channel=name, version=version, status=status)
                               for name in channel.split(", ") if name in {"trixie", "trixie (security)"})
    return cve, dict(url=url, html_sha256=sha256(body).hexdigest(), packages=records)


def evaluate(scan):
    input_record = json.loads((ROOT / "docs/agent-v7/container-acceptance.json").read_bytes())
    recorded = input_record["advisories"]["updated_trixie"]
    raw = scan.read_bytes()
    data = json.loads(raw)
    if (sha256(raw).hexdigest() != recorded["report_sha256"] or data["source"]["target"]["imageID"]
            != input_record["candidate_image"]):
        raise ValueError("image or scan identity mismatch")
    high = [m for m in data["matches"] if m["vulnerability"]["severity"] == "High"]
    if len(high) != len(recorded["high_findings"]):
        raise ValueError("published scan mismatch")
    with ThreadPoolExecutor(max_workers=3) as pool:
        debian = dict(pool.map(lookup, sorted({m["vulnerability"]["id"] for m in high})))
    rows = []
    # Binary catalogers may omit the Debian revision. Bind the Debian source
    # version through the actual dpkg package of the same name in this scan.
    installed = {m["artifact"]["name"]: m["artifact"] for m in data["matches"] if m["artifact"]["type"] == "deb"}
    for match in high:
        a, v = match["artifact"], match["vulnerability"]
        package = installed.get(a["name"])
        src = ((package.get("upstreams") or [{}])[0].get("name") or package["name"]) if package else a["name"]
        version = (package.get("upstreams") or [{}])[0].get("version") if package else None
        version = version or (package["version"] if package else None)
        releases = [r for r in debian[v["id"]]["packages"] if r["source"] == src]
        exact = {r["status"] for r in releases if r["version"] == version}
        if exact == {"fixed"}:
            status = "installed_version_marked_fixed"
        elif "vulnerable" in exact:
            status = "installed_version_marked_vulnerable"
        elif exact:
            status = "other_exact_status"
        else:
            status = "no_exact_version_record"
        rows.append(dict(advisory=v["id"], package=a["name"], kind=a["type"], detected_version=a["version"],
                         source=src, installed_debian_version=version, scanner_fix=v["fix"]["state"],
                         debian_status=status, release_has_fixed_record=any(r["status"] == "fixed" for r in releases)))
    return dict(checked_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                image=input_record["candidate_image"], scan_sha256=recorded["report_sha256"],
                scan_db_built=recorded["db_built"], high=len(rows), unique_advisories=len(debian),
                exact_status=dict(Counter(r["debian_status"] for r in rows)), rows=rows, tracker=debian)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("scan", type=Path)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    report = evaluate(args.scan)
    with args.output.open("x", encoding="utf8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(report["high"], report["unique_advisories"], report["exact_status"])
