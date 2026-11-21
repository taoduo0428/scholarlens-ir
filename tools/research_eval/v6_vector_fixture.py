"""Validate legacy vector cases on a disposable copy of a stopped local ES test fixture."""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from uuid import uuid4

from tools.research_eval.v6_legacy import ROOT


def signature(folder):
    return sorted((f.relative_to(folder).as_posix(), f.stat().st_size, f.stat().st_mtime_ns)
                  for f in folder.rglob("*") if f.is_file())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--es-home", type=Path, required=True)
    parser.add_argument("--offline-fixture", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("native", ROOT/"tools/audit/run-upload-integration.py")
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    source = args.offline_fixture.resolve(strict=True)
    expected = ROOT/"infra/.runtime/elasticsearch-8.19.23/data"
    if source != expected.resolve(strict=True) or native.listening(9200):
        raise ValueError("expected stopped local test fixture")
    nonce = uuid4().hex[:12]
    out = ROOT/"output/v6"/("vector-fixture-"+nonce)
    out.mkdir(exist_ok=False)
    before = signature(source)
    if any(f.is_symlink() for f in source.rglob("*")):
        raise ValueError("fixture contains links")
    shutil.copytree(source, out/"data")
    if before != signature(source):
        raise RuntimeError("source changed during copy")
    home = args.es_home.resolve(strict=True)
    config = out/"config"
    shutil.copytree(home/"config",config)
    for name in ("logs","tmp"):
        (out/name).mkdir()
    port, other = native.free_port(),native.free_port()
    while other == port:
        other=native.free_port()
    name="scholarlens-acceptance-"+nonce
    values={"cluster.name":name,"node.name":name,"path.data":str(out/"data"),"path.logs":str(out/"logs"),
            "network.host":"127.0.0.1","http.port":port,"transport.port":other,"discovery.type":"single-node",
            "xpack.security.enabled":False,"xpack.security.autoconfiguration.enabled":False,"xpack.ml.enabled":False,
            "ingest.geoip.downloader.enabled":False}
    (config/"elasticsearch.yml").write_text("".join(k+": "+json.dumps(v)+"\n" for k,v in values.items()),encoding="utf8")
    env=native.isolated_environment(out,config,home,ROOT/"backend/.runtime/minilm",port,other,nonce)
    env.update(ELASTICSEARCH_INDEX="scholarlens-papers-real",VECTOR_INDEX="scholarlens-vectors-real")
    url=env["ELASTICSEARCH_URL"]
    result={"tests_exit":None,"scope":"offline copied fixture","source_unchanged":None}
    print(out.name,flush=True)
    with (out/"server.log").open("w",encoding="utf8") as log:
        proc=subprocess.Popen(native.java_command(home,config),cwd=home,env=env,stdin=subprocess.PIPE,
                              stdout=log,stderr=log,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        try:
            deadline=time.monotonic()+150
            while True:
                try:
                    info=native.get_json(url)
                    break
                except (URLError,TimeoutError,ConnectionError):
                    if time.monotonic()>deadline or proc.poll() is not None:
                        raise RuntimeError("fixture unavailable")
                    time.sleep(.5)
            assert info["cluster_name"]==name and info["version"]["number"]=="8.19.23"
            node=next(iter(native.get_json(url+"/_nodes/_local/settings?flat_settings=true")["nodes"].values()))
            actual=node["settings"]["path.data"]
            assert Path(actual[0] if isinstance(actual,list) else actual).resolve()==out/"data"
            from elasticsearch import Elasticsearch
            with Elasticsearch(url,request_timeout=60) as es:
                es.cluster.put_settings(persistent={"cluster.routing.allocation.disk.watermark."+k:v
                                        for k,v in (("low","4gb"),("high","3gb"),("flood_stage","2gb"))})
                es.cluster.health(wait_for_status="yellow",timeout="70s")
                result["papers"]=es.count(index=env["ELASTICSEARCH_INDEX"])["count"]
                result["vectors"]=es.count(index=env["VECTOR_INDEX"])["count"]
                assert result["papers"]==859 and result["vectors"]>859
            code="""import os,sys,pytest
from elasticsearch import Elasticsearch
from unittest.mock import patch
original=Elasticsearch.__init__
def connect(client,hosts=None,*args,**kwargs):
    return original(client,os.environ['ELASTICSEARCH_URL'] if hosts=='http://127.0.0.1:9200' else hosts,*args,**kwargs)
with patch.object(Elasticsearch,'__init__',connect):
    sys.exit(pytest.main(sys.argv[1:]))"""
            with (out/"tests.log").open("w",encoding="utf8") as tests:
                result["tests_exit"]=native.run_tests([sys.executable,"-c",code,"-q","--tb=short",
                    "backend/tests/test_v2_vectors.py","backend/tests/test_v21.py::test_upload_vectorization_is_independent",
                    "--basetemp="+str(out/"pytest-runtime"),"--junitxml="+str(out/"junit.xml")],env,tests,timeout=480)
        finally:
            native.stop_owned(proc,port,other)
            result.update(source_unchanged=before==signature(source),ports_closed=not native.listening(port) and not native.listening(other))
            (out/"result.json").write_text(json.dumps(result),encoding="utf8")
            print(json.dumps(result), flush=True)
    return 0 if result["tests_exit"]==0 and result["source_unchanged"] and result["ports_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
