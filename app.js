(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const input = $('messageInput');
  const MAX_CHARS = 5000;
  let model = null;
  const samples = {
    grant: 'URGENT: Your ₦50,000 support grant has been approved. Confirm your BVN and OTP now at http://cbn-grants.example/verify before midnight.',
    ordinary: 'Hi, the meeting is at 3 pm tomorrow. Please bring the printed agenda. See you then.'
  };
  const wordPattern = /[\p{L}\p{N}_]+/gu;
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function tokenize(text) {
    const words = (text.toLocaleLowerCase().match(wordPattern) || []);
    const features = [...words];
    for (let i = 0; i + 1 < words.length; i++) features.push(`${words[i]} ${words[i + 1]}`);
    return { words, features };
  }
  function classify(text) {
    const { words, features } = tokenize(text);
    const counts = new Map();
    let known = 0;
    for (const feature of features) {
      const weight = model.weights[feature];
      if (typeof weight !== 'number') continue;
      known++;
      counts.set(feature, (counts.get(feature) || 0) + 1);
    }
    const contributions = [...counts.entries()].map(([term, count]) => ({ term, value: model.weights[term] * count }));
    const score = model.intercept + contributions.reduce((sum, row) => sum + row.value, 0);
    const margin = score - model.threshold;
    const boundary = Math.max(.25, Number(model.borderlineMargin) || .25);
    const spamLike = margin >= 0;
    const borderline = Math.abs(margin) <= boundary;
    const spamTerms = contributions.filter(row => row.value > 0).sort((a, b) => b.value - a.value).slice(0, 4);
    const hamTerms = contributions.filter(row => row.value < 0).sort((a, b) => a.value - b.value).slice(0, 4);
    const allCount = features.length;
    return {
      score, margin, boundary, spamLike, borderline, spamTerms, hamTerms,
      coverage: allCount ? known / allCount : 0,
      marker: Math.max(3, Math.min(97, 50 + 46 * Math.tanh(margin / 4)))
    };
  }
  function warningFlags(text) {
    const lower = text.toLowerCase();
    const flags = [];
    const hasLink = /(?:https?:\/\/|www\.)\S+|\b[a-z0-9-]+\.(?:com|net|org|info|xyz|site|app|ng|co|gov)(?:\/\S*)?/iu.test(text);
    const hasUrgency = /\b(?:urgent(?:ly)?|immediately|right now|within\s+\d+\s*(?:minutes?|mins?|hours?|hrs?)|before (?:midnight|\d|today)|expires? today|last chance|final notice|act now|account.{0,24}(?:blocked|suspended)|blocked.{0,24}(?:today|now))\b/iu.test(text);
    const credentialPattern = /\b(?:otp|one[ -]?time (?:password|code)|pin|password|passcode|cvv|security code|verification code|bvn|nin|bank details|account number|card number)\b/iu;
    const credentialMention = credentialPattern.test(text);
    const discouragesSharing = /\b(?:(?:(?:do not|don't|never|avoid|should not|shouldn't|must not|mustn't)(?: ever)?\s+(?:share|send|provide|enter|confirm|verify|update|reply with|submit|give|forward|tell|disclose))|(?:no one should\s+(?:share|send|provide|enter|confirm|verify|update|reply with|submit|give|forward|tell|disclose)))\b[^.!?]{0,80}\b(?:otp|one[ -]?time (?:password|code)|pin|password|passcode|cvv|security code|verification code|bvn|nin|bank details|account number|card number)\b|\b(?:otp|one[ -]?time (?:password|code)|pin|password|passcode|cvv|security code|verification code|bvn|nin|bank details|account number|card number)\b[^.!?]{0,60}\b(?:should|must) not be (?:shared|sent|provided|entered|confirmed|verified|updated|submitted|given)\b/iu.test(text);
    const requestsBeforeCredential = /\b(?:send|share|provide|enter|confirm|verify|update|reply with|submit|give|forward|tell us|need to)\b[^.!?]{0,80}\b(?:otp|one[ -]?time (?:password|code)|pin|password|passcode|cvv|security code|verification code|bvn|nin|bank details|account number|card number)\b/iu.test(text);
    const requestsAfterCredential = /\b(?:otp|one[ -]?time (?:password|code)|pin|password|passcode|cvv|security code|verification code|bvn|nin|bank details|account number|card number)\b[^.!?]{0,80}\b(?:send|share|provide|enter|confirm|verify|update|reply with|submit|give|forward)\b/iu.test(text);
    const asksCredential = credentialMention && !discouragesSharing && (requestsBeforeCredential || requestsAfterCredential);
    const impersonation = /\b(?:cbn|central bank|bank|government|ministry|police|customs|efcc|support scheme|grant|relief fund|tax authority|delivery company|courier|customer care|customer support)\b/iu.test(text);
    const moneyBait = /(?:₦|\b(?:cash prize|you (?:have )?won|winner|grant|free airtime|free data|bonus|refund|prize money|financial aid|support payment|claim (?:your )?(?:reward|prize|grant)|double your money)\b)/iu.test(text);
    if (hasLink) flags.push({ level: 'strong', label: 'A link or web address is present', detail: 'PauseCheck does not open or check the destination. A familiar logo or name does not prove the address is official.' });
    if (asksCredential) flags.push({ level: 'strong', label: 'The message asks for a sensitive code or detail', detail: 'Never share an OTP, PIN, password, BVN, NIN or card security code in response to a message.' });
    if (hasUrgency) flags.push({ level: 'caution', label: 'Urgent or deadline pressure', detail: 'Pressure to act immediately can discourage independent verification; urgency alone is not proof of fraud.' });
    if (impersonation && (hasLink || hasUrgency || asksCredential || moneyBait)) flags.push({ level: 'caution', label: 'An official or financial organisation is mentioned', detail: 'Check the claim using the organisation’s official app or a contact you find independently.' });
    if (moneyBait) flags.push({ level: 'caution', label: 'A reward, grant or payment is mentioned', detail: 'Unexpected offers should be verified through an official source before you pay or share information.' });
    if (!flags.length) flags.push({ level: 'none', label: 'No common link, urgency or credential-request pattern found', detail: 'The message can still be unsafe. New, indirect or context-dependent scams may not trigger these checks.' });
    return flags;
  }
  function setError(text) {
    $('formError').textContent = text;
    $('formError').classList.toggle('hidden', !text);
  }
  function renderEvidence(result) {
    const terms = result.spamLike ? result.spamTerms : result.hamTerms;
    const cls = result.spamLike ? 'spam' : 'ham';
    $('evidenceLabel').textContent = terms.length ? (result.spamLike ? 'PUSHED TOWARD SPAM' : 'PUSHED AWAY FROM SPAM') : 'NO STRONG WORD CLUES';
    $('modelEvidence').innerHTML = terms.length
      ? terms.map(row => `<span class="evidence-chip ${cls}">“${escapeHtml(row.term)}”</span>`).join('')
      : '<span class="evidence-chip none">No prominent learned words in this sample</span>';
  }
  function renderFlags(flags) {
    $('warningFlags').innerHTML = flags.map(flag => `<div class="flag-pill ${flag.level === 'strong' ? 'strong' : flag.level === 'none' ? 'flag-none' : ''}" title="${escapeHtml(flag.detail)}">${escapeHtml(flag.label)}</div>`).join('');
    $('warningFlags').setAttribute('aria-label', flags.map(flag => `${flag.label}. ${flag.detail}`).join(' '));
  }
  function showResult(text) {
    if (!model) { setError('The bundled model did not load. Run this app through the local server steps in README.md.'); return; }
    const trimmed = text.trim();
    if (!trimmed) { setError('Paste a message or choose an example before checking.'); return; }
    if (trimmed.length > MAX_CHARS) { setError(`Please use a message under ${MAX_CHARS} characters.`); return; }
    setError('');
    const result = classify(trimmed);
    const flags = warningFlags(trimmed);
    $('emptyResult').classList.add('hidden');
    $('scanResult').classList.remove('hidden');
    const label = $('resultLabel');
    label.className = `result-label ${result.spamLike ? 'warn' : result.borderline ? '' : 'clear'}`;
    const strongFlag = flags.some(flag => flag.level === 'strong');
    if (result.borderline) {
      label.textContent = 'BORDERLINE · VERIFY';
      $('resultTitle').textContent = 'Treat this as uncertain.';
      $('resultSummary').textContent = 'The model score is close to its screening boundary. Don’t use this result to decide whether to trust the sender.';
      $('resultStrength').textContent = 'MIXED MODEL SIGNAL';
    } else if (result.spamLike) {
      label.textContent = 'PAUSE & VERIFY';
      $('resultTitle').textContent = 'Spam-like wording detected.';
      $('resultSummary').textContent = strongFlag
        ? 'The model found spam-like wording, and a separate check found a high-risk request or link. Verify through an official channel before doing anything.'
        : 'The model found wording patterns associated with spam in its training corpus. This is a screening signal—not proof this message is fraudulent.';
      $('resultStrength').textContent = 'MODEL SCREEN · NOT A VERDICT';
    } else {
      label.textContent = 'NO STRONG MODEL MATCH';
      $('resultTitle').textContent = 'No strong spam pattern found.';
      $('resultSummary').textContent = 'This message did not cross the model’s spam-like threshold. New or local scams may be missed; verify unexpected requests anyway.';
      $('resultStrength').textContent = 'LIMITED MODEL SIGNAL';
    }
    $('signalMeter').setAttribute('aria-label', `Relative spam-like wording signal; ${result.spamLike ? 'model score is on the spam-like side of its threshold' : 'model score is below its spam-like threshold'}. Not a probability.`);
    $('meterMarker').style.left = `${result.marker}%`;
    renderEvidence(result);
    renderFlags(flags);
    $('nextStepText').textContent = strongFlag
      ? 'Do not tap the link or share the requested details. Contact the named organisation using its official app, website or number found independently.'
      : 'If the message asks you to pay or act, verify through a contact you find independently. Never share an OTP, PIN or password in response to a message.';
    if (result.coverage < .2) $('evidenceLabel').textContent += ' · FEW KNOWN FEATURES';
    $('scanResult').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function updateCount() { $('charCount').textContent = `${input.value.length} / ${MAX_CHARS}`; }
  function loadSample(name) {
    input.value = samples[name] || '';
    $('sampleNote').classList.remove('hidden');
    updateCount(); setError(''); showResult(input.value);
  }
  function clearForm() {
    input.value = ''; updateCount(); setError('');
    $('sampleNote').classList.add('hidden');
    $('scanResult').classList.add('hidden'); $('emptyResult').classList.remove('hidden');
    input.focus();
  }
  $('checkButton').addEventListener('click', () => { $('sampleNote').classList.add('hidden'); showResult(input.value); });
  $('clearButton').addEventListener('click', clearForm);
  input.addEventListener('input', () => { $('sampleNote').classList.add('hidden'); updateCount(); setError(''); });
  input.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') showResult(input.value); });
  document.querySelectorAll('[data-sample]').forEach(button => button.addEventListener('click', () => loadSample(button.dataset.sample)));
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js', { scope: './' }).catch(() => {});

  fetch('./model.json', { cache: 'no-store' })
    .then(response => { if (!response.ok) throw new Error('Could not load the local model file'); return response.json(); })
    .then(loaded => {
      if (loaded.schemaVersion !== 1 || loaded.modelType !== 'multinomial-naive-bayes-log-odds' || !loaded.weights) throw new Error('Unsupported local model format');
      model = loaded;
      $('modelStatus').classList.add('ready');
      $('modelStatus').innerHTML = '<i></i> MODEL READY · RUNS HERE';
      $('modelDetailsBody').insertAdjacentHTML('beforeend', `<p><b>Current model run:</b> ${escapeHtml(String(model.metadata.split.train))} training examples, ${escapeHtml(String(model.metadata.split.validation))} validation examples and ${escapeHtml(String(model.metadata.split.test))} held-out test examples; threshold selected on validation only.</p>`);
    })
    .catch(() => {
      $('modelStatus').classList.remove('ready');
      $('modelStatus').innerHTML = '<i></i> LOCAL MODEL NOT LOADED';
      setError('The bundled model did not load. Run this app through the local server steps in README.md.');
    });
  updateCount();
})();
