const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('live-infinita-operator') || '';
let toastTimer;
let monitorTimer;
let logsTimer;
let novLifeTimer;
let logsPaused = false;
let reportText = '';

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

async function safeApi(path) {
  try { return {ok: true, data: await api(path)}; }
  catch (error) { return {ok: false, error: String(error?.message || error)}; }
}

function showLogin(error = '') {
  clearTimeout(monitorTimer); clearTimeout(logsTimer); clearTimeout(novLifeTimer);
  $('manager-view').hidden = true;
  $('login-view').hidden = false;
  $('login-message').textContent = error;
  $('operator').value = '';
  $('operator').focus();
}

function showManager() {
  $('login-view').hidden = true;
  $('manager-view').hidden = false;
  const page = ({'#integracoes':'integracoes','#relatorio':'relatorio','#nov':'nov'})[location.hash] || 'overview';
  showPage(page, false);
}

function showPage(page, refresh = true) {
  clearTimeout(novLifeTimer);
  document.querySelectorAll('.manager-page').forEach(el => el.hidden = el.id !== page);
  document.querySelectorAll('[data-page]').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  if (page === 'overview' && refresh) { loadMonitor(); loadLogs(true); }
  if (page === 'relatorio' && refresh) generateReport();
  if (page === 'nov') void loadNovLife();
}

document.querySelectorAll('[data-page]').forEach(link => link.onclick = () => showPage(link.dataset.page));

function message(text, error = false) {
  const el = $('message'); clearTimeout(toastTimer);
  el.textContent = text; el.classList.toggle('error', error); el.classList.add('show');
  toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}
function badge(id, ok) { const el = $(id); el.textContent = ok ? 'Conectado' : 'Não configurado'; el.classList.toggle('ok', ok); }
function duration(seconds) { const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60); return h?`${h}h ${m}min`:`${m}min`; }
function monitorTextState(state) { return ({connected:'Ao vivo',searching:'Procurando live',waiting_retry:'Aguardando nova tentativa',disconnected:'Desconectado',live_ended:'Live encerrada',not_started:'Não iniciado',unknown:'Indisponível'})[state] || state; }
function activityLabel(item) { return ({join:'entrou na live',like:'enviou curtidas',gift:'enviou um presente',comment:'comentou',world_event:'alterou o mundo'})[item.kind] || `gerou ${item.kind}`; }
function collectiveLabel(state) {
  if (!state || !state.dominant) return 'sem direção';
  const names = {forest:'floresta',river:'rio',village:'vila',field:'campo'};
  const name = names[state.dominant] || state.dominant;
  const pct = Math.round((state.dominance || 0) * 100);
  return `${name} · ${pct}% · ${state.contributors || 0} pessoas`;
}

async function load() {
  const status = await api('/api/manage/integrations');
  showManager();
  badge('openai-state', status.openai.configured); badge('tiktok-state', status.tiktok.configured);
  $('openai-model').value = status.openai.model;
  $('openai-key').placeholder = status.openai.key_hint ? `Atual: ${status.openai.key_hint}` : 'Cole sua API key';
  $('tiktok-user').value = status.tiktok.unique_id || '';
  $('tiktok-key').placeholder = status.tiktok.sign_key_hint ? `Atual: ${status.tiktok.sign_key_hint}` : 'Deixe vazio para manter a atual';
  await loadMonitor();
  await loadLogs(true);
}

