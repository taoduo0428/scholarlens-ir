"""A real application on a reserved loopback socket for delivered-data acceptance."""
from contextlib import contextmanager
import os
from pathlib import Path
import socket
from threading import Thread
import time
from unittest.mock import patch


@contextmanager
def delivery_api(root, config):
    if "delivery" not in config:
        yield []
        return
    import uvicorn
    from backend.app1 import create_app
    from backend.config import Settings

    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8002)) == 0:
            raise RuntimeError("restart test requires free loopback port 8002")
    launcher = root/"restart-control"
    launcher.mkdir(exist_ok=False)
    values = {"SCHOLARLENS_LAUNCHER_DIR":str(launcher), "EVO_TEST_LOOPBACK_ES":"1"}
    with patch.dict(os.environ, values), socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        addr = "http://127.0.0.1:" + str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(create_app(Settings.from_env()), log_level="error", log_config=None))
        thread = Thread(target=server.run, kwargs={"sockets":[sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+20
            while not server.started:
                if not thread.is_alive() or time.monotonic()>deadline:
                    raise RuntimeError("isolated delivery api startup failed")
                time.sleep(.05)
            yield ["--real-data-dir="+str(Path(config["delivery"]).resolve(strict=True)), "--real-api="+addr]
        finally:
            server.should_exit = True
            thread.join(timeout=20)
            if thread.is_alive():
                raise RuntimeError("isolated delivery api did not stop")
