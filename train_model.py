#!/usr/bin/env python3
"""Train PauseCheck's transparent multinomial Naive Bayes SMS pattern model.

Only the licensed public UCI corpus is downloaded. The raw messages are not
written into the application bundle or project tree; only model parameters and
aggregate evaluation statistics are exported.
"""
from __future__ import annotations
import collections
import json
import math
import random
import re
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "model.json"
REPORT_PATH = ROOT / "model-evaluation.json"
DATA_URL = "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip"
DATA_CITATION = "Almeida, T. & Hidalgo, J. (2011). SMS Spam Collection [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CC84."
LICENSE = "CC BY 4.0"
TOKEN_RE = re.compile(r"\w+", re.UNICODE)
MAX_FEATURES = 12000
MIN_DOCUMENT_FREQUENCY = 2
ALPHA = 0.5
SEED = 2026


def fetch_messages() -> list[tuple[str, str]]:
    request = urllib.request.Request(DATA_URL, headers={"User-Agent": "PauseCheck-local-model-training/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read()
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
        filename = next((name for name in names if name.endswith("SMSSpamCollection")), None)
        if not filename:
            raise RuntimeError("UCI archive did not contain SMSSpamCollection")
        raw = archive.read(filename).decode("utf-8", errors="replace")
    rows: list[tuple[str, str]] = []
    for line in raw.splitlines():
        label, sep, text = line.partition("\t")
        label = label.strip().lower()
        text = text.strip()
        if sep and text and label in {"ham", "spam"}:
            rows.append((label, text))
    if not rows:
        raise RuntimeError("No labeled rows found in UCI dataset")
    return rows


def tokens(text: str) -> list[str]:
    words = TOKEN_RE.findall(text.lower())
    return words + [words[i] + " " + words[i + 1] for i in range(len(words) - 1)]


def deduplicate_messages(rows: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], int]:
    # Model tokenization is case-insensitive, so normalize case and whitespace
    # before grouping to prevent equivalent texts leaking across data splits.
    groups: dict[str, tuple[str, str]] = {}
    conflicts: set[str] = set()
    for label, text in rows:
        normalized = " ".join(text.split())
        key = normalized.casefold()
        if key in conflicts:
            continue
        previous = groups.get(key)
        if previous and previous[0] != label:
            conflicts.add(key)
            groups.pop(key, None)
            continue
        groups.setdefault(key, (label, normalized))
    return list(groups.values()), len(conflicts)


def stratified_split(rows: list[tuple[str, str]]) -> tuple[list, list, list]:
    rng = random.Random(SEED)
    buckets = {label: [] for label in ("ham", "spam")}
    for row in rows:
        buckets[row[0]].append(row)
    train, validation, test = [], [], []
    for label in ("ham", "spam"):
        group = buckets[label][:]
        rng.shuffle(group)
        train_end = int(len(group) * 0.70)
        validation_end = train_end + int(len(group) * 0.15)
        train.extend(group[:train_end])
        validation.extend(group[train_end:validation_end])
        test.extend(group[validation_end:])
    rng.shuffle(train)
    rng.shuffle(validation)
    rng.shuffle(test)
    return train, validation, test


def build_vocabulary(rows: list[tuple[str, str]]) -> list[str]:
    document_frequency: collections.Counter[str] = collections.Counter()
    for _, text in rows:
        document_frequency.update(set(tokens(text)))
    candidates = [(term, df) for term, df in document_frequency.items() if df >= MIN_DOCUMENT_FREQUENCY]
    candidates.sort(key=lambda item: (-item[1], item[0]))
    return [term for term, _ in candidates[:MAX_FEATURES]]


def fit(rows: list[tuple[str, str]], vocabulary: list[str]) -> tuple[float, dict[str, float], dict]:
    vocab = set(vocabulary)
    term_counts = {label: collections.Counter() for label in ("ham", "spam")}
    token_totals = {label: 0 for label in ("ham", "spam")}
    document_totals = collections.Counter()
    for label, text in rows:
        document_totals[label] += 1
        counts = collections.Counter(term for term in tokens(text) if term in vocab)
        term_counts[label].update(counts)
        token_totals[label] += sum(counts.values())
    if not document_totals["ham"] or not document_totals["spam"]:
        raise RuntimeError("Training split must contain both classes")
    weights: dict[str, float] = {}
    for term in vocabulary:
        p_spam = (term_counts["spam"][term] + ALPHA) / (token_totals["spam"] + ALPHA * len(vocabulary))
        p_ham = (term_counts["ham"][term] + ALPHA) / (token_totals["ham"] + ALPHA * len(vocabulary))
        weights[term] = math.log(p_spam) - math.log(p_ham)
    intercept = math.log(document_totals["spam"] / document_totals["ham"])
    return intercept, weights, {"documents": dict(document_totals), "tokenTotals": token_totals}


def score_text(text: str, intercept: float, weights: dict[str, float]) -> float:
    counts = collections.Counter(term for term in tokens(text) if term in weights)
    return intercept + sum(count * weights[term] for term, count in counts.items())


def metrics(rows: list[tuple[str, str]], scores: list[float], threshold: float) -> dict:
    tp = fp = tn = fn = 0
    for (label, _), score in zip(rows, scores):
        predicted_spam = score >= threshold
        actual_spam = label == "spam"
        if predicted_spam and actual_spam: tp += 1
        elif predicted_spam and not actual_spam: fp += 1
        elif not predicted_spam and actual_spam: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "samples": len(rows), "threshold": round(threshold, 6),
        "accuracy": round((tp + tn) / max(1, len(rows)), 6),
        "precision": round(precision, 6), "recall": round(recall, 6),
        "specificity": round(specificity, 6), "f1": round(f1, 6),
        "confusion": {"truePositive": tp, "falsePositive": fp, "trueNegative": tn, "falseNegative": fn}
    }