const NOV_NEED_NAMES = {curiosity:'Curiosidade',energy:'Energia',safety:'Segurança',social:'Convivência'};
function novLifeLabel(value) {
  return NOV_NEED_NAMES[value] || (value ? String(value).replaceAll('_',' ') : 'Necessidade não informada');
}
function novLifeText(value) { return value == null || value === '' ? '—' : String(value); }
async function loadNovLife() {
  clearTimeout(novLifeTimer);
  if ($('manager-view').hidden || $('nov').hidden) return;
  const list = $('nov-life-episodes');
  try {
    const result = await api('/api/manage/nov/life');
    list.replaceChildren();
    const records = Array.isArray(result.episodes) ? result.episodes : [];
    $('nov-life-window').textContent = `${records.length} episódio(s) · janela recente`;
    $('nov-life-state').lastChild.textContent = records.length ? ' Memória local ativa' : ' Nenhum episódio na janela';
    $('nov-life-state').classList.toggle('status-warning', !records.length);
    if (!records.length) {
      const li = document.createElement('li');
      li.className = 'empty';
      li.textContent = result.ledger_available ? 'Nenhum episódio de Nov encontrado na janela recente.' : 'Arquivo de memória episódica ainda não disponível.';
      list.append(li);
    }
    for (const episode of records) {
      const li = document.createElement('li');
      const title = document.createElement('strong');
      title.textContent = `${novLifeLabel(episode.need)} · tick ${novLifeText(episode.logical_tick)}`;
      const meta = document.createElement('p');
      const ctx = episode.context || {}, outcome = episode.outcome || {};
      meta.textContent = `Destino: ${novLifeText(episode.target_entity_id)} · região: ${novLifeText(ctx.region_id)} · período: ${novLifeText(ctx.period)} · estratégia: ${novLifeText(episode.strategy_id)}`;
      const resultLine = document.createElement('small');
      resultLine.textContent = `Resultado observado: satisfação ${outcome.satisfaction == null ? '—' : Math.round(outcome.satisfaction * 100) + '%'} · duração ${novLifeText(outcome.elapsed_ticks)} tick(s) · risco ${outcome.observed_risk == null ? '—' : Math.round(outcome.observed_risk * 100) + '%'} · origem: ${novLifeText(episode.provenance)}`;
      li.append(title, meta, resultLine);
      list.append(li);
    }
  } catch (error) {
    $('nov-life-state').lastChild.textContent = ' Memória indisponível';
    $('nov-life-state').classList.add('status-warning');
    list.replaceChildren();
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = 'Não foi possível consultar os episódios neste momento.';
    list.append(li);
  } finally {
    if (!$('manager-view').hidden && !$('nov').hidden) novLifeTimer = setTimeout(loadNovLife, 15000);
  }
}
$('nov-life-refresh').onclick = () => { void loadNovLife(); };

async function loadNovSyncPreview() {
  const button = $('nov-sync-preview-button');
  button.disabled = true;
  const status = $('nov-sync-preview-status');
  const list = $('nov-sync-preview-list');
  list.replaceChildren();
  status.textContent = 'Preparando primeira janela local…';
  try {
    const data = await api('/api/manage/nov/sync/preview?cursor=0');
    if (data.transport_enabled !== false || data.central_receipt !== null || data.candidate_cursor_is_ack !== false) {
      throw new Error('Prévia não confirma transporte desativado');
    }
    const envelopes = Array.isArray(data.episodes) ? data.episodes : [];
    status.textContent = `${envelopes.length} observação(ões) confirmada(s) · janela inicial · cursor candidato ${data.candidate_next_cursor} · sem envio, sem recibo e sem atualização de cursor.`;
    for (const entry of envelopes) {
      const li = document.createElement('li');
      const title = document.createElement('strong');
      title.textContent = `${novLifeLabel(entry.observation?.need)} · tick ${novLifeText(entry.observation?.logical_tick)}`;
      const detail = document.createElement('p');
      detail.textContent = `Fonte: ${novLifeText(entry.source?.source_kind)} · ID: ${novLifeText(entry.source?.episode_id)} · destino: ${novLifeText(entry.observation?.target_entity_id)}`;
      const digest = document.createElement('small');
      digest.textContent = `Chave estável: ${String(entry.record_key || '').slice(0, 20)}… · integridade: ${String(entry.content_sha256 || '').slice(0, 20)}… · sem confirmação central`;
      li.append(title, detail, digest);
      list.append(li);
    }
    if (!envelopes.length) {
      const li = document.createElement('li');
      li.className = 'empty';
      li.textContent = 'Nenhum episódio confirmado disponível nesta janela.';
      list.append(li);
    }
  } catch (_) {
    status.textContent = 'Não foi possível gerar a prévia local. Nenhum dado foi enviado.';
  } finally {
    button.disabled = false;
  }
}
$('nov-sync-preview-button').onclick = () => { void loadNovSyncPreview(); };


