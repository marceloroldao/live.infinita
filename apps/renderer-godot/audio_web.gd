extends RefCounted

var enabled := false
var ambient_volume := 0.18

func setup() -> void:
    if not OS.has_feature("web"):
        return
    var js := """
(() => {
  if (window.LiveInfinitaAudio) return true;
  window.LiveInfinitaAudio = {
    ctx: null,
    master: null,
    ambient: null,
    enabled: false,
    ensure: function() {
      if (this.ctx) return;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      this.ctx = new AudioCtx();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.9;
      this.master.connect(this.ctx.destination);

      const ambient = this.ctx.createGain();
      ambient.gain.value = 0.18;
      ambient.connect(this.master);
      this.ambient = ambient;

      // Soft filtered-noise bed: wind / distant forest texture.
      const seconds = 3;
      const length = Math.floor(this.ctx.sampleRate * seconds);
      const buffer = this.ctx.createBuffer(1, length, this.ctx.sampleRate);
      const data = buffer.getChannelData(0);
      let last = 0;
      for (let i = 0; i < length; i++) {
        const white = Math.random() * 2 - 1;
        last = last * 0.985 + white * 0.015;
        data[i] = last * 0.7;
      }
      const noise = this.ctx.createBufferSource();
      noise.buffer = buffer;
      noise.loop = true;
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.value = 900;
      filter.Q.value = 0.4;
      noise.connect(filter);
      filter.connect(ambient);
      noise.start();

      // Very low harmonic bed to avoid sterile silence.
      const toneGain = this.ctx.createGain();
      toneGain.gain.value = 0.018;
      toneGain.connect(ambient);
      [82.41, 123.47].forEach((hz, index) => {
        const osc = this.ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = hz;
        const g = this.ctx.createGain();
        g.gain.value = index === 0 ? 0.55 : 0.25;
        osc.connect(g);
        g.connect(toneGain);
        osc.start();
      });
    },
    enable: async function() {
      this.ensure();
      if (!this.ctx) return false;
      if (this.ctx.state !== 'running') await this.ctx.resume();
      this.enabled = true;
      if (this.ambient) this.ambient.gain.setTargetAtTime(0.18, this.ctx.currentTime, 0.2);
      return true;
    },
    setAmbientVolume: function(value) {
      this.ensure();
      const v = Math.max(0, Math.min(0.5, Number(value) || 0));
      if (this.ambient && this.ctx) this.ambient.gain.setTargetAtTime(v, this.ctx.currentTime, 0.15);
      return v;
    },
    speak: function(text) {
      if (!this.enabled || !('speechSynthesis' in window)) return false;
      const clean = String(text || '').trim();
      if (!clean) return false;
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(clean);
      utter.lang = 'pt-BR';
      utter.rate = 0.94;
      utter.pitch = 0.96;
      utter.volume = 0.92;
      const voices = window.speechSynthesis.getVoices();
      const ptbr = voices.find(v => String(v.lang).toLowerCase() === 'pt-br') ||
                   voices.find(v => String(v.lang).toLowerCase().startsWith('pt'));
      if (ptbr) utter.voice = ptbr;
      window.speechSynthesis.speak(utter);
      return true;
    }
  };
  return true;
})()
"""
    JavaScriptBridge.eval(js, true)

func enable_audio() -> bool:
    if not OS.has_feature("web"):
        return false
    setup()
    var result = JavaScriptBridge.eval("window.LiveInfinitaAudio && window.LiveInfinitaAudio.enable()", true)
    enabled = true
    return result != null

func set_ambient_volume(value: float) -> void:
    ambient_volume = clampf(value, 0.0, 0.5)
    if not OS.has_feature("web"):
        return
    setup()
    JavaScriptBridge.eval(
        "window.LiveInfinitaAudio && window.LiveInfinitaAudio.setAmbientVolume(%s)" % ambient_volume,
        true
    )

func speak(text: String) -> void:
    var clean := text.strip_edges()
    if clean.is_empty() or not enabled or not OS.has_feature("web"):
        return
    setup()
    JavaScriptBridge.eval(
        "window.LiveInfinitaAudio && window.LiveInfinitaAudio.speak(%s)" % JSON.stringify(clean),
        true
    )