def choose_threshold(rows: list[tuple[str, str]], scores: list[float]) -> float:
    candidates = sorted({-20.0, 0.0, 20.0, *scores})
    best_threshold, best_key = 0.0, (-1.0, -1.0, -1.0)
    for threshold in candidates:
        m = metrics(rows, scores, threshold)
        key = (m["f1"], m["precision"], m["specificity"])
        if key > best_key:
            best_key = key
            best_threshold = threshold
    return best_threshold


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * fraction)
    return ordered[index]


def main() -> None:
    messages = fetch_messages()
    # Group case-insensitive normalized text before splitting; drop any text
    # that has contradictory labels instead of letting it leak across splits.
    deduplicated, conflicting_text_groups_removed = deduplicate_messages(messages)
    train, validation, test = stratified_split(deduplicated)
    vocabulary = build_vocabulary(train)
    intercept, weights, counts = fit(train, vocabulary)
    validation_scores = [score_text(text, intercept, weights) for _, text in validation]
    threshold = choose_threshold(validation, validation_scores)
    test_scores = [score_text(text, intercept, weights) for _, text in test]
    test_metrics = metrics(test, test_scores, threshold)
    margin_boundary = percentile([abs(score - threshold) for score in validation_scores], .20)
    report = {
        "dataset": "UCI SMS Spam Collection",
        "datasetUrl": "https://archive.ics.uci.edu/ml/datasets/sms+spam+collection",
        "datasetLicense": LICENSE,
        "datasetCitation": DATA_CITATION,
        "datasetRowsPublished": len(messages),
        "uniqueRowsUsed": len(deduplicated),
        "conflictingTextGroupsRemoved": conflicting_text_groups_removed,
        "deduplication": "case-insensitive Unicode casefold and whitespace normalization; ambiguous cross-label text groups dropped before splitting",
        "splitSeed": SEED,
        "split": {"train": len(train), "validation": len(validation), "test": len(test)},
        "classCountsTrain": counts["documents"],
        "featureCount": len(vocabulary),
        "tokenization": "lowercase Unicode word tokens and adjacent word bigrams",
        "model": "multinomial Naive Bayes with additive alpha=0.5; spam-vs-ham log-likelihood-ratio score",
        "validationThreshold": round(threshold, 6),
        "validationBorderlineMarginP20": round(margin_boundary, 6),
        "testMetrics": test_metrics,
        "limitations": [
            "The UCI dataset combines older English-language spam and legitimate messages from UK and Singapore-related sources; it is not a current Nigerian scam corpus.",
            "Held-out results reflect this small corpus and do not estimate real-world safety or coverage of new scams.",
            "A no-spam-pattern result is not proof a message is safe."
        ]
    }
    model = {
        "schemaVersion": 1,
        "modelType": "multinomial-naive-bayes-log-odds",
        "intercept": intercept,
        "threshold": threshold,
        "borderlineMargin": margin_boundary,
        "alpha": ALPHA,
        "weights": weights,
        "metadata": report
    }
    MODEL_PATH.write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": str(MODEL_PATH), "report": str(REPORT_PATH), "features": len(vocabulary), "test": test_metrics}, indent=2))


if __name__ == "__main__":
    main()
