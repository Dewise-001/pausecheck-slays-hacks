#!/usr/bin/env python3
"""End-to-end smoke checks for the standalone PauseCheck prototype."""
from pathlib import Path
import socket
import subprocess
import sys
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "screenshots"
SHOTS.mkdir(exist_ok=True)
SUSPICIOUS = "URGENT: Your ₦50,000 support grant has been approved. Confirm your BVN and OTP now at http://cbn-grants.example/verify before midnight."


def available_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    port = available_port()
    origin = f"http://127.0.0.1:{port}/"
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("Local app server did not start")

        errors, external_requests = [], []
        with sync_playwright() as p:
            chromium = Path("/usr/bin/chromium")
            browser = p.chromium.launch(
                executable_path=str(chromium) if chromium.exists() else None,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: external_requests.append(request.url) if not request.url.startswith(origin) else None)
            page.goto(origin + "index.html", wait_until="networkidle")
            page.locator("#modelStatus.ready").wait_for(state="visible", timeout=10000)
            assert page.title() == "PauseCheck — stop, check, verify"
            assert page.locator("#emptyResult").is_visible()
            assert page.locator('link[rel="manifest"]').get_attribute("href") == "./manifest.webmanifest"

            # A protective reminder must not be mistaken for an OTP solicitation.
            page.locator("#messageInput").fill("Safety reminder: Please never share your OTP or password with anyone.")
            page.locator("#checkButton").click()
            assert "sensitive code" not in page.locator("#warningFlags").inner_text().lower()

            # A direct sensitive-code request is flagged; the example is conspicuously fictional.
            page.locator('[data-sample="grant"]').click()
            page.locator("#scanResult").wait_for(state="visible")
            assert page.locator("#sampleNote").is_visible()
            assert "FICTIONAL EXAMPLE" in page.locator("#sampleNote").inner_text()
            assert "link or web address" in page.locator("#warningFlags").inner_text().lower()
            assert "sensitive code" in page.locator("#warningFlags").inner_text().lower()
            assert page.locator("#resultTitle").inner_text()

            # Ordinary messages are not declared safe; the disclaimer remains present.
            page.locator('[data-sample="ordinary"]').click()
            assert "not mean the message is safe" in page.locator(".result-disclaimer").inner_text().lower()

            # User-supplied markup is treated as text and is not persisted across reloads.
            hostile = '<img src=x onerror="window.__pwned=1"> urgent account verify now'
            page.locator("#messageInput").fill(hostile)
            page.locator("#checkButton").click()
            assert page.locator("#messageInput").input_value() == hostile
            assert page.locator("img[src=x]").count() == 0
            assert page.evaluate("window.__pwned || false") is False
            page.reload(wait_until="networkidle")
            page.locator("#modelStatus.ready").wait_for(state="visible")
            assert page.locator("#messageInput").input_value() == ""

            # Once the local static shell/model has been cached, a reload and scan work offline.
            page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null", timeout=10000)
            context.set_offline(True)
            page.reload(wait_until="domcontentloaded", timeout=15000)
            page.locator("#modelStatus.ready").wait_for(state="visible", timeout=10000)
            page.locator('[data-sample="grant"]').click()
            assert "sensitive code" in page.locator("#warningFlags").inner_text().lower()
            context.set_offline(False)
            page.screenshot(path=str(SHOTS / "pausecheck-screening-example-desktop.png"), full_page=True)
            model_card = page.locator(".model-details")
            model_card.locator("summary").click()
            model_card_text = model_card.inner_text().lower()
            assert "52.6%" in model_card_text
            assert "not validation" in model_card_text
            assert "should not rely on this model" in model_card_text
            model_card.screenshot(path=str(SHOTS / "pausecheck-model-card-pilot-desktop.png"))

            # Responsive layout fits a phone-width viewport.
            mobile = context.new_page()
            mobile.set_viewport_size({"width": 390, "height": 844})
            mobile.on("pageerror", lambda error: errors.append(str(error)))
            mobile.goto(origin + "index.html", wait_until="networkidle")
            mobile.locator("#modelStatus.ready").wait_for(state="visible")
            mobile.locator('[data-sample="grant"]').click()
            assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            mobile.screenshot(path=str(SHOTS / "pausecheck-screening-example-mobile.png"), full_page=True)

            assert not errors, "Browser errors: " + " | ".join(errors)
            assert not external_requests, "Unexpected off-origin requests: " + " | ".join(external_requests)
            browser.close()
        print("PASS: local model, fictional label, positive and negated OTP checks, offline reload, safe rendering, non-persistence, no off-origin requests, responsive mobile layout")
        print(f"Screenshots: {SHOTS / 'pausecheck-screening-example-desktop.png'}; {SHOTS / 'pausecheck-screening-example-mobile.png'}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
