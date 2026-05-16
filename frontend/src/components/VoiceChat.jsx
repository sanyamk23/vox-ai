import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Phone, Mic, Square, Activity, Briefcase, User,
  PhoneCall, CheckCircle, XCircle, AlertTriangle,
  MessageSquare, Loader2, Zap, Clock, Sparkles,
} from 'lucide-react';

// ── Outcome config (light-theme safe colours) ─────────────────────────────────
const OUTCOME = {
  INTERESTED:         { label: 'Interested',         cls: 'text-emerald-700 bg-emerald-50 border-emerald-200', Icon: CheckCircle },
  CALLBACK_REQUESTED: { label: 'Callback Requested', cls: 'text-indigo-700  bg-indigo-50  border-indigo-200',  Icon: Phone },
  BUSY:               { label: 'Busy',               cls: 'text-amber-700   bg-amber-50   border-amber-200',   Icon: Clock },
  NOT_INTERESTED:     { label: 'Not Interested',     cls: 'text-red-700     bg-red-50     border-red-200',     Icon: XCircle },
  CONFUSED:           { label: 'Unclear',            cls: 'text-slate-600   bg-slate-100  border-slate-200',   Icon: AlertTriangle },
};
const scoreColor = (s) => s >= 8 ? '#059669' : s >= 5 ? '#d97706' : '#dc2626';
const scoreBg    = (s) => s >= 8 ? 'rgba(16,185,129,0.08)' : s >= 5 ? 'rgba(245,158,11,0.08)' : 'rgba(239,68,68,0.08)';
const scoreBd    = (s) => s >= 8 ? 'rgba(16,185,129,0.22)' : s >= 5 ? 'rgba(245,158,11,0.22)' : 'rgba(239,68,68,0.22)';

// ── Backend URLs (override via VITE_API_BASE_URL in .env) ────────────────────
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const WS_BASE  = API_BASE.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://');

// ── Utilities ─────────────────────────────────────────────────────────────────
const jsonTry = (s) => { try { return JSON.parse(s); } catch { return {}; } };
const nowTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const fmt     = (s) => `${String(Math.floor(s / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`;

