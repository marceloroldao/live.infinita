(() => {
  let viewerCounter = Number(sessionStorage.getItem('live-infinita-sim-viewer-counter') || '1');
  let simulatorBusy = false;

  const baseShowManager = showManager;
  const baseShowPage = showPage;

  showManager = function () {
    $('login-view').hidden = true;
    $('manager-view').hidden = false;
    const page = ({
      '#integracoes': 'integracoes',
      '#simulador': 'simulador',
      '#relatorio': 'relatorio'
    })[location.hash] || 'overview';
    showPage(page, false);
    if (page === 'simulador') refreshSimulatorState();
  };

  showPage = function (page, refresh = true) {
    baseShowPage(page, refresh);
    if (page === 'simulador') refreshSimulatorState();
  };

  function collectiveText(state) {
    if (!state || !state.dominant) return 'sem direção coletiva';
    const names = {forest: 'floresta', river: 'rio', village: 'vila', field: 'campo'};
    const label = names[state.dominant] || state.dominant;
    const pct = Math.round((Number(state.dominance) || 0) * 100);
    return `${label} · ${pct}% · ${state.contributors || 0} participantes`;
  }

  function worldText(world) {
    if (!world) return 'mundo indisponível';
    return `seq ${world.sequence ?? '—'} · ${world.period || '—'} · ${world.biome || '—'}`;
  }

  function setSimulatorStatus(data) {
    if (!data) return;
    const state = $('simulator-state');
    const live = Boolean(data.live_active);
    state.classList.toggle('status-error', live);
    state.classList.toggle('status-warning', !live && data.tiktok_state === 'searching');
    state.lastChild.textContent = live ? ' Bloqueado durante LIVE real' : ' Modo de teste disponível';
    $('sim-tiktok-state').textContent = live ? 'LIVE real conectada' : `TikTok: ${data.tiktok_state || 'offline'}`;
    $('sim-collective-state').textContent = collectiveText(data.collective);
    $('sim-world-state').textContent = worldText(data.world);
    $('sim-send').disabled = live || simulatorBusy;
  }

  function appendBubble(kind, title, text, meta = '') {
    const feed = $('sim-chat-feed');
    if (!feed) return;
    const empty = feed.querySelector('.sim-chat-empty');
    if (empty) empty.remove();
    const article = document.createElement('article');
    article.className = `sim-bubble ${kind}`;
    const header = document.createElement('header');
    const strong = document.createElement('strong');
    const small = document.createElement('small');
    const body = document.createElement('p');
    strong.textContent = title;
    small.textContent = meta;
    body.textContent = text;
    header.append(strong, small);
    article.append(header, body);
    feed.append(article);
    while (feed.children.length > 30) feed.firstElementChild?.remove();
    feed.scrollTop = feed.scrollHeight;
  }

  function currentIdentity() {
    const displayName = ($('sim-display-name').value || '').trim() || `Visitante ${viewerCounter}`;
    const actorId = ($('sim-actor-id').value || '').trim() || `manager-viewer-${viewerCounter}`;
    return {displayName, actorId};
  }

  function chooseNewViewer() {
    viewerCounter += 1;
    sessionStorage.setItem('live-infinita-sim-viewer-counter', String(viewerCounter));
    $('sim-display-name').value = `Visitante ${viewerCounter}`;
    $('sim-actor-id').value = `manager-viewer-${viewerCounter}`;
    $('sim-comment').focus();
    message(`Agora você está simulando o Visitante ${viewerCounter}.`);
  }

  async function refreshSimulatorState() {
    if (!$('simulador') || $('simulador').hidden || $('manager-view').hidden) return;
    try {
      const data = await api('/api/manage/simulator/state');
      setSimulatorStatus(data);
    } catch (error) {
      $('simulator-state').classList.add('status-error');
      $('simulator-state').lastChild.textContent = ' Simulador indisponível';
      $('sim-send').disabled = true;
    }
  }

  async function sendSimulatorComment(event) {
    event?.preventDefault();
    if (simulatorBusy) return;
    const text = ($('sim-comment').value || '').trim();
    if (!text) return;
    const {displayName, actorId} = currentIdentity();
    simulatorBusy = true;
    $('sim-send').disabled = true;
    $('sim-send').textContent = 'Enviando...';
    appendBubble('viewer', displayName, text, actorId);
    $('sim-comment').value = '';

    try {
      const data = await api('/api/manage/simulator/comment', {
        method: 'POST',
        body: JSON.stringify({
          display_name: displayName,
          actor_id: actorId,
          text
        })
      });

      if (data.narration_cue?.text) {
        appendBubble(
          'narrator',
          'Narrador',
          data.narration_cue.text,
          data.narration_cue.mode || 'interação'
        );
      } else if (data.narration_suppressed) {
        appendBubble(
          'system',
          'Sistema',
          'A interação foi recebida. A voz coletiva está aguardando o próximo momento narrativo.',
          data.narration_suppressed
        );
      }

      const runtime = data.runtime || {};
      const detail = runtime.world_mutated
        ? 'O mundo reagiu à interação.'
        : runtime.ai_fallback === 'proposal_only'
          ? 'A intenção foi compreendida, mas ficou somente como proposta.'
          : 'A interação foi observada sem mutação direta do mundo.';
      appendBubble('system', 'Resultado', detail, `HTTP ${runtime.status_code || '—'}`);
      setSimulatorStatus({
        live_active: false,
        tiktok_state: 'offline-test',
        collective: data.collective,
        world: data.world
      });
      loadMonitor();
    } catch (error) {
      appendBubble('error', 'Erro', String(error.message || error), 'simulador');
      message(String(error.message || error), true);
      await refreshSimulatorState();
    } finally {
      simulatorBusy = false;
      $('sim-send').textContent = 'Enviar como espectador';
      await refreshSimulatorState();
      $('sim-comment').focus();
    }
  }

  $('sim-form')?.addEventListener('submit', sendSimulatorComment);
  $('sim-new-viewer')?.addEventListener('click', chooseNewViewer);
  $('sim-clear-feed')?.addEventListener('click', () => {
    $('sim-chat-feed').innerHTML = '<p class="sim-chat-empty">As interações desta sessão aparecerão aqui.</p>';
  });
  document.querySelectorAll('[data-sim-prompt]').forEach(button => {
    button.addEventListener('click', () => {
      $('sim-comment').value = button.dataset.simPrompt || '';
      $('sim-comment').focus();
    });
  });

  if ($('sim-display-name') && !$('sim-display-name').value) {
    $('sim-display-name').value = `Visitante ${viewerCounter}`;
  }
  if ($('sim-actor-id') && !$('sim-actor-id').value) {
    $('sim-actor-id').value = `manager-viewer-${viewerCounter}`;
  }

  setInterval(() => {
    if ($('simulador') && !$('simulador').hidden) refreshSimulatorState();
  }, 5000);
})();
