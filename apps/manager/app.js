const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('live-infinita-operator') || '';
let toastTimer;

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
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}

function showLogin(error = '') {
  $('manager-view').hidden = true;
  $('login-view').hidden = false;
  $('login-message').textContent = error;
  $('operator').value = '';
  $('operator').focus();
}

function showManager() {
  $('login-view').hidden = true;
  $('manager-view').hidden = false;
}

function message(text, error = false) {
  const el = $('message');
  clearTimeout(toastTimer);
  el.textContent = text;
  el.classList.toggle('error', error);
  el.classList.add('show');
  toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}

function badge(id, ok) {
  const el = $(id);
  el.textContent = ok ? 'Conectado' : 'Não configurado';
  el.classList.toggle('ok', ok);
}

async function load() {
  const status = await api('/api/manage/integrations');
  showManager();
  badge('openai-state', status.openai.configured);
  badge('tiktok-state', status.tiktok.configured);
  $('openai-model').value = status.openai.model;
  $('openai-key').placeholder = status.openai.key_hint ? `Atual: ${status.openai.key_hint}` : 'Cole sua API key';
  $('tiktok-user').value = status.tiktok.unique_id || '';
  $('tiktok-key').placeholder = status.tiktok.sign_key_hint ? `Atual: ${status.tiktok.sign_key_hint}` : 'Deixe vazio para manter a atual';
}

$('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('unlock');
  button.disabled = true;
  $('login-message').textContent = '';
  token = $('operator').value.trim();
  try {
    await load();
    sessionStorage.setItem('live-infinita-operator', token);
    $('operator').value = '';
    message('Acesso liberado.');
  } catch (error) {
    token = '';
    sessionStorage.removeItem('live-infinita-operator');
    showLogin(error.message);
  } finally {
    button.disabled = false;
  }
});

$('toggle-password').onclick = () => {
  const input = $('operator');
  input.type = input.type === 'password' ? 'text' : 'password';
  $('toggle-password').setAttribute('aria-label', input.type === 'password' ? 'Mostrar senha' : 'Ocultar senha');
};

$('logout').onclick = () => {
  token = '';
  sessionStorage.removeItem('live-infinita-operator');
  showLogin();
};

document.querySelectorAll('[data-save]').forEach(button => button.onclick = async () => {
  const payload = button.dataset.save === 'openai'
    ? {openai_api_key: $('openai-key').value || null, openai_model: $('openai-model').value}
    : {tiktok_unique_id: $('tiktok-user').value, tiktok_sign_api_key: $('tiktok-key').value || null};
  try {
    await api('/api/manage/integrations', {method: 'PUT', body: JSON.stringify(payload)});
    $('openai-key').value = '';
    $('tiktok-key').value = '';
    await load();
    message('Configuração salva com segurança.');
  } catch (error) {
    message(error.message, true);
  }
});

document.querySelectorAll('[data-clear]').forEach(button => button.onclick = async () => {
  if (!confirm('Remover esta chave?')) return;
  try {
    await api('/api/manage/integrations', {method: 'PUT', body: JSON.stringify({[button.dataset.clear]: ''})});
    await load();
    message('Chave removida.');
  } catch (error) {
    message(error.message, true);
  }
});

$('test-openai').onclick = async () => {
  try {
    const result = await api('/api/manage/integrations/openai/test', {method: 'POST'});
    message(`OpenAI conectada. ${result.models_available} modelos disponíveis.`);
  } catch (error) {
    message(error.message, true);
  }
};

if (token) {
  load().catch(() => {
    token = '';
    sessionStorage.removeItem('live-infinita-operator');
    showLogin();
  });
} else {
  showLogin();
}