function floatTo16BitPCM(input) {
  const buf  = new ArrayBuffer(input.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return buf;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function VoiceChat() {
  const [status,   setStatus]   = useState('idle');
  const [messages, setMessages] = useState([]);
  const [recap,    setRecap]    = useState(null);
  const [jd,       setJd]       = useState('We are looking for a Senior Software Engineer proficient in React and Django.');
  const [phone,    setPhone]    = useState('+91');
  const [name,     setName]     = useState('');
  const [bars,     setBars]     = useState(Array(40).fill(0));
  const [aiSpeaks, setAiSpeaks] = useState(false);
  const [elapsed,  setElapsed]  = useState(0);

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

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  useEffect(() => {
    if (status === 'connected') {
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);
    } else {
      clearInterval(timerRef.current);
      if (status === 'idle') setElapsed(0);
    }
    return () => clearInterval(timerRef.current);
  }, [status]);

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

  const playNext = useCallback(async () => {
    if (!audioQ.current.length) { playing.current = false; setAiSpeaks(false); return; }
    playing.current = true; setAiSpeaks(true);
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

  const startMic = useCallback(async () => {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      alert('Microphone access denied. Please allow microphone access and try again.');
      cleanup();
      setStatus('idle');
      return;
    }
    streamRef.current = stream;
    const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    audioCtxRef.current = ctx;
    const source  = ctx.createMediaStreamSource(stream);
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

  const endSession = useCallback(() => { cleanup(); setStatus('ended'); }, [cleanup]);

  const startWeb = useCallback(async () => {
    setStatus('connecting'); setMessages([]); setRecap(null);
    const url = `${WS_BASE}/ws/voice/?jd=${encodeURIComponent(jd)}&name=${encodeURIComponent(name)}&phone=${encodeURIComponent(phone)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen    = async () => { setStatus('connected'); await startMic(); };
    ws.onmessage = async (e) => {
      if (typeof e.data === 'string') {
        const d = jsonTry(e.data);
        if      (d.type === 'transcript') setMessages(prev => [...prev, { role: d.role, text: d.text, time: nowTime() }]);
        else if (d.type === 'interrupt')  { audioQ.current = []; setAiSpeaks(false); }
        else if (d.type === 'recap')      { setRecap(d.data); cleanup(); setStatus('ended'); }
      } else {
        const ab = await e.data.arrayBuffer();
        audioQ.current.push(ab);
        if (!playing.current) playNext();
      }
    };
    ws.onclose = () => { if (wsRef.current) { cleanup(); setStatus(s => s === 'connected' ? 'ended' : s); } };
    ws.onerror = () => { cleanup(); setStatus('idle'); };
  }, [jd, name, phone, startMic, cleanup, playNext]);

  const triggerCall = useCallback(async () => {
    setStatus('connecting');
    try {
      const r   = await fetch(`${API_BASE}/api/call/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, jd, name }),
      });
      const res = await r.json();
      if (res.status === 'success') {
        setMessages([{ role: 'system', text: `Outbound call initiated → ${name || phone} · SID ${res.call_sid}`, time: nowTime() }]);
        setStatus('connected');
      } else { alert(res.message); setStatus('idle'); }
    } catch { alert('Backend unreachable.'); setStatus('idle'); }
  }, [phone, jd, name]);

  const report = recap ? (() => {
    const d = jsonTry(recap.reason || '{}');
    return { ...d, score: recap.score ?? d.intent_score };
  })() : null;

  const isIdle = status === 'idle';
  const isLive = status === 'connected';
  const isBusy = status === 'connecting';
  const isDone = status === 'ended';

  // ── Status pill config ──────────────────────────────────────────────────────
  const pill = isLive
    ? { bg: '#f0fdf4', bd: '#bbf7d0', tx: '#16a34a', dot: '#22c55e', label: 'Session Live',  pulse: true }
    : isBusy
    ? { bg: '#fffbeb', bd: '#fde68a', tx: '#b45309', dot: '#f59e0b', label: 'Connecting…',   pulse: true }
    : isDone
    ? { bg: '#f8fafc', bd: '#e2e8f0', tx: '#64748b', dot: '#94a3b8', label: 'Session Ended', pulse: false }
    : { bg: '#f8fafc', bd: '#e2e8f0', tx: '#94a3b8', dot: '#cbd5e1', label: 'Ready',         pulse: false };

  return (
    <div className="min-h-screen flex flex-col">

      {/* ── Ambient orbs (very subtle in light mode) ── */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none" aria-hidden>
        <div className="absolute -top-[10%] left-[5%]  w-[800px] h-[800px] rounded-full opacity-60"
          style={{ background: 'radial-gradient(circle, rgba(199,210,254,0.55) 0%, transparent 65%)', animation: 'drift1 16s ease-in-out infinite' }} />
        <div className="absolute -bottom-[15%] right-[5%] w-[900px] h-[900px] rounded-full opacity-50"
          style={{ background: 'radial-gradient(circle, rgba(221,214,254,0.50) 0%, transparent 65%)', animation: 'drift2 20s ease-in-out infinite' }} />
        <div className="absolute top-[35%] right-[25%]  w-[500px] h-[500px] rounded-full opacity-40"
          style={{ background: 'radial-gradient(circle, rgba(186,230,253,0.45) 0%, transparent 65%)', animation: 'drift3 12s ease-in-out infinite' }} />
      </div>

      {/* ── Navigation ── */}
      <header className="glass-nav sticky top-0 z-30 flex items-center justify-between px-6 py-3">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 16px rgba(99,102,241,0.30)' }}>
            <Zap size={14} className="text-white" fill="white" />
          </div>
          <div>
            <h1 className="text-[13px] font-bold tracking-tight text-slate-900 leading-none">Project Vox</h1>
            <p  className="text-[10px] text-slate-400 mt-[3px] leading-none font-medium">AI-Powered HR Screening</p>
          </div>
        </div>

        {/* Right side */}
        <div className="flex items-center gap-4">
          {isLive && (
            <span className="text-[12px] font-mono font-semibold text-slate-500 tabular-nums tracking-tight">{fmt(elapsed)}</span>
          )}
          {/* Status pill */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-[11px] font-semibold border select-none"
            style={{
              background: pill.bg, borderColor: pill.bd, color: pill.tx,
              animation: (isLive || isBusy) ? 'statusPop 0.28s ease-out' : 'none',
            }}>
            <span className="w-[7px] h-[7px] rounded-full flex-shrink-0"
              style={{ background: pill.dot, animation: pill.pulse ? 'pulse-dot 2s ease-in-out infinite' : 'none' }} />
            {pill.label}
          </div>
        </div>
      </header>

      {/* ── Main grid ── */}
      <main className="flex-1 grid grid-cols-12 gap-4 p-4 max-w-[1440px] w-full mx-auto">

        {/* ═══ LEFT — Setup ═══ */}
        <aside className="col-span-12 lg:col-span-3 flex flex-col gap-3">

          {/* Job Description */}
          <section className="glass rounded-2xl p-5">
            <Label icon={<Briefcase size={12} />}>Job Description</Label>
            <textarea
              rows={8}
              className="glass-input w-full rounded-xl p-3.5 text-[13px] placeholder-slate-400 resize-none leading-relaxed mt-3"
              placeholder="Paste the job description here…"
              value={jd} onChange={e => setJd(e.target.value)} disabled={isLive}
            />
          </section>

          {/* Candidate */}
          <section className="glass rounded-2xl p-5">
            <Label icon={<User size={12} />}>Candidate</Label>
            <div className="space-y-2 mt-3">
              <div className="relative">
                <User size={12} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input type="text"
                  className="glass-input w-full rounded-xl py-2.5 pl-9 pr-3.5 text-[13px]"
                  placeholder="Full name"
                  value={name} onChange={e => setName(e.target.value)} disabled={isLive} />
              </div>
              <div className="relative">
                <Phone size={12} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input type="text"
                  className="glass-input w-full rounded-xl py-2.5 pl-9 pr-3.5 text-[13px] font-mono"
                  placeholder="+91 XXXXX XXXXX"
                  value={phone} onChange={e => setPhone(e.target.value)} disabled={isLive} />
              </div>
            </div>
          </section>

          {/* CTA buttons */}
          <div className="space-y-2">
            {isLive ? (
              <button onClick={endSession}
                className="btn-danger w-full py-[11px] rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
                <Square size={14} fill="currentColor" />
                End Session
              </button>
            ) : (
              <>
                <button onClick={startWeb} disabled={isBusy}
                  className="btn-primary w-full py-[11px] rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
                  {isBusy ? <Loader2 size={14} className="animate-spin" /> : <Mic size={14} />}
                  {isBusy ? 'Initializing…' : 'Start Web Session'}
                </button>
                <button onClick={triggerCall} disabled={isBusy || !phone || phone === '+91'}
                  className="btn-ghost w-full py-[11px] rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
                  <PhoneCall size={14} />
                  Trigger Outbound Call
                </button>
              </>
            )}
            {isDone && (
              <button onClick={() => { setStatus('idle'); setMessages([]); setRecap(null); }}
                className="btn-ghost w-full py-2.5 rounded-xl text-xs font-medium text-slate-500 flex items-center justify-center gap-1.5">
                ↺ New Session
              </button>
            )}
          </div>

          {/* AI Stack */}
          <section className="glass rounded-2xl p-5">
            <Label icon={<Sparkles size={12} />}>AI Stack</Label>
            <div className="mt-3 space-y-2">
              {[
                { label: 'STT', value: 'Deepgram nova-2 · Hinglish' },
                { label: 'LLM', value: 'Groq · llama-3.3-70b' },
                { label: 'TTS', value: 'Sarvam → ElevenLabs → DG' },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-400">{label}</span>
                  <span className="text-[11px] font-semibold text-indigo-600">{value}</span>
                </div>
              ))}
            </div>
          </section>
        </aside>

        {/* ═══ CENTER — Chat ═══ */}
        <section className="col-span-12 lg:col-span-6">
          <div className="glass rounded-2xl flex flex-col" style={{ minHeight: 640 }}>

            {/* Chat header */}
            <div className="px-5 py-4 flex items-center justify-between border-b border-black/[0.05]">
              <div className="flex items-center gap-2">
                <MessageSquare size={13} className="text-indigo-500" />
                <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                  Live Screening Log
                </span>
              </div>
              {aiSpeaks && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-indigo-600">Speaking</span>
                  <div className="flex items-end gap-[2px]" style={{ height: 16 }}>
                    {Array.from({ length: 5 }, (_, i) => (
                      <div key={i} className="w-[2.5px] rounded-full bg-indigo-500"
                        style={{ height: '100%', transformOrigin: 'bottom',
                          animation: `voxBar 0.7s ease-in-out ${i * 0.1}s infinite` }} />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5 scrollbar-hide">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center gap-4 select-none" style={{ minHeight: 340 }}>
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                    style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.10), rgba(139,92,246,0.10))', border: '1px solid rgba(99,102,241,0.14)' }}>
                    <Zap size={22} className="text-indigo-500" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-semibold text-slate-400">Ready to Screen</p>
                    <p className="text-xs text-slate-300 mt-1.5">Configure the role above and start a session.</p>
                  </div>
                </div>
              ) : (
                messages.map((m, i) => {
                  if (m.role === 'system') return (
                    <div key={i} className="flex justify-center msg-in">
                      <div className="text-[11px] text-slate-400 italic px-4 py-1.5 rounded-full"
                        style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.11)' }}>
                        {m.text}
                      </div>
                    </div>
                  );

                  const isVox = m.role === 'vox';
                  return (
                    <div key={i} className={`flex gap-2.5 msg-in ${isVox ? '' : 'flex-row-reverse'}`}>
                      {/* Avatar */}
                      <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-[11px] font-bold mt-0.5"
                        style={isVox
                          ? { background: 'linear-gradient(135deg, rgba(99,102,241,0.14), rgba(139,92,246,0.14))', border: '1px solid rgba(99,102,241,0.22)', color: '#6366f1' }
                          : { background: 'rgba(15,23,42,0.06)', border: '1px solid rgba(15,23,42,0.10)', color: '#475569' }
                        }>
                        {isVox ? 'V' : (name?.[0]?.toUpperCase() || 'C')}
                      </div>

                      <div className="max-w-[76%]">
                        {/* Meta */}
                        <div className={`flex items-baseline gap-2 mb-1.5 ${isVox ? '' : 'flex-row-reverse'}`}>
                          <span className="text-[11px] font-semibold" style={{ color: isVox ? '#6366f1' : '#475569' }}>
                            {isVox ? 'Vox' : (name || 'Candidate')}
                          </span>
                          <span className="text-[10px] text-slate-300">{m.time}</span>
                        </div>
                        {/* Bubble */}
                        <div className="px-4 py-3 rounded-2xl text-[13px] leading-relaxed"
                          style={isVox
                            ? { background: 'rgba(255,255,255,0.90)', border: '1px solid rgba(0,0,0,0.07)',
                                boxShadow: '0 2px 10px rgba(0,0,0,0.05)', color: '#334155', borderTopLeftRadius: 4 }
                            : { background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                                border: '1px solid rgba(99,102,241,0.25)',
                                boxShadow: '0 4px 16px rgba(99,102,241,0.25)', color: '#ffffff', borderTopRightRadius: 4 }
                          }>
                          {m.text}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={endRef} />
            </div>

            {/* Waveform footer */}
            <div className="px-5 pb-4 pt-3 border-t border-black/[0.05]">
              <div className="flex items-center gap-2 mb-2.5">
                <span className="w-[7px] h-[7px] rounded-full flex-shrink-0"
                  style={{ background: isLive ? '#22c55e' : '#cbd5e1', animation: isLive ? 'pulse-dot 2s ease-in-out infinite' : 'none' }} />
                <span className="text-[10px] font-medium text-slate-400">
                  {isLive ? 'Microphone Active' : 'Microphone Idle'}
                </span>
              </div>
              <div className="flex items-end justify-between gap-[2px]" style={{ height: 36 }}>
                {bars.map((lvl, i) => (
                  <div key={i} className="flex-1 rounded-full transition-all duration-75"
                    style={{
                      height: `${Math.max(2, lvl * 36)}px`,
                      background: lvl > 0.05
                        ? `linear-gradient(to top, #6366f1, #a78bfa)`
                        : '#e2e8f0',
                      opacity: lvl > 0.05 ? 0.45 + lvl * 0.55 : 1,
                    }} />
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ═══ RIGHT — Info / Scorecard ═══ */}
        <aside className="col-span-12 lg:col-span-3 space-y-3 overflow-y-auto scrollbar-hide"
          style={{ maxHeight: 'calc(100vh - 5rem)' }}>

          {!report ? (
            <>
              {/* Session info */}
              <section className="glass rounded-2xl p-5">
                <Label icon={<Activity size={12} />}>Session</Label>
                <div className="mt-3 space-y-3">
                  <InfoRow label="Status"
                    value={
                      isLive ? <Chip color="emerald">Live</Chip> :
                      isBusy ? <Chip color="amber">Connecting</Chip> :
                      isDone ? <Chip color="slate">Ended</Chip> :
                      <span className="text-[11px] text-slate-300">—</span>
                    } />
                  {isLive && (
                    <InfoRow label="Duration"
                      value={<span className="text-[12px] font-mono font-semibold text-indigo-600 tabular-nums">{fmt(elapsed)}</span>} />
                  )}
                  <InfoRow label="Candidate"
                    value={<span className="text-[12px] font-medium text-slate-600 truncate max-w-[110px]">{name || '—'}</span>} />
                  <InfoRow label="Channel"
                    value={<span className="text-[12px] text-slate-500">{phone && phone !== '+91' ? 'Outbound' : 'Web'}</span>} />
                </div>
              </section>

              {/* Screening goals */}
              <section className="glass rounded-2xl p-5">
                <Label icon={<CheckCircle size={12} />}>Screening Goals</Label>
                <ul className="mt-3 space-y-2">
                  {[
                    'Confirm interest & availability',
                    'Verify 2–3 key technical skills',
                    'Capture salary expectation (LPA)',
                    'Note period / joining date',
                    'Cultural fit (internal score)',
                  ].map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-[12px] text-slate-500 leading-snug">
                      <span className="text-indigo-400 mt-[1px] text-[10px] flex-shrink-0">▸</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </section>

              {/* Language */}
              <section className="glass rounded-2xl p-5">
                <Label icon={<MessageSquare size={12} />}>Languages</Label>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {['English', 'Hindi', 'Hinglish'].map((l) => (
                    <span key={l} className="text-[11px] font-semibold px-3 py-1 rounded-lg"
                      style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.16)', color: '#4f46e5' }}>
                      {l}
                    </span>
                  ))}
                </div>
                <p className="text-[11px] text-slate-400 mt-2.5 leading-relaxed">
                  Vox mirrors the candidate's language — Indian accent via Sarvam AI.
                </p>
              </section>
            </>
          ) : (
            <Scorecard report={report} name={name} />
          )}
        </aside>
      </main>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function Label({ icon, children }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-indigo-500">{icon}</span>
      <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400">{children}</span>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] text-slate-400 flex-shrink-0">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function Chip({ color = 'slate', children }) {
  const map = {
    emerald: { bg: '#f0fdf4', bd: '#bbf7d0', tx: '#16a34a' },
    amber:   { bg: '#fffbeb', bd: '#fde68a', tx: '#b45309' },
    rose:    { bg: '#fff1f2', bd: '#fecdd3', tx: '#e11d48' },
    slate:   { bg: '#f8fafc', bd: '#e2e8f0', tx: '#64748b' },
    indigo:  { bg: '#eef2ff', bd: '#c7d2fe', tx: '#4f46e5' },
  };
  const s = map[color] || map.slate;
  return (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md"
      style={{ background: s.bg, border: `1px solid ${s.bd}`, color: s.tx }}>
      {children}
    </span>
  );
}

function Scorecard({ report, name }) {
  const outcome = OUTCOME[report.call_outcome] || OUTCOME.CONFUSED;
  const OutIcon = outcome.Icon;
  const score   = typeof report.score === 'number' ? report.score : null;

  return (
    <div className="space-y-3" style={{ animation: 'scoreDrop 0.35s ease-out' }}>

      {/* Hero */}
      <section className="glass rounded-2xl p-5">
        <Label icon={<Activity size={12} />}>Screening Report</Label>

        <div className="flex items-center gap-4 mt-4 mb-4">
          {/* Score ring */}
          <div className="relative w-[72px] h-[72px] flex-shrink-0 rounded-2xl flex flex-col items-center justify-center"
            style={{ background: scoreBg(score), border: `1.5px solid ${scoreBd(score)}` }}>
            <span className="text-[30px] font-black leading-none" style={{ color: scoreColor(score) }}>
              {score ?? '—'}
            </span>
            <span className="text-[9px] text-slate-400 font-semibold mt-0.5">/10</span>
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-[10px] text-slate-400 mb-2 font-medium">Call Outcome</p>
            <div className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-semibold ${outcome.cls}`}>
              <OutIcon size={11} />
              {outcome.label}
            </div>
          </div>
        </div>

        {report.vibe_check && (
          <blockquote className="text-[12px] text-slate-500 italic leading-relaxed border-l-2 pl-3 mt-2"
            style={{ borderColor: 'rgba(99,102,241,0.30)' }}>
            "{report.vibe_check}"
          </blockquote>
        )}
      </section>

      {/* Key metrics */}
      {(report.salary_expectation_lpa || report.notice_period_days || report.joining_timeline) && (
        <section className="glass rounded-2xl p-5">
          <Label icon={<Activity size={12} />}>Key Metrics</Label>
          <div className="grid grid-cols-2 gap-2 mt-3">
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
        </section>
      )}

      {/* Verified skills */}
      {report.skills_verified?.length > 0 && (
        <section className="glass rounded-2xl p-5">
          <Label icon={<CheckCircle size={12} />}>Verified Skills</Label>
          <div className="flex flex-wrap gap-1.5 mt-3">
            {report.skills_verified.map((s, i) => (
              <span key={i} className="text-[11px] font-semibold px-2.5 py-1 rounded-lg"
                style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#059669' }}>
                {s}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Summary */}
      {report.summary_bullets?.length > 0 && (
        <section className="glass rounded-2xl p-5">
          <Label icon={<MessageSquare size={12} />}>Summary</Label>
          <ul className="space-y-2 mt-3">
            {report.summary_bullets.map((b, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] text-slate-600 leading-relaxed">
                <span className="text-indigo-400 mt-0.5 flex-shrink-0">·</span>
                {b}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Live notes */}
      {report.live_notes && Object.keys(report.live_notes).length > 0 && (
        <section className="glass rounded-2xl p-5">
          <Label icon={<Activity size={12} />}>Captured Notes</Label>
          <div className="space-y-2.5 mt-3">
            {Object.entries(report.live_notes).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-slate-400 capitalize">{k.replace(/_/g, ' ')}</span>
                <span className="text-[11px] font-semibold text-slate-700 truncate max-w-[110px]">{String(v)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* HR flags */}
      {report.hr_flags?.length > 0 && (
        <section className="glass rounded-2xl p-5"
          style={{ background: 'rgba(255,251,235,0.85)', borderColor: 'rgba(251,191,36,0.25)' }}>
          <div className="flex items-center gap-1.5 mb-3">
            <AlertTriangle size={12} className="text-amber-500" />
            <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-amber-600">HR Flags</span>
          </div>
          <ul className="space-y-2">
            {report.hr_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] text-amber-700 leading-relaxed">
                <span className="flex-shrink-0 mt-0.5">·</span>
                {f}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function MetricTile({ label, value, wide }) {
  return (
    <div className={`rounded-xl p-3 ${wide ? 'col-span-2' : ''}`}
      style={{ background: 'rgba(248,250,252,0.9)', border: '1px solid rgba(15,23,42,0.08)' }}>
      <p className="text-[10px] text-slate-400 mb-0.5 font-medium">{label}</p>
      <p className="text-[13px] font-bold text-slate-800">{value}</p>
    </div>
  );
}
