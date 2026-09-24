(() => {
  'use strict';

  let operatorToken = '';
  let timer = null;
  let audioActive = false;

  const HISTORY_MAX_SAMPLES = 240;
  const HISTORY_MIN_SAMPLE_MS = 5000;
  const ALERT_HISTORY_MAX = 40;
  const ALERT_WARN_COOLDOWN_MS = 60000;
  const ALERT_CRITICAL_COOLDOWN_MS = 20000;
  const HOT_WARN = 80;
  const HOT_CRITICAL = 96;
  const WARM_WARN = 160;
  const WARM_CRITICAL = 192;
  const PREFETCH_WARN_RATE = 0.70;
  const PREFETCH_MIN_PROMOTIONS = 10;

  const spatialHistory = [];
  const alertHistory = [];
  let lastHistorySampleAt = 0;
  const lastAlertState = new Map();
  let alertLevelFilter = 'all';
  let alertKindFilter = 'all';

  const $ = (id) => document.getElementById(id);
  const monitor = $('monitor');
  const unlockCard = $('unlock-card');
  const unlockMessage = $('unlock-message');
  const audio = $('program-audio');
  const audioButton = $('audio');
  const preview = $('preview');

  async function getJSON(url, options = {}) {
    const response = await fetch(url, { cache: 'no-store', ...options });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function dot(id, state) { $(id).className = `dot ${state}`; }
  function text(id, value) { $(id).textContent = String(value ?? '—'); }
  function status(id, dotId, ok, yes, no = 'Indisponível') {
    text(id, ok ? yes : no);
    dot(dotId, ok ? 'good' : 'bad');
  }
  function setMaster(state, level) { text('master-state', state); dot('master-dot', level); }

  async function validateOperator(token) {
    return getJSON('/api/manage/integrations', { headers: { Authorization: `Bearer ${token}` } });
  }

  function broadcasterView(payload) {
    if (!payload || typeof payload !== 'object') return { live: false, label: 'PARADO', level: 'muted' };
    const updated = Number(payload.updated_at_unix || 0);
    const age = Date.now() / 1000 - updated;
    if (!Number.isFinite(age) || age > 5) return { live: false, label: 'PARADO', level: 'muted' };
    if (payload.state === 'live' && payload.mode === 'live') return { live: true, label: 'TRANSMITINDO', level: 'good' };
    if (payload.state === 'probing') return { live: false, label: 'PROBE', level: 'warn' };
    if (payload.state === 'error') return { live: false, label: 'ERRO', level: 'bad' };
    return { live: false, label: String(payload.state || 'PARADO').toUpperCase(), level: 'muted' };
  }

  function renderSpatialHistory() {
    const hotLine = $('history-hot');
    const warmLine = $('history-warm');
    if (!hotLine || !warmLine) return;
    if (spatialHistory.length === 0) {
      hotLine.setAttribute('points', '');
      warmLine.setAttribute('points', '');
      text('history-window', '0 min');
      text('history-hit', 'Prefetch —');
      return;
    }

    const width = 600;
    const height = 180;
    const maxValue = Math.max(1, ...spatialHistory.flatMap((row) => [row.hot, row.warm]));
    const xFor = (index) => spatialHistory.length === 1 ? width : (index / (spatialHistory.length - 1)) * width;
    const yFor = (value) => height - (Math.max(0, value) / maxValue) * (height - 8) - 4;
    const pointsFor = (key) => spatialHistory.map((row, index) => `${xFor(index).toFixed(1)},${yFor(row[key]).toFixed(1)}`).join(' ');

    hotLine.setAttribute('points', pointsFor('hot'));
    warmLine.setAttribute('points', pointsFor('warm'));
    const elapsedMs = spatialHistory[spatialHistory.length - 1].at - spatialHistory[0].at;
    text('history-window', `${Math.max(0, Math.round(elapsedMs / 60000))} min`);
    const latest = spatialHistory[spatialHistory.length - 1];
    text('history-hit', Number.isFinite(latest.hitRate) ? `Prefetch ${Math.round(latest.hitRate * 100)}%` : 'Prefetch —');
  }

  function appendSpatialHistory(payload) {
    const now = Date.now();
    if (now - lastHistorySampleAt < HISTORY_MIN_SAMPLE_MS) return;
    const hot = Number(payload.hot);
    const warm = Number(payload.warm);
    if (!Number.isFinite(hot) || !Number.isFinite(warm)) return;
    spatialHistory.push({ at: now, hot: Math.max(0, hot), warm: Math.max(0, warm), hitRate: Number(payload.prefetch_hit_rate) });
    lastHistorySampleAt = now;
    while (spatialHistory.length > HISTORY_MAX_SAMPLES) spatialHistory.shift();
    renderSpatialHistory();
  }

  function alertMatches(row) {
    const levelOk = alertLevelFilter === 'all' || row.level === alertLevelFilter;
    const kindOk = alertKindFilter === 'all' || row.kind === alertKindFilter;
    return levelOk && kindOk;
  }

  function renderAlertFilters() {
    document.querySelectorAll('[data-alert-level]').forEach((button) => button.classList.toggle('active', button.dataset.alertLevel === alertLevelFilter));
    document.querySelectorAll('[data-alert-kind]').forEach((button) => button.classList.toggle('active', button.dataset.alertKind === alertKindFilter));
  }

  function renderAlerts() {
    const list = $('alert-history');
    if (!list) return;
    list.replaceChildren();
    const rows = alertHistory.filter(alertMatches);
    if (rows.length === 0) {
      const item = document.createElement('li');
      item.className = 'alert-empty';
      item.textContent = alertHistory.length === 0 ? 'Nenhum alerta espacial nesta sessão.' : 'Nenhum alerta neste filtro.';
      list.appendChild(item);
      renderAlertFilters();
      return;
    }
    for (const row of [...rows].reverse()) {
      const item = document.createElement('li');
      item.className = `alert-item ${row.level}`;
      const when = new Date(row.at).toLocaleTimeString('pt-BR');
      item.textContent = `${when} · ${row.kind.toUpperCase()} · ${row.message}`;
      list.appendChild(item);
    }
    renderAlertFilters();
  }

  function pushAlert(key, kind, level, message) {
    const now = Date.now();
    const previous = lastAlertState.get(key) || { at: 0, level: '' };
    const escalated = previous.level === 'warn' && level === 'critical';
    const cooldown = level === 'critical' ? ALERT_CRITICAL_COOLDOWN_MS : ALERT_WARN_COOLDOWN_MS;
    if (!escalated && now - Number(previous.at || 0) < cooldown) return;
    lastAlertState.set(key, { at: now, level });
    alertHistory.push({ at: now, key, kind, level, message, escalated });
    while (alertHistory.length > ALERT_HISTORY_MAX) alertHistory.shift();
    renderAlerts();
  }

  function evaluateSpatialAlerts(payload) {
    const hot = Number(payload.hot);
    const warm = Number(payload.warm);
    const rate = Number(payload.prefetch_hit_rate);
    const promotions = Number(payload.promotions_total || 0);

    let level = 'good';
    let label = 'NORMAL';

    if (Number.isFinite(hot)) {
      if (hot >= HOT_CRITICAL) {
        pushAlert('hot', 'hot', 'critical', `HOT atingiu ${hot}/${HOT_CRITICAL}`);
        level = 'bad'; label = 'CRÍTICO';
      } else if (hot >= HOT_WARN) {
        pushAlert('hot', 'hot', 'warn', `HOT elevado: ${hot}/${HOT_CRITICAL}`);
        if (level === 'good') { level = 'warn'; label = 'ATENÇÃO'; }
      }
    }

    if (Number.isFinite(warm)) {
      if (warm >= WARM_CRITICAL) {
        pushAlert('warm', 'warm', 'critical', `WARM atingiu ${warm}/${WARM_CRITICAL}`);
        level = 'bad'; label = 'CRÍTICO';
      } else if (warm >= WARM_WARN) {
        pushAlert('warm', 'warm', 'warn', `WARM elevado: ${warm}/${WARM_CRITICAL}`);
        if (level === 'good') { level = 'warn'; label = 'ATENÇÃO'; }
      }
    }

    if (promotions >= PREFETCH_MIN_PROMOTIONS && Number.isFinite(rate) && rate < PREFETCH_WARN_RATE) {
      pushAlert('prefetch', 'prefetch', 'warn', `Prefetch abaixo de 70%: ${Math.round(rate * 100)}%`);
      if (level === 'good') { level = 'warn'; label = 'ATENÇÃO'; }
    }

    text('spatial-alert-state', label);
    dot('spatial-alert-dot', level);
  }

  function applySpatialMetrics(payload) {
    text('spatial-hot', payload.hot ?? '—');
    text('spatial-warm', payload.warm ?? '—');
    const rate = Number(payload.prefetch_hit_rate);
    text('spatial-hit-rate', Number.isFinite(rate) ? `${Math.round(rate * 100)}%` : '—');
    text('spatial-predicted', payload.predicted_promotions_total ?? '—');
    text('spatial-unexpected', payload.unexpected_promotions_total ?? '—');
    text('spatial-transitions', payload.active_transitions ?? '—');
    text('spatial-cold', payload.cold_omitted ? 'OMITIDO' : '—');
    appendSpatialHistory(payload);
    evaluateSpatialAlerts(payload);
  }

  async function refreshTelemetry() {
    if (!operatorToken) return;
    const [healthResult, worldResult, replayResult, audioResult, broadcasterResult] = await Promise.allSettled([
      getJSON('/api/health'), getJSON('/api/world'), getJSON('/api/replay/verify'), getJSON('/audio/health'), getJSON('/broadcast-status.json'),
    ]);
    const health = healthResult.status === 'fulfilled' ? healthResult.value : null;
    const world = worldResult.status === 'fulfilled' ? worldResult.value : null;
    const replay = replayResult.status === 'fulfilled' ? replayResult.value : null;
    const audioHealth = audioResult.status === 'fulfilled' ? audioResult.value : null;
    const broadcaster = broadcasterResult.status === 'fulfilled' ? broadcasterResult.value : null;
    const broadcast = broadcasterView(broadcaster);

    status('runtime-state', 'runtime-dot', Boolean(health?.ok), 'ONLINE');
    status('replay-state', 'replay-dot', Boolean(replay?.ok), 'ÍNTEGRO', 'FALHA');
    status('audio-state', 'audio-dot', Boolean(audioHealth?.ok), 'ONLINE');
    text('broadcaster-state', broadcast.label); dot('broadcaster-dot', broadcast.level);

    const tiktokConfigured = Boolean(health?.integrations?.tiktok);
    text('tiktok-state', tiktokConfigured ? 'CONFIGURADO' : 'NÃO CONFIG.'); dot('tiktok-dot', tiktokConfigured ? 'good' : 'warn');
    const openaiConfigured = Boolean(health?.integrations?.openai);
    text('openai-state', openaiConfigured ? 'CONFIGURADO' : 'NÃO CONFIG.'); dot('openai-dot', openaiConfigured ? 'good' : 'warn');

    if (world) {
      text('sequence', world.sequence ?? '—'); text('version', world.version ?? '—');
      text('entities', Array.isArray(world.entities) ? world.entities.length : '—');
      text('period', world.environment?.period ?? '—'); text('narration', world.narration?.text || 'Sem narrativa no estado atual.');
    }
    if (health) {
      text('audience-events', health.audience_events_total ?? '—'); text('actors', health.actors_total ?? '—'); text('proposals', health.audience_proposals_total ?? '—');
    }
    const coreReady = Boolean(health?.ok && replay?.ok && audioHealth?.ok);
    if (broadcast.live && coreReady) setMaster('LIVE', 'good');
    else if (coreReady) setMaster('PRONTO', 'good');
    else if (health?.ok) setMaster('DEGRADADO', 'warn');
    else setMaster('OFFLINE', 'bad');
    text('updated', new Date().toLocaleTimeString('pt-BR'));
  }

  async function unlock() {
    const token = $('operator').value.trim();
    if (!token) { unlockMessage.textContent = 'Informe a chave do operador.'; return; }
    $('unlock').disabled = true; unlockMessage.textContent = 'Validando…';
    try {
      await validateOperator(token); operatorToken = token; $('operator').value = ''; unlockCard.hidden = true; monitor.hidden = false; unlockMessage.textContent = '';
      setMaster('CARREGANDO', 'warn'); await refreshTelemetry(); timer = window.setInterval(refreshTelemetry, 3000);
    } catch (_) {
      operatorToken = ''; unlockMessage.textContent = 'Chave inválida ou Runtime indisponível.'; setMaster('BLOQUEADO', 'muted');
    } finally { $('unlock').disabled = false; }
  }

  async function toggleAudio() {
    if (!audioActive) {
      try { audio.src = `/audio/live.mp3?ts=${Date.now()}`; await audio.play(); audioActive = true; audioButton.textContent = 'Silenciar áudio'; }
      catch (_) { audioButton.textContent = 'Tentar áudio novamente'; }
    } else {
      audio.pause(); audio.removeAttribute('src'); audio.load(); audioActive = false; audioButton.textContent = 'Ativar áudio';
    }
  }

  function restartAudioIfNeeded() {
    if (!audioActive) return;
    window.setTimeout(async () => {
      if (!audioActive) return;
      try { audio.src = `/audio/live.mp3?ts=${Date.now()}`; await audio.play(); } catch (_) { restartAudioIfNeeded(); }
    }, 1200);
  }

  window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin) return;
    const payload = event.data;
    if (!payload || payload.type !== 'live-infinita-spatial-metrics') return;
    applySpatialMetrics(payload);
  });

  document.querySelectorAll('[data-alert-level]').forEach((button) => button.addEventListener('click', () => {
    alertLevelFilter = button.dataset.alertLevel || 'all'; renderAlerts();
  }));
  document.querySelectorAll('[data-alert-kind]').forEach((button) => button.addEventListener('click', () => {
    alertKindFilter = button.dataset.alertKind || 'all'; renderAlerts();
  }));

  $('unlock').addEventListener('click', unlock);
  $('operator').addEventListener('keydown', (event) => { if (event.key === 'Enter') unlock(); });
  $('refresh').addEventListener('click', async () => { preview.src = `/godot/?capture=1&ts=${Date.now()}`; await refreshTelemetry(); });
  audioButton.addEventListener('click', toggleAudio);
  audio.addEventListener('ended', restartAudioIfNeeded); audio.addEventListener('error', restartAudioIfNeeded);
  window.addEventListener('beforeunload', () => {
    if (timer) window.clearInterval(timer);
    operatorToken = ''; spatialHistory.length = 0; alertHistory.length = 0; lastAlertState.clear();
  });

  renderAlerts();
})();
