#!/usr/bin/env python3
"""Exploratory stress test of PauseCheck on a small public constructed set.

The script fetches NaijaScamBench v0 at a pinned Hugging Face revision and
processes the CSV in memory. It deliberately excludes rows sourced from the
UCI SMS Spam Collection because UCI is the model's training source. It sends
only public benchmark examples to a local browser instance and writes aggregate
metrics only; it never writes raw message text or individual predictions.

This is not a real-world Nigerian validation study. See LOCAL_PILOT.md.
"""
from __future__ import annotations

import collections
import csv
import hashlib
import io
import json
import math
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATASET_REVISION = "558fcb62602b8421733381fbfedcc61167398d12"
DATASET_URL = (
    "https://huggingface.co/datasets/Eterniti/NaijaScamBench/resolve/"
    f"{DATASET_REVISION}/naijascambench_v0.csv"
)
EXPECTED_SHA256 = "bac021051086d464385b01cce874bbf249610d44a5bd21e359fd48fb39711a9d"
EXPECTED_ALL_ROWS = 180
EXPECTED_CONSTRUCTED_ROWS = 135
REPORT_PATH = ROOT / "LOCAL_PILOT_EVALUATION.json"


def available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fetch_rows() -> tuple[list[dict[str, str]], str]:
    request = urllib.request.Request(
        DATASET_URL,
        headers={"User-Agent": "PauseCheck-private-exploratory-test/1.0"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(
            "Pinned benchmark CSV checksum changed; stop and review the dataset "
            "revision before using it."
        )
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    if len(rows) != EXPECTED_ALL_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ALL_ROWS} rows, found {len(rows)}")
    if not rows or not {"text", "label", "language", "source"}.issubset(rows[0]):
        raise RuntimeError("Dataset schema changed; stop and review before use")
    return rows, digest


def run_local_app(examples: list[dict[str, str]]) -> dict:
    port = available_port()
    origin = f"http://127.0.0.1:{port}/"
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(port),
            "--bind",
            "127.0.0.1",
            "--directory",
            str(ROOT),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Local app server did not start")

        outcomes: list[tuple[dict[str, str], bool]] = []
        with sync_playwright() as p:
            chromium = Path("/usr/bin/chromium")
            browser = p.chromium.launch(
                executable_path=str(chromium) if chromium.exists() else None,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            external_requests: list[str] = []
            page.on(
                "request",
                lambda request: external_requests.append(request.url)
                if not request.url.startswith(origin)
                else None,
            )
            page.goto(origin + "index.html", wait_until="networkidle")
            page.locator("#modelStatus.ready").wait_for(state="visible", timeout=10000)
            for row in examples:
                page.locator("#messageInput").fill(row["text"])
                page.locator("#checkButton").click()
                page.locator("#scanResult").wait_for(state="visible")
                classes = (page.locator("#resultLabel").get_attribute("class") or "").split()
                outcomes.append((row, "warn" in classes))
            browser.close()
        if external_requests:
            raise RuntimeError("Unexpected off-origin app requests were observed")
        return summarize(outcomes)
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()


def summarize(outcomes: list[tuple[dict[str, str], bool]]) -> dict:
    confusion = collections.Counter()
    language_counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row, predicted_scam in outcomes:
        actual_scam = row["label"].strip().lower() == "scam"
        key = ("scam" if actual_scam else "legit", "scam" if predicted_scam else "legit")
        confusion[key] += 1
        language_counts[row["language"].strip().lower()]["scam" if actual_scam else "legit"] += 1

    tp = confusion["scam", "scam"]
    fp = confusion["legit", "scam"]
    tn = confusion["legit", "legit"]
    fn = confusion["scam", "legit"]
    n = len(outcomes)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "n": n,
        "matchedLabels": tp + tn,
        "accuracy": round((tp + tn) / n, 6) if n else None,
        "spamPrecision": round(precision, 6),
        "spamRecall": round(recall, 6),
        "specificity": round(specificity, 6),
        "spamF1": round(f1, 6),
        "confusion": {
            "truePositive": tp,
            "falsePositive": fp,
            "trueNegative": tn,
            "falseNegative": fn,
        },
        "constructedLanguageLabelCounts": {
            lang: dict(sorted(counts.items()))
            for lang, counts in sorted(language_counts.items())
        },
    }


def main() -> None:
    all_rows, digest = fetch_rows()
    constructed = [row for row in all_rows if row["source"].strip().lower() == "constructed"]
    excluded = [row for row in all_rows if row not in constructed]
    if len(constructed) != EXPECTED_CONSTRUCTED_ROWS:
        raise RuntimeError(
            f"Expected {EXPECTED_CONSTRUCTED_ROWS} constructed examples, found {len(constructed)}"
        )
    if len(excluded) != EXPECTED_ALL_ROWS - EXPECTED_CONSTRUCTED_ROWS:
        raise RuntimeError("Unexpected non-constructed rows; stop and review dataset source labels")
    if any(row["label"].strip().lower() not in {"scam", "legit"} for row in constructed):
        raise RuntimeError("Unexpected label; stop and review the benchmark schema")

    results = run_local_app(constructed)
    report = {
        "title": "NaijaScamBench v0 constructed-example exploratory stress test",
        "dataset": "Eterniti/Xvimo team, NaijaScamBench v0",
        "datasetCard": "https://huggingface.co/datasets/Eterniti/NaijaScamBench",
        "datasetLicense": "CC BY 4.0",
        "datasetRevision": DATASET_REVISION,
        "datasetFile": "naijascambench_v0.csv",
        "datasetFileSha256": digest,
        "allDatasetRows": len(all_rows),
        "excludedUciSourcedRows": len(excluded),
        "excludedRowsReason": "The model was trained on the UCI SMS Spam Collection; these UCI-sourced rows are excluded to avoid overlap.",
        "constructedExamplesEvaluated": len(constructed),
        "constructedExampleLabelCounts": {
            "scam": sum(row["label"].strip().lower() == "scam" for row in constructed),
            "legit": sum(row["label"].strip().lower() == "legit" for row in constructed),
        },
        "evaluation": "Frozen model as delivered by the local app; predictions read from the browser UI; no retraining or threshold adjustment.",
        "results": results,
        "limitations": [
            "This is a small constructed-example stress test, not real-world Nigerian validation.",
            "The dataset card says most evaluated examples were constructed by the Xvimo team and that local-language examples have not been reviewed by native speakers.",
            "Language groups are too small to support language-specific performance claims.",
            "The test does not assess the separate rule-based warning flags, user behavior, or protection from financial loss.",
            "Do not use these results as a real-world estimate or safety guarantee.",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Aggregate report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
