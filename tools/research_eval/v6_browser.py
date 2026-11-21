"""Test both browser journeys against an isolated published demo and fixture lab."""
import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--fixture-lab", type=Path, required=True)
    cli.add_argument("--dist", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--e11", action="store_true", help="Verify the per-paper profile journey on E11")
    args = cli.parse_args()
    if not (args.dist / "index.html").is_file():
        cli.error("Build the demo frontend first")
    source = args.fixture_lab.resolve(strict=True)
    out = args.output.resolve() / ("ui-" + uuid4().hex[:12])
    out.mkdir(parents=True, exist_ok=False)
    local_copy = out / "lab.sqlite3"
    with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as src, closing(sqlite3.connect(local_copy)) as dest:
        src.backup(dest)
    runtime = str(out / "runtime")
    env = {**os.environ, "PYTHONUTF8": "1", "SCHOLARLENS_E10_ENABLED":"true", "SCHOLARLENS_TEST_E91":"true",
           "SCHOLARLENS_RESEARCH_ENABLED":"true", "SCHOLARLENS_EVOLUTION_LAB":"true",
           "SCHOLARLENS_TEST_RUNTIME":runtime, "SCHOLARLENS_LAB_DB":str(local_copy),
           "SCHOLARLENS_PYTHON":sys.executable, "SCHOLARLENS_RESEARCH_OUTPUT":str(out/"captures")}
    if args.e11:
        env["SCHOLARLENS_E11_ENABLED"] = "true"
    with (out/"server.log").open("w", encoding="utf8") as errors:
        proc = subprocess.Popen([sys.executable,"-u","-m","tools.research_demo","--runtime",runtime,
                                 "--frontend",str(args.dist.resolve()),"--port","0","--corpus",
                                 "profile-fixture" if args.e11 else "fixture"],
                                env=env,stdout=subprocess.PIPE,stderr=errors,text=True,encoding="utf8")
        try:
            url = re.search(r"http://127\.0\.0\.1:\d+", proc.stdout.readline())
            if not url:
                raise RuntimeError("fixture_service_unavailable")
            env["SCHOLARLENS_URL"] = url[0]
            journeys = ("e11-profile-live",) if args.e11 else ("e9-field-release", "workspace-v4-live")
            for name in journeys:
                with (out/(name+".log")).open("w",encoding="utf8") as log:
                    subprocess.run([shutil.which("node") or "node","frontend/tests/"+name+".mjs"],env=env,
                                   stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
                print(name,"PASS",flush=True)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=15)


if __name__ == "__main__":
    main()
