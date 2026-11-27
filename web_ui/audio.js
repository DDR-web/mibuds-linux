(function () {
  "use strict";

  class CommuteSoundEngine {
    constructor() {
      this.ctx = null;
      this.activeNodes = [];
      this.currentMode = "off";
      this.ringInterval = null;
    }

    _ensureCtx() {
      if (!this.ctx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return null;
        this.ctx = new AudioCtx();
      }
      if (this.ctx.state === "suspended") {
        this.ctx.resume().catch(() => {});
      }
      return this.ctx;
    }

    _makeNoiseBuffer(ctx, kind) {
      const sampleRate = ctx.sampleRate;
      const len = sampleRate * 4;
      const buf = ctx.createBuffer(1, len, sampleRate);
      const out = buf.getChannelData(0);

      let b0 = 0, b1 = 0, b2 = 0, lastOut = 0;
      for (let i = 0; i < len; i++) {
        const white = Math.random() * 2 - 1;
        if (kind === "brown") {
          lastOut = (lastOut + 0.02 * white) / 1.02;
          out[i] = lastOut * 2.6;
        } else {
          b0 = 0.99765 * b0 + white * 0.0990460;
          b1 = 0.96300 * b1 + white * 0.2965164;
          b2 = 0.57000 * b2 + white * 1.0526913;
          out[i] = (b0 + b1 + b2 + white * 0.1848) * 0.14;
        }
      }
      return buf;
    }

    stopCommute() {
      this.currentMode = "off";
      for (const node of this.activeNodes) {
        try {
          if (node.stop) node.stop();
          node.disconnect();
        } catch (_) {}
      }
      this.activeNodes = [];
    }

    playCommute(mode) {
      this.stopCommute();
      if (!mode || mode === "off") return;
      const ctx = this._ensureCtx();
      if (!ctx) return;
      this.currentMode = mode;

      const src = ctx.createBufferSource();
      src.buffer = this._makeNoiseBuffer(ctx, mode === "airplane" ? "brown" : "pink");
      src.loop = true;

      const filter = ctx.createBiquadFilter();
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0.001, ctx.currentTime);

      if (mode === "airplane") {
        filter.type = "lowpass";
        filter.frequency.value = 340;
        gain.gain.exponentialRampToValueAtTime(0.09, ctx.currentTime + 0.6);
      } else if (mode === "public_transit") {
        filter.type = "bandpass";
        filter.frequency.value = 620;
        filter.Q.value = 0.65;
        gain.gain.exponentialRampToValueAtTime(0.075, ctx.currentTime + 0.6);
      } else if (mode === "train") {
        filter.type = "lowpass";
        filter.frequency.value = 460;
        gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.6);

        // Gentle rhythmic rail pulse modulation
        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.frequency.value = 1.65;
        lfoGain.gain.value = 0.02;
        lfo.connect(lfoGain);
        lfoGain.connect(gain.gain);
        lfo.start();
        this.activeNodes.push(lfo, lfoGain);
      }

      src.connect(filter);
      filter.connect(gain);
      gain.connect(ctx.destination);
      src.start();
      this.activeNodes.push(src, filter, gain);
    }

    setRinging(active) {
      if (this.ringInterval) {
        clearInterval(this.ringInterval);
        this.ringInterval = null;
      }
      if (!active) return;
      const ctx = this._ensureCtx();
      if (!ctx) return;

      const chirp = () => {
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(2400, now);
        osc.frequency.setValueAtTime(3100, now + 0.14);
        gain.gain.setValueAtTime(0.001, now);
        gain.gain.exponentialRampToValueAtTime(0.08, now + 0.04);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.34);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.36);
      };

      chirp();
      this.ringInterval = setInterval(chirp, 850);
    }
  }

  window.XiaomiAudio = new CommuteSoundEngine();
})();
