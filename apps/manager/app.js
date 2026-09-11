const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('live-infinita-operator') || '';
$('operator').value = token;

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', ...(options.headers || {}) }});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}
function message(text, error=false){ $('message').textContent=text; $('message').style.color=error?'#ff98a3':'#9fb4ff'; }
function badge(id, ok){ const e=$(id); e.textContent=ok?'Configurado':'Não configurado'; e.classList.toggle('ok',ok); }
async function load(){
  const status=await api('/api/manage/integrations');
  $('panel').hidden=false; badge('openai-state',status.openai.configured); badge('tiktok-state',status.tiktok.configured);
  $('openai-model').value=status.openai.model; $('openai-key').placeholder=status.openai.key_hint?`Atual: ${status.openai.key_hint}`:'Cole sua API key';
  $('tiktok-user').value=status.tiktok.unique_id||''; $('tiktok-key').placeholder=status.tiktok.sign_key_hint?`Atual: ${status.tiktok.sign_key_hint}`:'Opcional';
}
$('unlock').onclick=async()=>{ token=$('operator').value.trim(); sessionStorage.setItem('live-infinita-operator',token); try{await load();message('Gerência desbloqueada.')}catch(e){$('panel').hidden=true;message(e.message,true)} };
document.querySelectorAll('[data-save]').forEach(button=>button.onclick=async()=>{
  const which=button.dataset.save, payload=which==='openai'?{openai_api_key:$('openai-key').value||null,openai_model:$('openai-model').value}:{tiktok_unique_id:$('tiktok-user').value,tiktok_sign_api_key:$('tiktok-key').value||null};
  try{await api('/api/manage/integrations',{method:'PUT',body:JSON.stringify(payload)}); $('openai-key').value='';$('tiktok-key').value='';await load();message('Configuração salva com segurança.')}catch(e){message(e.message,true)}
});
document.querySelectorAll('[data-clear]').forEach(button=>button.onclick=async()=>{if(!confirm('Remover esta chave?'))return;try{await api('/api/manage/integrations',{method:'PUT',body:JSON.stringify({[button.dataset.clear]:''})});await load();message('Chave removida.')}catch(e){message(e.message,true)}});
$('test-openai').onclick=async()=>{try{const r=await api('/api/manage/integrations/openai/test',{method:'POST'});message(`OpenAI conectada. ${r.models_available} modelos disponíveis para esta chave.`)}catch(e){message(e.message,true)}};
if(token) load().catch(()=>sessionStorage.removeItem('live-infinita-operator'));
