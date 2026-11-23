# PauseCheck model card

## Intended use

Screen a short, user-provided SMS, WhatsApp forward, or email snippet for wording patterns associated with the “spam” class in a public English-language SMS corpus. Show influential terms and separate rule-based flags for links, urgency, and requests for sensitive data. Offer cautious verification steps.

## Not intended for

A definitive scam/fraud verdict, phishing-site detection, link reputation checking, Nigerian-language coverage claims, financial advice, law-enforcement evidence, a safe-sender guarantee, or emergency incident response. The model cannot inspect sender identity, URL destination, message headers, or conversation context.

## Training data and license

UCI Machine Learning Repository’s SMS Spam Collection, DOI [10.24432/C5CC84](https://doi.org/10.24432/C5CC84), licensed CC BY 4.0. The public source describes 5,574 labeled messages built from older sources including UK spam reports and legitimate SMS subsets with Singapore-related provenance. The training script processes the archive in memory, groups case-insensitive whitespace-normalized text before splitting, and drops any normalized text group with contradictory labels. The current corpus snapshot leaves 5,159 messages and contains no contradictory-label groups. Raw SMS text is not saved or bundled; only learned parameters and aggregate evaluation are exported with source attribution.

## Model and evaluation

Multinomial Naive Bayes with word unigrams and adjacent-word bigrams, Unicode-aware lowercase tokenization, 9,571 features, and additive smoothing α=0.5. A stratified 70/15/15 split uses seed 2026. The spam threshold is chosen against the validation split by F1; metrics below use the separate held-out test split.

- Train: 3,610 messages.
- Validation: 773 messages.
- Test: 776 messages.
- Test accuracy: 98.71%; spam precision: 100%; spam recall: 89.69%; specificity: 100%; F1: 94.57%.
- Confusion matrix: 87 true positives, 0 false positives, 679 true negatives, 10 false negatives.

These results describe only this random holdout from this dataset. They are not a real-world deployment estimate. The test split contains 97 messages labeled spam, so a small number of changed outcomes would materially shift the percentages.

## Exploratory Nigerian-context stress test—not validation

The frozen browser model was checked against the 135 `constructed` examples in the public [NaijaScamBench v0](https://huggingface.co/datasets/Eterniti/NaijaScamBench) benchmark. Its 45 examples marked as sourced from UCI were excluded because UCI is the training source. The model matched 71 of 135 labels (52.59%): 21 of 49 scam examples (42.86% recall) and 50 of 86 legitimate examples (58.14% specificity). It missed 28 scam examples and flagged 36 legitimate examples. The model was not retrained and its threshold was not changed.

This is a small, constructed-example stress test, not real-world Nigerian validation. The dataset card says local-language examples have not been reviewed by native speakers; the evaluated set has only 12 Pidgin examples and four each in Yoruba, Hausa and Igbo. It cannot support language-specific claims or an estimate of real-world safety. The test evaluates the learned model label only, not the separate rule-based flags or whether users avoid harm. Do not rely on PauseCheck to decide whether a Nigerian message is safe. The version-pinned test script and aggregate-only report are [`tests/evaluate_naijascambench_pilot.py`](tests/evaluate_naijascambench_pilot.py) and [`LOCAL_PILOT_EVALUATION.json`](LOCAL_PILOT_EVALUATION.json); details and the reason another personal-inbox corpus was excluded are in [`LOCAL_PILOT.md`](LOCAL_PILOT.md).

## Runtime and data

Inference, pattern flags, and explanations run in the browser. The app loads the bundled `model.json` from the same origin and caches the static app shell/model after first load via a service worker. Message text is held only in page memory; it is not put in local storage, cookies, query strings, server requests, analytics or logs by the app. The app never fetches a message link or contacts a sender. Clearing the tab clears the entered text.

## Limitations and safeguards

The UCI messages are older English examples from a different context—not a current Nigerian scam dataset. Nigerian slang, Yoruba, Hausa, Igbo, new financial scams and indirect social engineering may be missed. Legitimate notifications may be flagged. Sensitive-request rules are heuristic and may produce false alerts. The result is explicitly described as a pattern screen, not a verdict; even “no strong match” is not a safety guarantee. The app points to ngCERT and CBN guidance without implying endorsement.
