# Local-context stress test: a caution, not validation

PauseCheck’s existing classifier was tested unchanged against **135 constructed Nigerian-context examples** from the public [NaijaScamBench v0 dataset](https://huggingface.co/datasets/Eterniti/NaijaScamBench). The dataset is published under **CC BY 4.0**. Its card says the constructed messages were written by the benchmark team, contain no real people’s data, and should be treated as a small starting point. It also says the local-language examples have not been reviewed by native speakers.

The model matched the dataset labels on **71 of 135 examples (52.6%)**. It matched 21 of 49 scam labels (42.9% recall) and 50 of 86 legitimate labels (58.1% specificity). It missed 28 scam examples and flagged 36 legitimate examples. These are results on this particular constructed set—not an estimate of real-world scam detection in Nigeria. They show that PauseCheck’s frozen UCI-trained model is a weak fit for this small challenge set and should not be relied on to judge Nigerian messages.

The benchmark contains 180 rows overall. Its 45 rows marked as sourced from the UCI SMS Spam Collection were excluded because UCI is the model’s training source. The test made no model updates, threshold changes or training on benchmark examples. It reads the app’s actual browser result, processes public text in memory, and saves only aggregate results to [`LOCAL_PILOT_EVALUATION.json`](LOCAL_PILOT_EVALUATION.json). Run it with `python3 tests/evaluate_naijascambench_pilot.py` when online.

The evaluated set is still highly limited: 110 examples are English, 12 are Nigerian Pidgin, and Yoruba, Hausa and Igbo each have only four examples; one is mixed-language. Those groups are far too small for language-specific conclusions. The dataset card further warns that constructed examples may be optimistic because they were written by the team behind another scam-checking project. The test covers only the learned model label, not the separate rule-based flags, user behavior, or protection from financial loss.

A separate Zenodo record, [Nigerian Computer-Mediated Fraudulent Text Messages](https://doi.org/10.5281/zenodo.16947613), is licensed CC BY 4.0 and describes messages collected from researchers’ personal inboxes, colleagues and students. Because its record does not describe message-level de-identification or privacy safeguards, PauseCheck did **not** download or use that corpus. An open license alone does not answer whether private message contents are safe to reuse.

## What this means for PauseCheck

Do not describe the model as locally validated or promote the stress-test scores as a real-world performance estimate. Keep its output framed as an uncertain, non-authoritative text signal. A meaningful future Nigerian pilot would need participant consent, clear data minimization and retention controls, independent labeling, native-language review, and a much larger, representative set. This private test is not a substitute for that work.

## Reproducibility

The test pins the benchmark CSV to revision `558fcb62602b8421733381fbfedcc61167398d12` and verifies its SHA-256 digest before processing it. The browser test uses the app’s shipped model exactly as delivered. No benchmark message text, IDs or individual predictions are retained in the project.