async function loadPerformance() {
  if ($('manager-view').hidden || $('overview').hidden) return;
  const value = (id, text) => { $(id).textContent = text; };
  try {
    const data = await api('/api/manage/performance');
    const cpu = data.host || {}, loop = data.api || {}, renderer = data.renderer || {};
    const audio = data.audio || {}, relay = data.audio_web || {};
    const number = v => Number.isFinite(Number(v)) && v !== null ? Number(v) : null;
    const pressure = number(cpu.cpu_pressure_avg10_pct);
    value('perf-cpu', pressure === null ? '—' : pressure.toFixed(1) + '%');
    value('perf-cpu-detail', cpu.load_1m == null ? 'Carga não disponível' : `Carga ${cpu.load_1m} · ${cpu.logical_cpus || '—'} vCPUs`);
    const lag = number(loop.max_recent_ms);
    value('perf-loop', lag === null ? '—' : lag.toFixed(0) + ' ms');
    value('perf-loop-detail', loop.samples ? `Pico nas últimas ${loop.samples} amostras · atual ${loop.last_ms ?? '—'} ms` : 'Aguardando amostras');
    value('perf-fps', renderer.available ? `${renderer.fps} / ${renderer.capture_fps}` : '—');
    value('perf-fps-detail', renderer.available ? `Meta dinâmica · atualização há ${renderer.updated_age_s} s` : 'Telemetria do renderer indisponível');
    value('perf-tts', audio.last_tts_ok === true ? 'OK' : audio.last_tts_ok === false ? 'Falhou' : '—');
    value('perf-tts-detail', audio.last_tts_provider ? `${audio.last_tts_provider} · ${audio.last_pcm_bytes ?? 0} bytes PCM` : 'Nenhuma síntese registrada');
    value('perf-voice', number(audio.voice_chunks) === null ? '—' : String(audio.voice_chunks));
    value('perf-voice-detail', audio.xruns == null ? 'Mixer não medido' : `${audio.xruns} xruns · ${audio.deadline_misses ?? '—'} atrasos`);
    value('perf-listeners', relay.available ? String(relay.active_streams ?? '—') : '—');
    value('perf-listeners-detail', relay.available ? `Capacidade: ${relay.max_clients ?? '—'} conexões` : 'Relay de áudio indisponível');
    const state = $('performance-state');
    state.textContent = renderer.available && relay.available ? 'Telemetria ativa' : 'Telemetria parcial';
    state.classList.toggle('status-warning', !(renderer.available && relay.available));
  } catch (_) {
    $('performance-state').textContent = 'Telemetria indisponível';
    $('performance-state').classList.add('status-warning');
  }
}

