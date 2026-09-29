import socket
import subprocess
import sys
import time
import re
from typing import Iterator
from urllib.request import urlopen
from pathlib import Path

import pytest
from playwright.sync_api import Page


@pytest.fixture(autouse=True)
def capture_failure_artifacts(page: Page, request: pytest.FixtureRequest) -> Iterator[None]:
    failed_requests = []
    page.on("requestfailed", lambda failed: failed_requests.append({
        "url": failed.url,
        "method": failed.method,
        "error": failed.failure or "request failed",
    }))
    page.context.tracing.start(screenshots=True, snapshots=True, sources=True)
    yield

    call_report = getattr(request.node, "rep_call", None)
    failure_record = getattr(request.node, "_investigator_failure_record", None)
    if call_report is not None and call_report.failed and failure_record is not None:
        artifact_dir = Path("artifacts") / "browser"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)
        screenshot_path = artifact_dir / (safe_name + ".png")
        trace_path = artifact_dir / (safe_name + ".zip")
        page.screenshot(path=str(screenshot_path), full_page=True)
        page.context.tracing.stop(path=str(trace_path))
        browser = page.context.browser
        failure_record["browser"] = browser.browser_type.name if browser else "unknown"
        failure_record["screenshot"] = screenshot_path.as_posix()
        failure_record["trace"] = trace_path.as_posix()
        failure_record["network_errors"] = failed_requests
    else:
        page.context.tracing.stop()


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    with socket.socket() as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        port = server_socket.getsockname()[1]

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = "http://127.0.0.1:{}".format(port)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("uvicorn exited before becoming ready")
        try:
            with urlopen(url + "/api/health", timeout=0.5) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("uvicorn did not become ready")

    yield url
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
