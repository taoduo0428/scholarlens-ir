"""Check page-eight formula mentions in the authenticated ScholarLens workbench."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time


def browser_check(origin, chrome, record):
    from playwright.sync_api import sync_playwright

    assert origin.startswith("http://127.0.0.1:")
    expected = json.loads(record.read_bytes())
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True, executable_path=chrome)
        context = browser.new_context()
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort())
        credentials = {"username": "formula-" + secrets.token_hex(8), "password": secrets.token_hex(20)}
        assert context.request.post(origin + "/api/auth/register", data=credentials).status == 201
        login = context.request.post(origin + "/api/auth/login", data=credentials)
        assert login.status == 200
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda _: errors.append("script error"))
        page.goto(origin + "/research")
        page.evaluate("(value) => sessionStorage.setItem('scholarlens-session',value)", login.json()["access_token"])
        page.reload()
        page.get_by_text("本库论文范围", exact=True).click()
        page.get_by_label("限定论文 ID").fill("figure-eval-paper")
        page.get_by_text("引用 PDF 表格单元格（可选）", exact=True).click()
        def read_page(n):
            page.get_by_label("PDF 页码").fill(str(n))
            target = origin + f"/api/papers/figure-eval-paper/pdf/layout/{n}"
            with page.expect_response(lambda r: r.url == target) as pending:
                page.get_by_role("button", name="读取本页表格").click()
            return pending.value
        result = read_page(8)
        assert result.status == 200
        layout = result.json()
        assert layout["source_version"] == expected["pdf_sha256"]
        visible = []
        for ref in expected["mentions"]:
            source = ref["product_source"]
            label = f"第 8 页正文引用 {source['quote']}"
            toggle = page.get_by_text(label, exact=True)
            toggle.click()
            panel = toggle.locator("..")
            panel.get_by_text(source["locator"], exact=True).wait_for(state="visible")
            assert "本页公式位置" not in panel.inner_text()
            visible.append(label)
        missing = read_page(499)
        assert missing.status == 422
        page.get_by_text(missing.json()["error"]["message"], exact=True).wait_for(state="visible")
        for label in visible:
            assert page.get_by_text(label, exact=True).count() == 0
        assert not errors
        return {"browser": browser.version, "scope": "one catalogue fixture row; normal application and layout route",
                "pdf_sha256": layout["source_version"], "http_status": result.status, "expanded_mentions": visible,
                "visible_source_locations": len(visible), "unresolved_same_page_links": len(visible),
                "unavailable_page_status": missing.status, "stale_mentions_after_error": 0, "page_errors": len(errors)}


def verify(args):
    import uvicorn
    from tools.research_eval.v7_figure_legend_browser import PaperCatalogue
    from tools.research_eval.v7_pdf import PDF_HASH

    pdf = args.pdf.resolve(strict=True)
    assert sha256(pdf.read_bytes()).hexdigest() == PDF_HASH
    assert (args.dist / "index.html").is_file()
    with TemporaryDirectory() as runtime, socket.socket() as sock:
        os.environ.update(SCHOLARLENS_RUNTIME_DIR=runtime, SCHOLARLENS_RESEARCH_ENABLED="true")
        from backend.app1 import create_app
        from backend.config import Settings
        settings = Settings(runtime_dir=runtime, index="legend-eval", pdf_root=str(pdf.parent),
                            pdf_path_base=str(pdf.parent), frontend_dir=str(args.dist.resolve()))
        app = create_app(settings, client=PaperCatalogue(pdf.name))
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 20
            while not server.started:
                if time.monotonic() > deadline:
                    raise TimeoutError("fixture API did not start")
                time.sleep(.05)
            url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            output = subprocess.check_output([args.browser_python, __file__, "client", url, args.chrome,
                                              str(args.record.resolve())], env=env, timeout=120, encoding="utf8")
            result = json.loads(output)
            with args.output.open("x", encoding="utf8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        finally:
            server.should_exit = True
            thread.join(timeout=15)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "client":
        print(json.dumps(browser_check(sys.argv[2], sys.argv[3], Path(sys.argv[4]))))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        for name in ("pdf", "dist", "record"):
            parser.add_argument(name, type=Path)
        parser.add_argument("--browser-python", default=sys.executable)
        parser.add_argument("--chrome", required=True)
        parser.add_argument("--output", required=True, type=Path)
        verify(parser.parse_args())
