const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('live-infinita-operator') || '';
let toastTimer;
let monitorTimer;
let logsTimer;
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
  clearTimeout(monitorTimer); clearTimeout(logsTimer);
  $('manager-view').hidden = true;
  $('login-view').hidden = false;
  $('login-message').textContent = error;
  $('operator').value = '';
  $('operator').focus();
}

function showManager() {
  $('login-view').hidden = true;
  $('manager-view').hidden = false;
  const page = ({'#integracoes':'integracoes','#relatorio':'relatorio'})[location.hash] || 'overview';
  showPage(page, false);
}

function showPage(page, refresh = true) {
  document.querySelectorAll('.manager-page').forEach(el => el.hidden = el.id !== page);
  document.querySelectorAll('[data-page]').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  if (page === 'overview' && refresh) { loadMonitor(); loadLogs(true); }
  if (page === 'relatorio' && refresh) generateReport();
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
    badge('replay-state', data.world.replay_ok); $('replay-state').textContent = data.world.replay_ok ? 'Replay íntegro' : 'Replay com erro';
    $('system-state').classList.toggle('status-error', !data.world.replay_ok); $('system-state').lastChild.textContent = data.world.replay_ok ? ' Sistema online' : ' Verificar sistema';
    $('last-update').textContent = `atualizado ${new Date(data.generated_at_unix*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
    const list = $('activity-list'); list.replaceChildren();
    if (!data.activity.length) { const li=document.createElement('li'); li.className='empty'; li.textContent='Nenhum evento registrado.'; list.append(li); }
    data.activity.forEach(item => { const li=document.createElement('li'), t=document.createElement('time'), icon=document.createElement('span'), text=document.createElement('span'), source=document.createElement('small'); t.textContent=item.at_unix?new Date(item.at_unix*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):'—'; icon.className='activity-icon'; icon.textContent=item.channel==='world'?'◇':'•'; text.textContent=`${item.actor} ${activityLabel(item)}`; source.textContent=item.source; li.append(t,icon,text,source); list.append(li); });
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
