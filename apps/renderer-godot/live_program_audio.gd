extends RefCounted

static func install() -> void:
    if not OS.has_feature("web"): return
    var script := """
(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('capture') === '1') { window.__liveInfinitaCaptureMode = true; return true; }
  if (window.__liveInfinitaAudioInstalled) return true;
  window.__liveInfinitaAudioInstalled = true;
  const audio = document.createElement('audio');
  audio.id = 'live-infinita-program-audio'; audio.preload = 'none'; audio.src = '/audio/live.mp3'; audio.volume = 1.0;
  document.body.appendChild(audio);
  const btn = document.createElement('button');
  btn.id = 'live-infinita-audio-button'; btn.textContent = '🔊 ATIVAR ÁUDIO DA LIVE';
  Object.assign(btn.style, {position:'fixed',left:'50%',bottom:'18px',transform:'translateX(-50%)',zIndex:'99999',padding:'14px 22px',borderRadius:'12px',border:'1px solid rgba(255,255,255,.35)',background:'rgba(8,12,20,.92)',color:'#fff',font:'700 15px system-ui,sans-serif',cursor:'pointer'});
  document.body.appendChild(btn);
  const start = async () => { try { audio.src='/audio/live.mp3?ts='+Date.now(); await audio.play(); btn.textContent='🔊 ÁUDIO ATIVO'; setTimeout(()=>{btn.style.display='none';},1400); window.__liveInfinitaAudioActive=true; } catch(e) { btn.textContent='⚠ TOQUE NOVAMENTE'; } };
  btn.addEventListener('click', start);
  let reconnectTimer=null;
  const reconnect=()=>{ if(!window.__liveInfinitaAudioActive||reconnectTimer!==null)return; reconnectTimer=setTimeout(async()=>{reconnectTimer=null;try{audio.src='/audio/live.mp3?ts='+Date.now();await audio.play();}catch(_){reconnect();}},1200); };
  audio.addEventListener('ended',reconnect); audio.addEventListener('error',reconnect); return true;
})()
"""
    JavaScriptBridge.eval(script)

