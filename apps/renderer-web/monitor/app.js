(() => {
  'use strict';

  let operatorToken = '';
  let timer = null;
  let audioActive = false;

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

  function applySpatialMetrics(payload) {
    text('spatial-hot', payload.hot ?? '—');
    text('spatial-warm', payload.warm ?? '—');
    const rate = Number(payload.prefetch_hit_rate);
    text('spatial-hit-rate', Number.isFinite(rate) ? `${Math.round(rate * 100)}%` : '—');
    text('spatial-predicted', payload.predicted_promotions_total ?? '—');
    text('spatial-unexpected', payload.unexpected_promotions_total ?? '—');
    text('spatial-transitions', payload.active_transitions ?? '—');
    text('spatial-cold', payload.cold_omitted ? 'OMITIDO' : '—');
  }

  async function refreshTelemetry() {
    if (!operatorToken) return;

    const [healthResult, worldResult, replayResult, audioResult, broadcasterResult] = await Promise.allSettled([
      getJSON('/api/health'),
      getJSON('/api/world'),
      getJSON('/api/replay/verify'),
      getJSON('/audio/health'),
      getJSON('/broadcast-status.json'),
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
    text('broadcaster-state', broadcast.label);
    dot('broadcaster-dot', broadcast.level);

    const tiktokConfigured = Boolean(health?.integrations?.tiktok);
    text('tiktok-state', tiktokConfigured ? 'CONFIGURADO' : 'NÃO CONFIG.');
    dot('tiktok-dot', tiktokConfigured ? 'good' : 'warn');

    const openaiConfigured = Boolean(health?.integrations?.openai);
    text('openai-state', openaiConfigured ? 'CONFIGURADO' : 'NÃO CONFIG.');
    dot('openai-dot', openaiConfigured ? 'good' : 'warn');

    if (world) {
      text('sequence', world.sequence ?? '—');
      text('version', world.version ?? '—');
      text('entities', Array.isArray(world.entities) ? world.entities.length : '—');
      text('period', world.environment?.period ?? '—');
      text('narration', world.narration?.text || 'Sem narrativa no estado atual.');
    }

    if (health) {
      text('audience-events', health.audience_events_total ?? '—');
      text('actors', health.actors_total ?? '—');
      text('proposals', health.audience_proposals_total ?? '—');
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
    $('unlock').disabled = true;
    unlockMessage.textContent = 'Validando…';
    try {
      await validateOperator(token);
      operatorToken = token;
      $('operator').value = '';
      unlockCard.hidden = true;
      monitor.hidden = false;
      unlockMessage.textContent = '';
      setMaster('CARREGANDO', 'warn');
      await refreshTelemetry();
      timer = window.setInterval(refreshTelemetry, 3000);
    } catch (_) {
      operatorToken = '';
      unlockMessage.textContent = 'Chave inválida ou Runtime indisponível.';
      setMaster('BLOQUEADO', 'muted');
    } finally {
      $('unlock').disabled = false;
    }
  }

  async function toggleAudio() {
    if (!audioActive) {
      try {
        audio.src = `/audio/live.mp3?ts=${Date.now()}`;
        await audio.play();
        audioActive = true;
        audioButton.textContent = 'Silenciar áudio';
      } catch (_) {
        audioButton.textContent = 'Tentar áudio novamente';
      }
    } else {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      audioActive = false;
      audioButton.textContent = 'Ativar áudio';
    }
  }

  function restartAudioIfNeeded() {
    if (!audioActive) return;
    window.setTimeout(async () => {
      if (!audioActive) return;
      try {
        audio.src = `/audio/live.mp3?ts=${Date.now()}`;
        await audio.play();
      } catch (_) { restartAudioIfNeeded(); }
    }, 1200);
  }

  window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin) return;
    const payload = event.data;
    if (!payload || payload.type !== 'live-infinita-spatial-metrics') return;
    applySpatialMetrics(payload);
  });

  $('unlock').addEventListener('click', unlock);
  $('operator').addEventListener('keydown', (event) => { if (event.key === 'Enter') unlock(); });
  $('refresh').addEventListener('click', async () => {
    preview.src = `/godot/?capture=1&ts=${Date.now()}`;
    await refreshTelemetry();
  });
  audioButton.addEventListener('click', toggleAudio);
  audio.addEventListener('ended', restartAudioIfNeeded);
  audio.addEventListener('error', restartAudioIfNeeded);
  window.addEventListener('beforeunload', () => {
    if (timer) window.clearInterval(timer);
    operatorToken = '';
  });
})();
