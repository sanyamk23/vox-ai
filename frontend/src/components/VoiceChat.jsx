import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Phone, Mic, Square, Activity, Briefcase, User,
  PhoneCall, CheckCircle, XCircle, AlertTriangle,
  MessageSquare, Loader2, Zap, Clock
} from 'lucide-react';

// ── Outcome config ────────────────────────────────────────────────────────────
const OUTCOME = {
  INTERESTED:         { label: 'Interested',         cls: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20', Icon: CheckCircle },
  CALLBACK_REQUESTED: { label: 'Callback Requested', cls: 'text-indigo-400  bg-indigo-400/10  border-indigo-400/20',  Icon: Phone },
  BUSY:               { label: 'Busy',               cls: 'text-amber-400   bg-amber-400/10   border-amber-400/20',   Icon: Clock },
  NOT_INTERESTED:     { label: 'Not Interested',     cls: 'text-rose-400    bg-rose-400/10    border-rose-400/20',    Icon: XCircle },
  CONFUSED:           { label: 'Unclear',            cls: 'text-slate-400   bg-slate-400/10   border-slate-400/20',   Icon: AlertTriangle },
};
const scoreColor = (s) => s >= 8 ? '#34d399' : s >= 5 ? '#fbbf24' : '#f87171';
const scoreGlow  = (s) => s >= 8 ? 'rgba(52,211,153,0.2)' : s >= 5 ? 'rgba(251,191,36,0.2)' : 'rgba(248,113,113,0.2)';

// ── Helpers ───────────────────────────────────────────────────────────────────
const jsonTry  = (s) => { try { return JSON.parse(s); } catch { return {}; } };
const nowTime  = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const fmt      = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

function floatTo16BitPCM(input) {
  const buf = new ArrayBuffer(input.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return buf;
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function VoiceChat() {
  const [status,    setStatus]    = useState('idle');   // idle | connecting | connected | ended
  const [messages,  setMessages]  = useState([]);
  const [recap,     setRecap]     = useState(null);
  const [jd,        setJd]        = useState('We are looking for a Senior Software Engineer proficient in React and Django.');
  const [phone,     setPhone]     = useState('+91');
  const [name,      setName]      = useState('');
  const [bars,      setBars]      = useState(Array(40).fill(0));
  const [aiSpeaks,  setAiSpeaks]  = useState(false);
  const [elapsed,   setElapsed]   = useState(0);

  const wsRef       = useRef(null);
  const audioCtxRef = useRef(null);
  const procRef     = useRef(null);
  const streamRef   = useRef(null);
  const analyserRef = useRef(null);
  const rafRef      = useRef(null);
  const audioQ      = useRef([]);
  const playing     = useRef(false);
  const endRef      = useRef(null);
  const timerRef    = useRef(null);

  // ── auto-scroll ──
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // ── timer ──
  useEffect(() => {
    if (status === 'connected') {
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);
    } else {
      clearInterval(timerRef.current);
      if (status === 'idle') setElapsed(0);
    }
    return () => clearInterval(timerRef.current);
  }, [status]);

  // ── waveform RAF loop ──
  const startWaveform = useCallback(() => {
    const tick = () => {
      if (!analyserRef.current) return;
      const d = new Uint8Array(analyserRef.current.frequencyBinCount);
      analyserRef.current.getByteFrequencyData(d);
      const N = 40, step = Math.max(1, Math.floor(d.length / N));
      setBars(Array.from({ length: N }, (_, i) => d[i * step] / 255));
      rafRef.current = requestAnimationFrame(tick);
    };
    tick();
  }, []);

  // ── audio playback ──
  const playNext = useCallback(async () => {
    if (!audioQ.current.length) { playing.current = false; setAiSpeaks(false); return; }
    playing.current = true;
    setAiSpeaks(true);
    const buf = audioQ.current.shift();
    try {
      const decoded = await audioCtxRef.current.decodeAudioData(buf);
      const src = audioCtxRef.current.createBufferSource();
      src.buffer = decoded;
      src.connect(audioCtxRef.current.destination);
      src.onended = playNext;
      src.start(0);
    } catch { playNext(); }
  }, []);

  // ── mic setup ──
  const startMic = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    audioCtxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 128;
    analyserRef.current = analyser;
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    procRef.current = proc;
    proc.onaudioprocess = (e) => {
      const pcm = floatTo16BitPCM(e.inputBuffer.getChannelData(0));
      if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(pcm);
    };
    source.connect(analyser);
    analyser.connect(proc);
    proc.connect(ctx.destination);
    startWaveform();
  }, [startWaveform]);

  // ── cleanup ──
  const cleanup = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    wsRef.current?.close();
    streamRef.current?.getTracks().forEach(t => t.stop());
    procRef.current?.disconnect();
    audioCtxRef.current?.close().catch(() => {});
    playing.current = false;
    audioQ.current  = [];
    setBars(Array(40).fill(0));
    setAiSpeaks(false);
  }, []);

  const endSession = useCallback(() => {
    cleanup();
    setStatus('ended');
  }, [cleanup]);

  // ── connect web ──
  const startWeb = useCallback(async () => {
    setStatus('connecting');
    setMessages([]);
    setRecap(null);
    const url = `ws://localhost:8000/ws/voice/?jd=${encodeURIComponent(jd)}&name=${encodeURIComponent(name)}&phone=${encodeURIComponent(phone)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = async () => { setStatus('connected'); await startMic(); };

    ws.onmessage = async (e) => {
      if (typeof e.data === 'string') {
        const d = jsonTry(e.data);
        if (d.type === 'transcript') {
          setMessages(prev => [...prev, { role: d.role, text: d.text, time: nowTime() }]);
        } else if (d.type === 'interrupt') {
          audioQ.current = []; setAiSpeaks(false);
        } else if (d.type === 'recap') {
          setRecap(d.data); cleanup(); setStatus('ended');
        }
      } else {
        const ab = await e.data.arrayBuffer();
        audioQ.current.push(ab);
        if (!playing.current) playNext();
      }
    };

    ws.onclose = () => { if (wsRef.current) { cleanup(); setStatus(s => s === 'connected' ? 'ended' : s); } };
    ws.onerror = () => { cleanup(); setStatus('idle'); };
  }, [jd, name, phone, startMic, cleanup, playNext]);

  // ── outbound call ──
  const triggerCall = useCallback(async () => {
    setStatus('connecting');
    try {
      const r = await fetch('http://localhost:8000/api/call/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, jd, name }),
      });
      const res = await r.json();
      if (res.status === 'success') {
        setMessages([{ role: 'system', text: `Outbound call initiated → ${name || phone} · SID ${res.call_sid}`, time: nowTime() }]);
        setStatus('connected');
      } else { alert(res.message); setStatus('idle'); }
    } catch { alert('Backend unreachable.'); setStatus('idle'); }
  }, [phone, jd, name]);

  // ── parse recap ──
  const report = recap ? (() => {
    const d = jsonTry(recap.reason || '{}');
    return { ...d, score: recap.score ?? d.intent_score };
  })() : null;

  const isIdle  = status === 'idle';
  const isLive  = status === 'connected';
  const isBusy  = status === 'connecting';
  const isDone  = status === 'ended';

  return (
    <div className="min-h-screen flex flex-col">

      {/* ── Aurora orbs ── */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[15%] w-[600px] h-[600px] rounded-full opacity-[0.12]"
          style={{ background: 'radial-gradient(circle, #6366f1 0%, transparent 70%)', animation: 'drift1 14s ease-in-out infinite' }} />
        <div className="absolute bottom-[-15%] right-[10%] w-[700px] h-[700px] rounded-full opacity-[0.10]"
          style={{ background: 'radial-gradient(circle, #8b5cf6 0%, transparent 70%)', animation: 'drift2 18s ease-in-out infinite' }} />
        <div className="absolute top-[40%] right-[30%] w-[400px] h-[400px] rounded-full opacity-[0.07]"
          style={{ background: 'radial-gradient(circle, #3b82f6 0%, transparent 70%)', animation: 'drift3 10s ease-in-out infinite' }} />
        <div className="absolute inset-0" style={{ background: 'radial-gradient(ellipse at 50% 0%, rgba(99,102,241,0.04) 0%, transparent 60%)' }} />
      </div>

      {/* ── Header ── */}
      <header className="glass-nav sticky top-0 z-20 flex items-center justify-between px-6 py-3.5">
        <div className="flex items-center gap-3">
          <div className="relative w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 16px rgba(99,102,241,0.35)' }}>
            <Zap size={15} className="text-white" fill="white" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight leading-none text-white">Project Vox</h1>
            <p className="text-[10px] text-slate-500 mt-0.5 leading-none">AI-Powered HR Screening</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {isLive && (
            <span className="text-xs font-mono text-slate-400 tabular-nums">{fmt(elapsed)}</span>
          )}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-[11px] font-medium border"
            style={{ animation: (isLive || isBusy) ? 'statusPop 0.3s ease-out' : 'none',
              background: isLive ? 'rgba(52,211,153,0.08)' : isBusy ? 'rgba(251,191,36,0.08)' : isDone ? 'rgba(100,116,139,0.08)' : 'rgba(255,255,255,0.04)',
              borderColor: isLive ? 'rgba(52,211,153,0.2)' : isBusy ? 'rgba(251,191,36,0.2)' : isDone ? 'rgba(100,116,139,0.2)' : 'rgba(255,255,255,0.08)',
              color: isLive ? '#34d399' : isBusy ? '#fbbf24' : isDone ? '#94a3b8' : '#64748b',
            }}>
            <span className="w-1.5 h-1.5 rounded-full inline-block mr-1"
              style={{ background: isLive ? '#34d399' : isBusy ? '#fbbf24' : isDone ? '#475569' : '#334155',
                animation: (isLive || isBusy) ? 'pulse 2s infinite' : 'none' }} />
            {isLive ? 'Session Live' : isBusy ? 'Connecting…' : isDone ? 'Session Ended' : 'Ready'}
          </div>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="flex-1 grid grid-cols-12 gap-4 p-4 max-w-[1440px] w-full mx-auto">

        {/* ═══ LEFT: Setup ═══ */}
        <aside className="col-span-12 lg:col-span-3 flex flex-col gap-3">

          {/* JD */}
          <div className="glass rounded-2xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <Briefcase size={13} className="text-indigo-400" />
              <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Job Description</span>
            </div>
            <textarea
              rows={8}
              className="glass-input w-full rounded-xl p-3.5 text-[13px] text-slate-300 placeholder-slate-600 resize-none"
              placeholder="Paste the Job Description here…"
              value={jd}
              onChange={e => setJd(e.target.value)}
              disabled={isLive}
            />
          </div>

          {/* Candidate */}
          <div className="glass rounded-2xl p-5 space-y-2.5">
            <div className="flex items-center gap-2 mb-1">
              <User size={13} className="text-indigo-400" />
              <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Candidate</span>
            </div>
            <div className="relative">
              <User size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-600" />
              <input type="text"
                className="glass-input w-full rounded-xl py-2.5 pl-9 pr-4 text-[13px] text-slate-300 placeholder-slate-600"
                placeholder="Full name"
                value={name} onChange={e => setName(e.target.value)} disabled={isLive} />
            </div>
            <div className="relative">
              <Phone size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-600" />
              <input type="text"
                className="glass-input w-full rounded-xl py-2.5 pl-9 pr-4 text-[13px] text-slate-300 placeholder-slate-600 font-mono"
                placeholder="+91 XXXXX XXXXX"
                value={phone} onChange={e => setPhone(e.target.value)} disabled={isLive} />
            </div>
          </div>

          {/* Actions */}
          <div className="space-y-2">
            {isLive ? (
              <button onClick={endSession}
                className="btn-danger w-full py-3 rounded-xl text-rose-400 text-sm font-semibold flex items-center justify-center gap-2">
                <Square size={15} fill="currentColor" />
                End Session
              </button>
            ) : (
              <>
                <button onClick={startWeb} disabled={isBusy}
                  className="btn-primary w-full py-3 rounded-xl text-white text-sm font-semibold flex items-center justify-center gap-2">
                  {isBusy ? <Loader2 size={15} className="animate-spin" /> : <Mic size={15} />}
                  {isBusy ? 'Initializing…' : 'Start Web Session'}
                </button>
                <button onClick={triggerCall} disabled={isBusy || !phone || phone === '+91'}
                  className="btn-ghost w-full py-3 rounded-xl text-slate-300 text-sm font-semibold flex items-center justify-center gap-2">
                  <PhoneCall size={15} />
                  Trigger Outbound Call
                </button>
              </>
            )}
            {isDone && (
              <button
                onClick={() => { setStatus('idle'); setMessages([]); setRecap(null); }}
                className="btn-ghost w-full py-2.5 rounded-xl text-slate-500 text-xs font-medium flex items-center justify-center gap-2">
                ↺ New Session
              </button>
            )}
          </div>

          {/* Provider badge */}
          <div className="glass rounded-2xl p-4">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-2.5">AI Stack</p>
            <div className="space-y-1.5">
              {[
                { label: 'STT', value: 'Deepgram nova-2 · Hinglish', active: true },
                { label: 'LLM', value: 'Groq llama-3.3-70b', active: true },
                { label: 'TTS', value: 'Sarvam → ElevenLabs → DG', active: true },
              ].map(({ label, value, active }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-[10px] font-medium text-slate-600">{label}</span>
                  <span className={`text-[10px] font-medium ${active ? 'text-indigo-400' : 'text-slate-600'}`}>{value}</span>
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* ═══ CENTER: Chat ═══ */}
        <section className="col-span-12 lg:col-span-6">
          <div className="glass rounded-2xl flex flex-col" style={{ minHeight: 640 }}>

            {/* Chat header */}
            <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
              <div className="flex items-center gap-2">
                <MessageSquare size={14} className="text-indigo-400" />
                <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Live Screening Log</span>
              </div>
              {aiSpeaks && (
                <div className="flex items-center gap-2.5">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-indigo-400">Vox Speaking</span>
                  <div className="flex items-end gap-[2.5px]" style={{ height: 18 }}>
                    {Array.from({ length: 5 }, (_, i) => (
                      <div key={i} className="w-[3px] rounded-full bg-indigo-400"
                        style={{ height: '100%', transformOrigin: 'bottom',
                          animation: `voxBar 0.7s ease-in-out ${i * 0.1}s infinite` }} />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5 scrollbar-hide">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center gap-4 opacity-25 select-none"
                  style={{ minHeight: 320 }}>
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                    style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))', border: '1px solid rgba(99,102,241,0.15)' }}>
                    <Zap size={24} className="text-indigo-400" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-medium text-slate-400">Ready to Screen</p>
                    <p className="text-xs text-slate-600 mt-1">Configure the role and start a session.</p>
                  </div>
                </div>
              ) : (
                messages.map((m, i) => {
                  if (m.role === 'system') {
                    return (
                      <div key={i} className="flex justify-center msg-in">
                        <div className="text-[11px] text-slate-600 italic px-4 py-1.5 rounded-full"
                          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                          {m.text}
                        </div>
                      </div>
                    );
                  }
                  const isVox = m.role === 'vox';
                  return (
                    <div key={i} className={`flex gap-2.5 msg-in ${isVox ? '' : 'flex-row-reverse'}`}>
                      {/* Avatar */}
                      <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-[11px] font-bold mt-0.5"
                        style={{
                          background: isVox
                            ? 'linear-gradient(135deg, rgba(99,102,241,0.3), rgba(139,92,246,0.3))'
                            : 'rgba(255,255,255,0.07)',
                          border: isVox ? '1px solid rgba(99,102,241,0.25)' : '1px solid rgba(255,255,255,0.1)',
                          color: isVox ? '#a5b4fc' : '#94a3b8',
                        }}>
                        {isVox ? 'V' : (name?.[0]?.toUpperCase() || 'C')}
                      </div>

                      <div className="max-w-[76%]">
                        {/* Name + time */}
                        <div className={`flex items-baseline gap-2 mb-1 ${isVox ? '' : 'flex-row-reverse'}`}>
                          <span className="text-[10px] font-semibold" style={{ color: isVox ? '#818cf8' : '#94a3b8' }}>
                            {isVox ? 'Vox' : (name || 'Candidate')}
                          </span>
                          <span className="text-[9px] text-slate-700">{m.time}</span>
                        </div>

                        {/* Bubble */}
                        <div className="px-4 py-2.5 rounded-2xl text-sm leading-relaxed"
                          style={isVox ? {
                            background: 'rgba(255,255,255,0.04)',
                            border: '1px solid rgba(255,255,255,0.07)',
                            color: '#cbd5e1',
                            borderTopLeftRadius: 4,
                          } : {
                            background: 'linear-gradient(135deg, rgba(99,102,241,0.6), rgba(139,92,246,0.5))',
                            border: '1px solid rgba(139,92,246,0.3)',
                            color: '#ffffff',
                            borderTopRightRadius: 4,
                          }}>
                          {m.text}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={endRef} />
            </div>

            {/* Waveform */}
            <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
              <div className="flex items-center gap-1.5 mb-2.5">
                <div className="w-1.5 h-1.5 rounded-full"
                  style={{ background: isLive ? '#34d399' : '#334155', animation: isLive ? 'pulse 2s infinite' : 'none' }} />
                <span className="text-[10px] font-medium text-slate-700">
                  {isLive ? 'Microphone Active' : 'Microphone Idle'}
                </span>
              </div>
              <div className="flex items-end justify-between gap-[2px]" style={{ height: 40 }}>
                {bars.map((lvl, i) => (
                  <div key={i} className="flex-1 rounded-full transition-all duration-75"
                    style={{
                      height: `${Math.max(3, lvl * 40)}px`,
                      background: lvl > 0.5
                        ? 'linear-gradient(to top, #6366f1, #a78bfa)'
                        : 'linear-gradient(to top, #3730a3, #6366f1)',
                      opacity: 0.35 + lvl * 0.65,
                    }} />
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ═══ RIGHT: Info / Scorecard ═══ */}
        <aside className="col-span-12 lg:col-span-3 space-y-3 overflow-y-auto scrollbar-hide"
          style={{ maxHeight: 'calc(100vh - 5rem)' }}>

          {!report ? (
            /* Session Info */
            <>
              <div className="glass rounded-2xl p-5 space-y-4">
                <div className="flex items-center gap-2">
                  <Activity size={13} className="text-indigo-400" />
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Session</span>
                </div>
                <div className="space-y-2.5">
                  <InfoRow label="Status" value={
                    isLive ? <Chip color="emerald">Live</Chip> :
                    isBusy ? <Chip color="amber">Connecting</Chip> :
                    isDone ? <Chip color="slate">Ended</Chip>    :
                    <span className="text-slate-700 text-[11px]">—</span>
                  } />
                  {isLive && <InfoRow label="Duration" value={<span className="text-[11px] font-mono text-indigo-400 tabular-nums">{fmt(elapsed)}</span>} />}
                  <InfoRow label="Candidate" value={<span className="text-[11px] text-slate-300 truncate max-w-[120px]">{name || '—'}</span>} />
                  <InfoRow label="Channel" value={<span className="text-[11px] text-slate-400">{phone && phone !== '+91' ? 'Outbound' : 'Web'}</span>} />
                </div>
              </div>

              <div className="glass rounded-2xl p-5">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-3">Screening Goals</p>
                <ul className="space-y-2">
                  {[
                    'Confirm interest & availability',
                    'Verify 2-3 key technical skills',
                    'Capture salary expectation (LPA)',
                    'Note period / joining date',
                    'Cultural fit (1-10 internal)',
                  ].map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-[12px] text-slate-500">
                      <span className="text-indigo-500 mt-0.5 text-[10px] leading-none flex-shrink-0">▸</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="glass rounded-2xl p-5">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-3">Language Support</p>
                <div className="flex flex-wrap gap-1.5">
                  {['English', 'Hindi', 'Hinglish'].map((l, i) => (
                    <span key={l} className="text-[11px] px-2.5 py-1 rounded-lg font-medium"
                      style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', color: '#a5b4fc' }}>
                      {l}
                    </span>
                  ))}
                </div>
                <p className="text-[11px] text-slate-600 mt-2.5 leading-relaxed">
                  Vox mirrors the candidate's language automatically — Indian accent via Sarvam AI.
                </p>
              </div>
            </>
          ) : (
            /* Scorecard */
            <Scorecard report={report} name={name} />
          )}
        </aside>
      </main>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] text-slate-600 flex-shrink-0">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function Chip({ color = 'slate', children }) {
  const map = {
    emerald: { bg: 'rgba(52,211,153,0.1)', border: 'rgba(52,211,153,0.2)', color: '#34d399' },
    amber:   { bg: 'rgba(251,191,36,0.1)', border: 'rgba(251,191,36,0.2)',  color: '#fbbf24' },
    rose:    { bg: 'rgba(248,113,113,0.1)',border: 'rgba(248,113,113,0.2)', color: '#f87171' },
    slate:   { bg: 'rgba(100,116,139,0.1)',border: 'rgba(100,116,139,0.2)', color: '#94a3b8' },
    indigo:  { bg: 'rgba(99,102,241,0.1)', border: 'rgba(99,102,241,0.2)',  color: '#818cf8' },
  };
  const s = map[color] || map.slate;
  return (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md"
      style={{ background: s.bg, border: `1px solid ${s.border}`, color: s.color }}>
      {children}
    </span>
  );
}

function Scorecard({ report, name }) {
  const outcome = OUTCOME[report.call_outcome] || OUTCOME.CONFUSED;
  const OutIcon = outcome.Icon;
  const score   = typeof report.score === 'number' ? report.score : null;

  return (
    <div className="space-y-3" style={{ animation: 'scoreDrop 0.4s ease-out' }}>

      {/* Hero: score + outcome */}
      <div className="glass rounded-2xl p-5">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-4">Screening Report</p>

        <div className="flex items-center gap-4 mb-4">
          {/* Score ring */}
          <div className="relative w-[72px] h-[72px] flex-shrink-0 rounded-2xl flex flex-col items-center justify-center"
            style={{ background: `radial-gradient(circle at 50% 50%, ${scoreGlow(score)}, transparent 70%)`,
              border: `1px solid ${scoreGlow(score).replace('0.2', '0.4')}` }}>
            <span className="text-3xl font-black leading-none" style={{ color: scoreColor(score) }}>
              {score ?? '—'}
            </span>
            <span className="text-[9px] text-slate-600 font-medium mt-0.5">/10</span>
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-[10px] text-slate-600 mb-2">Call Outcome</p>
            <div className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-semibold ${outcome.cls}`}>
              <OutIcon size={11} />
              {outcome.label}
            </div>
          </div>
        </div>

        {report.vibe_check && (
          <blockquote className="text-[12px] text-slate-400 italic leading-relaxed border-l-2 pl-3"
            style={{ borderColor: 'rgba(99,102,241,0.35)' }}>
            "{report.vibe_check}"
          </blockquote>
        )}
      </div>

      {/* Key metrics */}
      {(report.salary_expectation_lpa || report.notice_period_days || report.joining_timeline) && (
        <div className="glass rounded-2xl p-5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-3">Key Metrics</p>
          <div className="grid grid-cols-2 gap-2">
            {report.salary_expectation_lpa && (
              <MetricTile label="Salary" value={`${report.salary_expectation_lpa} LPA`} />
            )}
            {report.notice_period_days && (
              <MetricTile label="Notice" value={`${report.notice_period_days} days`} />
            )}
            {report.joining_timeline && (
              <MetricTile label="Joining" value={report.joining_timeline} wide />
            )}
          </div>
        </div>
      )}

      {/* Verified skills */}
      {report.skills_verified?.length > 0 && (
        <div className="glass rounded-2xl p-5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-3">Verified Skills</p>
          <div className="flex flex-wrap gap-1.5">
            {report.skills_verified.map((s, i) => (
              <span key={i} className="text-[11px] px-2.5 py-1 rounded-lg font-medium"
                style={{ background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.18)', color: '#6ee7b7' }}>
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Summary bullets */}
      {report.summary_bullets?.length > 0 && (
        <div className="glass rounded-2xl p-5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-3">Summary</p>
          <ul className="space-y-2">
            {report.summary_bullets.map((b, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] text-slate-400 leading-relaxed">
                <span className="text-indigo-500 mt-0.5 flex-shrink-0">·</span>
                {b}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Live notes */}
      {report.live_notes && Object.keys(report.live_notes).length > 0 && (
        <div className="glass rounded-2xl p-5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-3">Captured Notes</p>
          <div className="space-y-2">
            {Object.entries(report.live_notes).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-slate-600 capitalize">{k.replace(/_/g, ' ')}</span>
                <span className="text-[11px] font-medium text-slate-300 truncate max-w-[120px]">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* HR flags */}
      {report.hr_flags?.length > 0 && (
        <div className="glass rounded-2xl p-5"
          style={{ borderColor: 'rgba(251,191,36,0.15)', background: 'rgba(251,191,36,0.03)' }}>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-amber-600/70 mb-3 flex items-center gap-1.5">
            <AlertTriangle size={10} /> HR Flags
          </p>
          <ul className="space-y-2">
            {report.hr_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] leading-relaxed"
                style={{ color: 'rgba(251,191,36,0.6)' }}>
                <span className="flex-shrink-0 mt-0.5">·</span>
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MetricTile({ label, value, wide }) {
  return (
    <div className={`rounded-xl p-3 ${wide ? 'col-span-2' : ''}`}
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <p className="text-[10px] text-slate-600 mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-slate-200">{value}</p>
    </div>
  );
}