async function loadMonitor() {
  clearTimeout(monitorTimer);
  if ($('manager-view').hidden) return;
  try {
    const data = await api('/api/manage/monitor');
    $('runtime-value').textContent = 'Online'; $('runtime-detail').textContent = `ativo há ${duration(data.runtime.uptime_seconds)}`;
    const tiktokState = data.tiktok.stale && data.tiktok.state === 'connected' ? 'stale' : data.tiktok.state;
    $('tiktok-value').textContent = tiktokState === 'stale' ? 'Sem atualização' : monitorTextState(tiktokState);
    $('tiktok-detail').textContent = data.tiktok.unique_id || 'não configurado';
    $('tiktok-live-state').textContent = tiktokState === 'connected' ? 'AO VIVO' : (tiktokState === 'stale' ? 'SEM ATUALIZAÇÃO' : monitorTextState(tiktokState).toUpperCase());
    document.querySelector('.live-pulse').classList.toggle('offline', tiktokState !== 'connected');
    $('live-detail').textContent = data.tiktok.configured ? `${data.tiktok.unique_id} · ${data.audience.total} eventos recebidos` : 'Configure o TikTok na área de integrações.';
    $('monitor-openai-value').textContent = data.openai.configured ? 'Configurada' : 'Não configurada';
    $('monitor-openai-detail').textContent = data.openai.model || '—';
    $('websocket-value').textContent = data.websocket.clients;
    $('audience-total').textContent = `${data.audience.total} eventos`;
    $('joins-value').textContent = data.audience.join; $('likes-value').textContent = data.audience.like; $('gifts-value').textContent = data.audience.gift; $('actors-value').textContent = data.actors.total;
    $('world-version').textContent = data.world.version ?? '—';
    $('world-sequence').textContent = data.world.sequence ?? '—';
    $('world-entities').textContent = data.world.entities;
    $('world-regions').textContent = data.world.regions ?? '—';
    $('world-period').textContent = data.world.period || '—';
    $('story-chapter').textContent = data.world.story?.chapter ?? data.collective?.chapter ?? 0;
    $('story-motif').textContent = data.world.story?.title || data.world.story?.motif || 'história autônoma';
    $('collective-intent').textContent = collectiveLabel(data.collective);
    badge('replay-state', data.world.replay_ok); $('replay-state').textContent = data.world.replay_ok ? 'Replay inicial OK' : 'Replay inicial com erro';
    $('system-state').classList.toggle('status-error', !data.world.replay_ok); $('system-state').lastChild.textContent = data.world.replay_ok ? ' Sistema online' : ' Verificar sistema';
    $('last-update').textContent = `atualizado ${new Date(data.generated_at_unix*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
    const list = $('activity-list'); list.replaceChildren();
    if (!data.activity.length) { const li=document.createElement('li'); li.className='empty'; li.textContent='Nenhum evento registrado.'; list.append(li); }
    data.activity.forEach(item => { const li=document.createElement('li'), t=document.createElement('time'), icon=document.createElement('span'), text=document.createElement('span'), source=document.createElement('small'); t.textContent=item.at_unix?new Date(item.at_unix*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):'—'; icon.className='activity-icon'; icon.textContent=item.channel==='world'?'◇':'•'; text.textContent=`${item.actor} ${activityLabel(item)}`; source.textContent=item.source; li.append(t,icon,text,source); list.append(li); });
    void loadPerformance();
  } catch (error) {
    if (String(error.message).includes('401') || String(error.message).includes('chave')) return showLogin('Sua senha não é mais válida. Entre novamente.');
    $('system-state').classList.add('status-error'); $('system-state').lastChild.textContent=' Monitor indisponível';
  }
  monitorTimer = setTimeout(loadMonitor, 5000);
}

function renderLog(id, data) {
  const el = $(id);
  if (!data.ok && !(data.lines || []).length) { el.textContent = data.error ? `Log indisponível: ${data.error}` : 'Nenhum registro disponível.'; return; }
  const lines = (data.lines || []).slice(-160); el.textContent = lines.length ? lines.join('\n') : 'Nenhum registro ainda.'; el.scrollTop = el.scrollHeight;
}

async function loadLogs(force = false) {
  clearTimeout(logsTimer);
  if ($('manager-view').hidden || (logsPaused && !force)) return;
  try {
    const [tiktok,audio] = await Promise.all([api('/api/ops/logs/tiktok?lines=160'), api('/api/ops/logs/audio?lines=160')]);
    renderLog('tiktok-log', tiktok); renderLog('audio-log', audio);
  } catch (error) {
    if (String(error.message).includes('401') || String(error.message).includes('chave')) return showLogin('Sua senha não é mais válida. Entre novamente.');
    $('tiktok-log').textContent = `Console indisponível: ${error.message}`;
    $('audio-log').textContent = `Console indisponível: ${error.message}`;
  }
  if (!logsPaused) logsTimer = setTimeout(loadLogs, 3000);
}

function sanitizeReportText(value) {
  return String(value ?? '')
    .replace(/sk-[A-Za-z0-9_-]{8,}/g, '[OPENAI_KEY_REMOVIDA]')
    .replace(/(Bearer\s+)[A-Za-z0-9._~+\/-]+/gi, '$1[TOKEN_REMOVIDO]')
    .replace(/((?:api[_-]?key|token|secret|password|authorization|stream[_-]?key)\s*[:=]\s*)[^\s,;]+/gi, '$1[REMOVIDO]')
    .replace(/([?&](?:key|token|secret|api_key|stream_key)=)[^&#\s]+/gi, '$1[REMOVIDO]');
}

function reportLogLines(result) {
  if (!result.ok) return [`[endpoint indisponível: ${sanitizeReportText(result.error)}]`];
  const lines = Array.isArray(result.data?.lines) ? result.data.lines.slice(-100) : [];
  if (!lines.length) return ['[sem registros recentes]'];
  return lines.map(line => {
    const text = String(line || '');
    if (/coment[aá]rio\s+actor=|\btext=['"]/i.test(text)) return '[comentário da audiência omitido]';
    return sanitizeReportText(text);
  });
}

function endpointLine(name, result) {
  return `- ${name}: ${result.ok ? 'OK' : `FALHOU — ${sanitizeReportText(result.error)}`}`;
}

function reportAlerts(results) {
  const {health, monitor, collective, tiktokLog, audioLog} = results;
  const alerts = [];
  if (!health.ok) alerts.push(`ERRO: /api/health indisponível (${sanitizeReportText(health.error)})`);
  if (!monitor.ok) alerts.push(`ERRO: monitor indisponível (${sanitizeReportText(monitor.error)})`);
  if (!collective.ok) alerts.push(`AVISO: intenção coletiva indisponível (${sanitizeReportText(collective.error)})`);
  if (!tiktokLog.ok) alerts.push(`AVISO: console TikTok indisponível (${sanitizeReportText(tiktokLog.error)})`);
  if (!audioLog.ok) alerts.push(`AVISO: console de áudio indisponível (${sanitizeReportText(audioLog.error)})`);
  if (monitor.ok) {
    const data = monitor.data || {};
    if (data.world?.replay_ok === false) alerts.push('ERRO: replay do World State não está íntegro.');
    if (data.runtime?.state && data.runtime.state !== 'online') alerts.push(`ERRO: runtime reportou estado ${data.runtime.state}.`);
    if (data.tiktok?.configured && data.tiktok?.stale) alerts.push('AVISO: TikTok configurado, mas o status está sem atualização.');
    if (data.tiktok?.configured && ['disconnected','live_ended','unknown'].includes(data.tiktok?.state)) alerts.push(`AVISO: TikTok está ${data.tiktok.state}.`);
    if (!data.openai?.configured) alerts.push('AVISO: OpenAI não está configurada.');
  }
  return alerts.length ? alerts : ['Nenhum alerta estrutural detectado pelo Manager.'];
}

async function generateReport() {
  const button = $('report-generate');
  button.disabled = true; button.textContent = 'Gerando...';
  $('report-state').classList.remove('status-error','status-warning');
  $('report-state').lastChild.textContent = ' Coletando diagnóstico';
  const [health, monitor, collective, tiktokLog, audioLog, integrations] = await Promise.all([
    safeApi('/api/health'),
    safeApi('/api/manage/monitor'),
    safeApi('/api/audience/collective-intent'),
    safeApi('/api/ops/logs/tiktok?lines=100'),
    safeApi('/api/ops/logs/audio?lines=100'),
    safeApi('/api/manage/integrations')
  ]);
  const results = {health, monitor, collective, tiktokLog, audioLog, integrations};
  const alerts = reportAlerts(results);
  const now = new Date();
  const m = monitor.ok ? monitor.data || {} : {};
  const h = health.ok ? health.data || {} : {};
  const c = collective.ok ? collective.data?.state || {} : {};
  const i = integrations.ok ? integrations.data || {} : {};
  const storyAudience = collective.ok ? collective.data?.story_audience || {} : {};
  const sections = [
    'LIVE INFINITA — RELATÓRIO DE DIAGNÓSTICO v1',
    `Gerado em: ${now.toISOString()}`,
    `Origem: ${location.origin}`,
    `Navegador: ${navigator.userAgent}`,
    '',
    '=== SEGURANÇA ===',
    '- Senha do Manager: NÃO incluída',
    '- Bearer token: NÃO incluído',
    '- API keys / secrets: NÃO incluídos',
    '- Comentários brutos da audiência: NÃO incluídos',
    '',
    '=== ALERTAS DETECTADOS ===',
    ...alerts.map(item => `- ${item}`),
    '',
    '=== ENDPOINTS ===',
    endpointLine('/api/health', health),
    endpointLine('/api/manage/monitor', monitor),
    endpointLine('/api/audience/collective-intent', collective),
    endpointLine('/api/ops/logs/tiktok', tiktokLog),
    endpointLine('/api/ops/logs/audio', audioLog),
    endpointLine('/api/manage/integrations', integrations),
    '',
    '=== RUNTIME ===',
    `health.mvp: ${h.mvp ?? h.name ?? '—'}`,
    `health.version: ${h.version ?? '—'}`,
    `runtime.state: ${m.runtime?.state ?? '—'}`,
    `runtime.uptime_seconds: ${m.runtime?.uptime_seconds ?? '—'}`,
    `websocket.clients: ${m.websocket?.clients ?? '—'}`,
    '',
    '=== WORLD STATE ===',
    `world.version: ${m.world?.version ?? '—'}`,
    `world.sequence: ${m.world?.sequence ?? '—'}`,
    `world.entities: ${m.world?.entities ?? '—'}`,
    `world.regions: ${m.world?.regions ?? '—'}`,
    `world.period: ${m.world?.period ?? '—'}`,
    `world.replay_ok: ${m.world?.replay_ok ?? '—'}`,
    `world.story.chapter: ${m.world?.story?.chapter ?? c.chapter ?? '—'}`,
    `world.story.title: ${sanitizeReportText(m.world?.story?.title || m.world?.story?.motif || '—')}`,
    '',
    '=== NARRADOR / INTENÇÃO COLETIVA ===',
    `narrator.policy: ${m.narrator?.policy ?? '—'}`,
    `narrator.active_participants: ${m.narrator?.audience?.participants ?? storyAudience.participants ?? '—'}`,
    `collective.dominant: ${c.dominant ?? '—'}`,
    `collective.dominance: ${c.dominance ?? '—'}`,
    `collective.contributors: ${c.contributors ?? '—'}`,
    `collective.comment_signals: ${c.comment_signals ?? '—'}`,
    `collective.chapter: ${c.chapter ?? '—'}`,
    `collective.ready: ${c.ready ?? '—'}`,
    '',
    '=== INTEGRAÇÕES ===',
    `OpenAI.configured: ${m.openai?.configured ?? i.openai?.configured ?? '—'}`,
    `OpenAI.model: ${sanitizeReportText(m.openai?.model || i.openai?.model || '—')}`,
    `TikTok.configured: ${m.tiktok?.configured ?? i.tiktok?.configured ?? '—'}`,
    `TikTok.user: ${sanitizeReportText(m.tiktok?.unique_id || i.tiktok?.unique_id || '—')}`,
    `TikTok.state: ${m.tiktok?.state ?? '—'}`,
    `TikTok.stale: ${m.tiktok?.stale ?? '—'}`,
    `TikTok.age_seconds: ${m.tiktok?.age_seconds ?? '—'}`,
    '',
    '=== AUDIÊNCIA ===',
    `events.total: ${m.audience?.total ?? '—'}`,
    `events.join: ${m.audience?.join ?? '—'}`,
    `events.like: ${m.audience?.like ?? '—'}`,
    `events.gift: ${m.audience?.gift ?? '—'}`,
    `actors.total: ${m.actors?.total ?? '—'}`,
    `actors.bound: ${m.actors?.bound ?? '—'}`,
    '',
    '=== LOG TIKTOK — ÚLTIMAS LINHAS SANITIZADAS ===',
    ...reportLogLines(tiktokLog),
    '',
    '=== LOG ÁUDIO/NARRADOR — ÚLTIMAS LINHAS SANITIZADAS ===',
    ...reportLogLines(audioLog),
    '',
    '=== FIM DO RELATÓRIO ==='
  ];
  reportText = sanitizeReportText(sections.join('\n'));
  $('diagnostic-report').textContent = reportText;
  $('report-generated-at').textContent = now.toLocaleString('pt-BR');
  const hasError = alerts.some(item => item.startsWith('ERRO:'));
  const hasWarning = alerts.some(item => item.startsWith('AVISO:'));
  $('report-state').classList.toggle('status-error', hasError);
  $('report-state').classList.toggle('status-warning', !hasError && hasWarning);
  $('report-state').lastChild.textContent = hasError ? ' Erros encontrados' : (hasWarning ? ' Atenção necessária' : ' Sem alertas estruturais');
  button.disabled = false; button.textContent = 'Gerar novamente';
  return reportText;
}

async function copyReport() {
  if (!reportText) await generateReport();
  try {
    await navigator.clipboard.writeText(reportText);
  } catch (_) {
    const area=document.createElement('textarea'); area.value=reportText; area.setAttribute('readonly',''); area.style.position='fixed'; area.style.opacity='0'; document.body.append(area); area.select(); document.execCommand('copy'); area.remove();
  }
  message('Relatório copiado. Pode colar diretamente no ChatGPT.');
}

async function downloadReport() {
  if (!reportText) await generateReport();
  const blob = new Blob([reportText + '\n'], {type:'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = `live-infinita-diagnostico-${new Date().toISOString().replace(/[:.]/g,'-')}.txt`;
  document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  message('Relatório .txt gerado.');
}

$('logs-refresh').onclick = () => loadLogs(true);
$('logs-pause').onclick = () => { logsPaused=!logsPaused; $('logs-pause').textContent=logsPaused?'Retomar':'Pausar'; if(logsPaused) clearTimeout(logsTimer); else loadLogs(true); };
$('report-generate').onclick = () => generateReport().catch(error => { $('report-state').classList.add('status-error'); $('report-state').lastChild.textContent=' Falha ao gerar'; message(error.message,true); });
$('report-copy').onclick = () => copyReport().catch(error => message(error.message,true));
$('report-download').onclick = () => downloadReport().catch(error => message(error.message,true));

$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button=$('unlock'); button.disabled=true; $('login-message').textContent=''; token=$('operator').value.trim();
  try { await api('/api/manage/integrations'); sessionStorage.setItem('live-infinita-operator', token); $('operator').value=''; await load(); message('Acesso liberado.'); }
  catch(error) { token=''; sessionStorage.removeItem('live-infinita-operator'); showLogin(error.message); }
  finally { button.disabled=false; }
});
$('toggle-password').onclick=()=>{const input=$('operator');input.type=input.type==='password'?'text':'password';$('toggle-password').setAttribute('aria-label',input.type==='password'?'Mostrar senha':'Ocultar senha');};
$('logout').onclick=()=>{token='';sessionStorage.removeItem('live-infinita-operator');showLogin();};

document.querySelectorAll('[data-save]').forEach(button=>button.onclick=async()=>{const payload=button.dataset.save==='openai'?{openai_api_key:$('openai-key').value||null,openai_model:$('openai-model').value}:{tiktok_unique_id:$('tiktok-user').value,tiktok_sign_api_key:$('tiktok-key').value||null};try{await api('/api/manage/integrations',{method:'PUT',body:JSON.stringify(payload)});$('openai-key').value='';$('tiktok-key').value='';await load();message('Configuração salva com segurança.');}catch(error){message(error.message,true);}});
document.querySelectorAll('[data-clear]').forEach(button=>button.onclick=async()=>{if(!confirm('Remover esta chave?'))return;try{await api('/api/manage/integrations',{method:'PUT',body:JSON.stringify({[button.dataset.clear]:''})});await load();message('Chave removida.');}catch(error){message(error.message,true);}});
$('test-openai').onclick=async()=>{try{const result=await api('/api/manage/integrations/openai/test',{method:'POST'});message(`OpenAI conectada. ${result.models_available} modelos disponíveis.`);await loadMonitor();}catch(error){message(error.message,true);}};

if (token) load().catch(()=>{token='';sessionStorage.removeItem('live-infinita-operator');showLogin();}); else showLogin();
