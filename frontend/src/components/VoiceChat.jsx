import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Phone, Activity, Briefcase, User,
  PhoneCall, CheckCircle, XCircle, AlertTriangle,
  MessageSquare, Loader2, Zap, Clock, Sparkles,
  Copy, TrendingUp, Heart, Package, Code2,
  MapPin, DollarSign, Calendar, Users, Building2,
  SlidersHorizontal, FileText, Upload, Mic, Square, BarChart3,
} from 'lucide-react';
import CallConsole from './CallConsole';

// ── Outcome config ─────────────────────────────────────────────────────────────
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
const confLabel  = (c) => c == null ? null : c >= 0.7 ? 'High' : c >= 0.4 ? 'Medium' : 'Low';
const confColor  = (c) => c == null ? '#94a3b8' : c >= 0.7 ? '#059669' : c >= 0.4 ? '#d97706' : '#dc2626';

const DIMS = [
  { key: 'technical_fit',  label: 'Technical',    Icon: Code2,         color: '#6366f1', bg: 'rgba(99,102,241,0.07)',  bd: 'rgba(99,102,241,0.18)' },
  { key: 'communication',  label: 'Communication', Icon: MessageSquare, color: '#8b5cf6', bg: 'rgba(139,92,246,0.07)', bd: 'rgba(139,92,246,0.18)' },
  { key: 'motivation_fit', label: 'Motivation',   Icon: Heart,         color: '#059669', bg: 'rgba(5,150,105,0.07)',  bd: 'rgba(5,150,105,0.18)' },
  { key: 'logistics_fit',  label: 'Logistics',    Icon: Package,       color: '#d97706', bg: 'rgba(217,119,6,0.07)',  bd: 'rgba(217,119,6,0.18)' },
];

function buildExportText(report, name) {
  const cf = report.overall_confidence;
  const lines = [
    '═══════════════════════════════════════',
    '           VOX SCREENING REPORT        ',
    '═══════════════════════════════════════',
    `Candidate  : ${name || 'Unknown'}`,
    `Score      : ${report.score ?? '—'}/10`,
    `Outcome    : ${OUTCOME[report.call_outcome]?.label ?? report.call_outcome ?? '—'}`,
    cf != null ? `Confidence : ${confLabel(cf)} (${Math.round(cf * 100)}%)` : '',
    '',
    report.vibe_check ? `"${report.vibe_check}"` : '',
    '',
    '─── Summary ────────────────────────────',
    ...(report.summary_bullets || []).map(b => `  • ${b}`),
    '',
    '─── Skills Verified ────────────────────',
    `  ${(report.skills_verified || []).join(', ') || 'None mentioned'}`,
    '',
    '─── Key Metrics ────────────────────────',
    report.salary_expectation_lpa != null ? `  Expected CTC : ${report.salary_expectation_lpa} LPA` : '',
    report.current_ctc_lpa != null        ? `  Current CTC  : ${report.current_ctc_lpa} LPA`        : '',
    report.notice_period_days != null     ? `  Notice Period: ${report.notice_period_days} days`     : '',
    report.joining_timeline               ? `  Joining      : ${report.joining_timeline}`            : '',
    report.other_offers != null           ? `  Other Offers : ${report.other_offers ? 'Yes' : 'No'}` : '',
    '',
    '─── Dimension Scores ───────────────────',
    ...DIMS.map(d => {
      const dim = report[d.key];
      return dim ? `  ${d.label.padEnd(14)}: ${dim.score}/10 (confidence ${Math.round((dim.confidence ?? 0) * 100)}%)` : '';
    }).filter(Boolean),
    '',
    ...(report.hr_flags?.length ? [
      '─── HR Flags ───────────────────────────',
      ...(report.hr_flags || []).map(f => `  ⚠  ${f}`),
      '',
    ] : []),
    ...(report.recommended_next_step ? [
      '─── Recommended Action ─────────────────',
      `  ${report.recommended_next_step}`,
      '',
    ] : []),
    '═══════════════════════════════════════',
  ].filter(l => l != null);
  return lines.join('\n');
}

// ── Backend URLs (override via VITE_API_BASE_URL in .env) ────────────────────
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const WS_BASE  = API_BASE.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://');

// ── Utilities ─────────────────────────────────────────────────────────────────
const jsonTry = (s) => { try { return JSON.parse(s); } catch { return {}; } };
const nowTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const fmt     = (s) => `${String(Math.floor(s / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`;


// ── Component ─────────────────────────────────────────────────────────────────
const WORK_LOCATION_OPTIONS = ['Hybrid', 'Onsite', 'WFH'];

const EMPTY_STRUCTURED = {
  job_title: '',
  company_overview: '',
  team_details: '',
  company_location: '',
  required_skills: '',
  years_of_experience: '',
  ctc_range: '',
  required_joining_timeline: '',
  work_location_type: '',
};

export default function VoiceChat() {
  const [status,           setStatus]          = useState('idle');
  const [messages,         setMessages]        = useState([]);
  const [recap,            setRecap]           = useState(null);
  const [jd,               setJd]              = useState('');
  const [phone,            setPhone]           = useState('+91');
  const [name,             setName]            = useState('');
  const [elapsed,          setElapsed]         = useState(0);
  const [resumeText,       setResumeText]      = useState('');
  const [resumeStatus,     setResumeStatus]    = useState('idle'); // idle | uploading | ready | error
  const [resumeFile,       setResumeFile]      = useState('');
  const [resumeError,      setResumeError]     = useState('');
  const [dragOver,         setDragOver]        = useState(false);
  const [inputMode,        setInputMode]       = useState('prompt');   // 'prompt' | 'structured'
  const [structuredFields, setStructuredFields] = useState(EMPTY_STRUCTURED);
  const [connectingType,   setConnectingType]  = useState(null);
  const [toast,            setToast]           = useState(null);

  const endRef       = useRef(null);
  const timerRef     = useRef(null);
  const fileInputRef = useRef(null);
  const pollRef      = useRef(null);
  const wsRef        = useRef(null);
  const callSidRef   = useRef(null);
  const [bars, setBars] = useState(Array(20).fill(0));

  const setSF = (key, val) => setStructuredFields(prev => ({ ...prev, [key]: val }));

  const showToast = useCallback((message, type = 'error') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

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



  const handleResumeFile = useCallback(async (file) => {
    if (!file) return;
    const fname = file.name.toLowerCase();
    if (!fname.endsWith('.pdf') && !fname.endsWith('.docx')) {
      setResumeStatus('error');
      setResumeError('Only PDF and DOCX files are supported');
      return;
    }
    setResumeFile(file.name);
    setResumeStatus('uploading');
    setResumeError('');
    const form = new FormData();
    form.append('resume', file);
    try {
      const r = await fetch(`${API_BASE}/api/upload-resume/`, { method: 'POST', body: form });
      const res = await r.json();
      if (res.status === 'success') {
        setResumeText(res.text);
        setResumeStatus('ready');
      } else {
        setResumeStatus('error');
        setResumeError(res.message || 'Upload failed');
      }
    } catch {
      setResumeStatus('error');
      setResumeError('Network error — check connection');
    }
  }, []);

  const clearResume = useCallback(() => {
    setResumeText('');
    setResumeStatus('idle');
    setResumeFile('');
    setResumeError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const cleanup = useCallback(() => {
    // Hang up the Twilio call so the phone actually stops ringing
    if (callSidRef.current) {
      fetch(`${API_BASE}/api/call/${callSidRef.current}/end/`, { method: 'POST' }).catch(() => {});
    }
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    // Keep polling so the evaluation scorecard still appears when it's ready
    setBars(Array(20).fill(0));
    setStatus('ended');
    setConnectingType(null);
  }, []);

  const startWeb = useCallback(async () => {
    if (!name) { showToast('Please enter a candidate name first'); return; }
    showToast('Web call coming soon — use phone call for now', 'info');
  }, [name, showToast]);

  const _startPolling = useCallback((callSid) => {
    clearInterval(pollRef.current);
    let attempts = 0;
    const MAX_ATTEMPTS = 60; // 5 minutes at 5s intervals
    pollRef.current = setInterval(async () => {
      attempts++;
      if (attempts > MAX_ATTEMPTS) { clearInterval(pollRef.current); return; }
      try {
        const r = await fetch(`${API_BASE}/api/session/${callSid}/`);
        if (r.status === 202) return; // call still live
        const data = await r.json();
        if (data.status === 'evaluating') {
          // Call has ended — transition UI immediately, keep polling for scorecard
          setStatus('ended');
        } else if (data.status === 'complete') {
          clearInterval(pollRef.current);
          const reason = JSON.stringify({ ...(data.notes || {}), candidate_summary: data.candidate_summary });
          setRecap({ score: data.score, reason });
          setStatus('ended');
        }
      } catch { /* network blip — keep polling */ }
    }, 5000);
  }, []);

  const triggerCall = useCallback(async () => {
    setStatus('connecting');
    setConnectingType('phone');
    try {
      let payload = { phone, name };

      if (inputMode === 'prompt') {
        payload.jd = jd || 'Software Engineer role';
      } else {
        // Build a synthetic JD for AI fallback parsing
        const sf = structuredFields;
        const parts = [
          sf.job_title         && `Role: ${sf.job_title}`,
          sf.company_overview  && `Company: ${sf.company_overview}`,
          sf.required_skills   && `Required Skills: ${sf.required_skills}`,
          sf.years_of_experience && `Experience: ${sf.years_of_experience}`,
          sf.company_location  && `Location: ${sf.company_location}`,
          sf.work_location_type && `Work Mode: ${sf.work_location_type}`,
          sf.ctc_range         && `CTC Range: ${sf.ctc_range}`,
          sf.required_joining_timeline && `Joining Timeline: ${sf.required_joining_timeline}`,
          sf.team_details      && `Team: ${sf.team_details}`,
          jd                   && `Additional Details: ${jd}`,
        ].filter(Boolean);
        payload.jd = parts.join('\n') || 'Software Engineer role';

        // Send structured fields as explicit overrides for the AI-parsed context
        const recruiter_inputs = {};
        ['company_overview', 'team_details', 'company_location', 'years_of_experience',
         'ctc_range', 'required_joining_timeline', 'work_location_type'].forEach(k => {
          if (sf[k]?.trim()) recruiter_inputs[k] = sf[k].trim();
        });
        if (Object.keys(recruiter_inputs).length) payload.recruiter_inputs = recruiter_inputs;
      }

      const r   = await fetch(`${API_BASE}/api/call/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, resume_text: resumeText }),
      });
      const res = await r.json();
      if (res.status === 'success') {
        const sid = res.call_sid;
        callSidRef.current = sid;
        setMessages([{ role: 'system', text: `Outbound call initiated → ${name || phone} · SID ${sid}`, time: nowTime() }]);
        setStatus('connected');
        // Poll for evaluation results — backend saves DB record after call ends
        _startPolling(sid);
      } else { alert(res.message); setStatus('idle'); setConnectingType(null); }
    } catch { alert('Backend unreachable.'); setStatus('idle'); setConnectingType(null); }
  }, [phone, jd, name, inputMode, structuredFields, resumeText, _startPolling]);

  const report = recap ? (() => {
    const d = jsonTry(recap.reason || '{}');
    return { ...d, score: recap.score ?? d.intent_score };
  })() : null;

  const isIdle  = status === 'idle';
  const isLive  = status === 'connected';
  const isBusy  = status === 'connecting';
  const isDone  = status === 'ended';

  if (isLive) {
    return (
      <CallConsole 
        name={name}
        phone={phone}
        elapsed={elapsed}
        messages={messages}
        endRef={endRef}
        onEnd={cleanup}
        bars={bars}
        fmt={fmt}
        status={status}
      />
    );
  }

  // ── Status pill config ──────────────────────────────────────────────────────
  const pill = isLive
    ? { bg: 'rgba(111,255,0,0.1)', bd: 'rgba(111,255,0,0.3)', tx: '#6FFF00', dot: '#6FFF00', label: 'SESSION ACTIVE', pulse: true }
    : isBusy
    ? { bg: 'rgba(255,255,255,0.1)', bd: 'rgba(255,255,255,0.2)', tx: '#EFF4FF', dot: '#EFF4FF', label: 'CONNECTING...',  pulse: true }
    : isDone
    ? { bg: 'rgba(255,255,255,0.05)', bd: 'rgba(255,255,255,0.1)', tx: 'rgba(239,244,255,0.5)', dot: 'rgba(239,244,255,0.3)', label: 'SESSION ENDED',  pulse: false }
    : { bg: 'rgba(255,255,255,0.05)', bd: 'rgba(255,255,255,0.1)', tx: '#EFF4FF', dot: 'rgba(239,244,255,0.5)', label: 'READY', pulse: false };

  return (
    <div className="relative min-h-screen bg-background text-cream overflow-hidden font-sans selection:bg-neon selection:text-background">
      {/* Texture Overlay */}
      <div 
        className="fixed inset-0 z-50 pointer-events-none mix-blend-lighten opacity-60"
        style={{ backgroundImage: 'url(/texture.png)', backgroundSize: 'cover', backgroundPosition: 'center' }}
      />
      
      {/* Background Video */}
      <div className="fixed inset-0 z-0 opacity-20">
        <video 
          className="absolute inset-0 w-full h-full object-cover"
          autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_151551_992053d1-3d3e-4b8c-abac-45f22158f411.mp4"
        />
        <div className="absolute inset-0 bg-background/40" />
      </div>
      {/* Texture Overlay */}
      <div 
        className="fixed inset-0 z-50 pointer-events-none mix-blend-lighten opacity-60"
        style={{ backgroundImage: 'url(/texture.png)', backgroundSize: 'cover', backgroundPosition: 'center' }}
      />
      
      {/* Background Video */}
      <div className="fixed inset-0 z-0 opacity-40">
        <video 
          className="absolute inset-0 w-full h-full object-cover"
          autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_045634_e1c98c76-1265-4f5c-882a-4276f2080894.mp4"
        />
        <div className="absolute inset-0 bg-background/60" />
      </div>

      {/* ── Navigation ── */}
      <header className="relative z-40 px-6 sm:px-12 py-6 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <div className="font-grotesk text-[20px] uppercase tracking-wide">
            Clarix.Ai
          </div>
          <span className="font-condiment text-neon text-[20px] ml-2 -rotate-2">screening</span>
        </Link>

        <nav className="hidden lg:flex liquid-glass rounded-[28px] px-12 py-4 items-center gap-10">
          {[
            { name: 'Home', path: '/' },
            { name: 'About', path: '/about' },
            { name: 'Features', path: '/features' },
            { name: 'Dashboard', path: '/dashboard' },
            { name: 'App', path: '/app' },
          ].map(link => (
            <Link key={link.name} to={link.path} className={`font-grotesk text-[13px] uppercase tracking-widest transition-colors ${link.path === '/app' ? 'text-neon' : 'hover:text-neon'}`}>
              {link.name}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-5">
          {isLive && (
            <span className="text-[14px] font-mono font-bold text-cream tabular-nums">{fmt(elapsed)}</span>
          )}
          <div className="flex items-center gap-2 px-4 py-1.5 rounded-full text-[11px] font-mono border select-none transition-colors backdrop-blur-sm"
            style={{ background: pill.bg, borderColor: pill.bd, color: pill.tx }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: pill.dot, animation: pill.pulse ? 'pulse-dot 2s ease-in-out infinite' : 'none' }} />
            {pill.label}
          </div>
        </div>
      </header>

      {/* ── Main Layout ── */}
      <main className="relative z-10 flex-1 w-full max-w-[1831px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 p-4 lg:p-6 overflow-hidden h-[calc(100vh-88px)]">

        {/* ═══ LEFT PANEL — Setup ═══ */}
        <aside className="col-span-12 lg:col-span-3 flex flex-col liquid-glass rounded-[32px] overflow-hidden">
          <div className="p-4 lg:p-5 flex-1 overflow-y-auto space-y-6 scrollbar-hide">
            
            <div className="space-y-1">
              <h2 className="font-grotesk uppercase text-[22px] leading-none">Role Info</h2>
              <p className="font-mono text-[11px] text-cream/50 uppercase">Configure AI Parameters</p>
            </div>

            {/* Input Mode Toggle */}
            <div className="flex p-1 bg-white/5 rounded-[16px] backdrop-blur-md">
              <button onClick={() => setInputMode('prompt')} className={`flex-1 py-2 text-[11px] font-mono uppercase transition-all rounded-[12px] ${inputMode === 'prompt' ? 'bg-white/20 text-cream shadow-sm' : 'text-cream/40 hover:text-cream/80'}`}>Freeform</button>
              <button onClick={() => setInputMode('structured')} className={`flex-1 py-2 text-[11px] font-mono uppercase transition-all rounded-[12px] ${inputMode === 'structured' ? 'bg-white/20 text-cream shadow-sm' : 'text-cream/40 hover:text-cream/80'}`}>Structured</button>
            </div>

            {inputMode === 'prompt' ? (
              <div className="space-y-2">
                <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Job Description</label>
                <textarea
                  rows={8}
                  className="w-full rounded-[16px] bg-white/5 border border-white/10 px-4 py-3 text-[13px] font-mono text-cream placeholder-cream/30 focus:outline-none focus:ring-1 focus:ring-neon transition-all resize-none backdrop-blur-md"
                  placeholder="Paste the full job description here..."
                  value={jd} onChange={e => setJd(e.target.value)} disabled={isLive}
                />
              </div>
            ) : (
              <div className="space-y-5">
                <div className="space-y-4">
                  <div className="space-y-1.5">
                    <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Job Title</label>
                    <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 px-4 py-2.5 text-[13px] font-mono text-cream placeholder-cream/30 focus:outline-none focus:ring-1 focus:ring-neon transition-all backdrop-blur-md"
                      placeholder="e.g. Senior Frontend Engineer" value={structuredFields.job_title} onChange={e => setSF('job_title', e.target.value)} disabled={isLive} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Required Skills</label>
                    <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 px-4 py-2.5 text-[13px] font-mono text-cream placeholder-cream/30 focus:outline-none focus:ring-1 focus:ring-neon transition-all backdrop-blur-md"
                      placeholder="e.g. React, Node.js, Typescript" value={structuredFields.required_skills} onChange={e => setSF('required_skills', e.target.value)} disabled={isLive} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Years Exp.</label>
                    <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 px-4 py-2.5 text-[13px] font-mono text-cream placeholder-cream/30 focus:outline-none focus:ring-1 focus:ring-neon transition-all backdrop-blur-md"
                      placeholder="e.g. 5+ Years" value={structuredFields.years_of_experience} onChange={e => setSF('years_of_experience', e.target.value)} disabled={isLive} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="font-mono text-[10px] text-neon uppercase tracking-wider">CTC Range</label>
                    <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 px-4 py-2.5 text-[13px] font-mono text-cream placeholder-cream/30 focus:outline-none focus:ring-1 focus:ring-neon transition-all backdrop-blur-md"
                      placeholder="e.g. 25-30 LPA" value={structuredFields.ctc_range} onChange={e => setSF('ctc_range', e.target.value)} disabled={isLive} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Location</label>
                    <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 px-4 py-2.5 text-[13px] font-mono text-cream placeholder-cream/30 focus:outline-none focus:ring-1 focus:ring-neon transition-all backdrop-blur-md"
                      placeholder="Bangalore" value={structuredFields.company_location} onChange={e => setSF('company_location', e.target.value)} disabled={isLive} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Joining</label>
                    <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 px-4 py-2.5 text-[13px] font-mono text-cream placeholder-cream/30 focus:outline-none focus:ring-1 focus:ring-neon transition-all backdrop-blur-md"
                      placeholder="Immediate" value={structuredFields.required_joining_timeline} onChange={e => setSF('required_joining_timeline', e.target.value)} disabled={isLive} />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Work Mode</label>
                  <div className="flex gap-2">
                    {WORK_LOCATION_OPTIONS.map(opt => {
                      const active = structuredFields.work_location_type === opt;
                      return (
                        <button key={opt} disabled={isLive} onClick={() => setSF('work_location_type', active ? '' : opt)}
                          className={`flex-1 py-2 rounded-[12px] text-[11px] font-mono uppercase transition-all backdrop-blur-md ${active ? 'bg-neon/20 border border-neon text-neon' : 'bg-white/5 border border-white/10 text-cream/50 hover:bg-white/10 hover:text-cream'}`}>
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            <div className="h-px bg-white/10" />

            <div className="space-y-4">
              <h3 className="font-grotesk uppercase text-[24px] leading-none">Candidate</h3>
              <div className="space-y-3">
                <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 py-3 px-4 text-[13px] font-mono text-cream focus:outline-none focus:ring-1 focus:ring-neon transition-all placeholder-cream/30 backdrop-blur-md"
                  placeholder="Full name" value={name} onChange={e => setName(e.target.value)} disabled={isLive} />
                <input type="text" className="w-full rounded-[16px] bg-white/5 border border-white/10 py-3 px-4 text-[13px] font-mono text-cream focus:outline-none focus:ring-1 focus:ring-neon transition-all placeholder-cream/30 backdrop-blur-md"
                  placeholder="+91 XXXXX XXXXX" value={phone} onChange={e => setPhone(e.target.value)} disabled={isLive} />
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="font-grotesk uppercase text-[24px] leading-none">Resume Context</h3>
              <div
                className="rounded-[16px] border border-white/10 transition-all cursor-pointer overflow-hidden group bg-white/5 backdrop-blur-md"
                style={{
                  borderColor: dragOver ? '#6FFF00' : resumeStatus === 'ready' ? '#6FFF00' : resumeStatus === 'error' ? '#ef4444' : 'rgba(255,255,255,0.1)',
                  background:  dragOver ? 'rgba(111,255,0,0.05)' : resumeStatus === 'ready' ? 'rgba(111,255,0,0.02)' : 'rgba(255,255,255,0.02)',
                }}
                onDragOver={(e) => { e.preventDefault(); if (!isLive) setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); if (!isLive) handleResumeFile(e.dataTransfer.files[0]); }}
                onClick={() => { if (!isLive && resumeStatus !== 'uploading') fileInputRef.current?.click(); }}
              >
                <input ref={fileInputRef} type="file" accept=".pdf,.docx" className="hidden" onChange={(e) => handleResumeFile(e.target.files[0])} />

                {resumeStatus === 'idle' && (
                  <div className="py-6 flex flex-col items-center gap-2 group-hover:bg-white/5 transition-colors">
                    <Upload size={16} className="text-cream/50" />
                    <p className="font-mono text-[11px] text-cream/50 uppercase">Drop PDF/DOCX here</p>
                  </div>
                )}

                {resumeStatus === 'uploading' && (
                  <div className="py-6 flex flex-col items-center gap-2">
                    <Loader2 size={16} className="text-neon animate-spin" />
                    <p className="font-mono text-[11px] text-neon uppercase">Parsing resume...</p>
                  </div>
                )}

                {resumeStatus === 'ready' && (
                  <div className="py-4 px-4 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-neon/20 flex items-center justify-center flex-shrink-0">
                      <CheckCircle size={14} className="text-neon" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-[11px] text-neon truncate">{resumeFile}</p>
                      <p className="font-mono text-[9px] text-neon/70 mt-0.5">{resumeText.length.toLocaleString()} chars</p>
                    </div>
                  </div>
                )}

                {resumeStatus === 'error' && (
                  <div className="py-4 px-4 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-red-500/20 flex items-center justify-center flex-shrink-0">
                      <XCircle size={14} className="text-red-400" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-[11px] text-red-400 leading-snug">{resumeError}</p>
                      <p className="font-mono text-[9px] text-red-400/70 mt-0.5">Click to try again</p>
                    </div>
                  </div>
                )}
              </div>
              {resumeStatus === 'ready' && (
                <button onClick={(e) => { e.stopPropagation(); clearResume(); }} className="w-full font-mono text-[10px] text-cream/40 hover:text-red-400 uppercase transition-colors text-left pl-1">
                  Remove attachment
                </button>
              )}
            </div>
            <div className="pb-4" />
          </div>

          {/* CTA Footer */}
          <div className="p-5 border-t border-white/10 bg-black/20 backdrop-blur-xl">
            {isLive ? (
              <div className="flex gap-2">
                <div className="flex-1 py-3.5 rounded-[16px] font-grotesk text-[20px] uppercase flex items-center justify-center gap-2 text-neon bg-neon/10 border border-neon/30 select-none">
                  {wsRef.current ? <Mic size={18} className="animate-pulse" /> : <PhoneCall size={18} className="animate-pulse" />}
                  Active Session
                </div>
                {wsRef.current && (
                  <button onClick={cleanup} className="bg-red-500/20 hover:bg-red-500 text-red-400 hover:text-white border border-red-500/50 hover:border-red-500 px-6 rounded-[16px] flex items-center justify-center transition-colors">
                    <Square size={16} fill="currentColor" />
                  </button>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <button onClick={startWeb} disabled={isBusy || !name}
                  className="w-full py-3.5 rounded-[16px] font-grotesk text-[24px] uppercase flex items-center justify-center gap-3 bg-neon text-background hover:bg-[#8aff2a] disabled:opacity-50 disabled:bg-white/10 disabled:text-cream/50 transition-colors shadow-[0_0_20px_rgba(111,255,0,0.2)]">
                  {isBusy && connectingType === 'web' ? <Loader2 size={18} className="animate-spin" /> : <Mic size={18} />}
                  {isBusy && connectingType === 'web' ? 'CONNECTING...' : 'START WEB CALL'}
                </button>
                <button onClick={triggerCall} disabled={isBusy || !phone || phone === '+91'}
                  className="w-full py-3.5 rounded-[16px] font-grotesk text-[20px] uppercase flex items-center justify-center gap-2 bg-transparent text-cream border border-cream/20 hover:bg-white/5 disabled:opacity-50 transition-colors">
                  {isBusy && connectingType === 'phone' ? <Loader2 size={16} className="animate-spin" /> : <PhoneCall size={16} />}
                  {isBusy && connectingType === 'phone' ? 'INITIATING...' : 'CALL PHONE'}
                </button>
              </div>
            )}
            {(isLive || isDone) && (
              <button onClick={() => { clearInterval(pollRef.current); callSidRef.current = null; setStatus('idle'); setMessages([]); setRecap(null); setElapsed(0); setJd(''); setStructuredFields(EMPTY_STRUCTURED); clearResume(); }}
                className="w-full mt-3 py-2 font-mono text-[10px] text-cream/40 hover:text-cream uppercase tracking-widest transition-colors">
                Start New Session
              </button>
            )}
          </div>
        </aside>

        {/* ═══ CENTER PANEL — Log ═══ */}
        <section className="col-span-12 lg:col-span-6 flex flex-col liquid-glass rounded-[32px] overflow-hidden relative">
          
          <div className="px-8 py-5 border-b border-white/10 flex items-center justify-between bg-white/5 backdrop-blur-md">
            <h2 className="font-grotesk uppercase text-[22px] leading-none">Transcript</h2>
            <MessageSquare size={16} className="text-cream/50" />
          </div>

          <div className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-4 lg:space-y-6 scrollbar-hide bg-black/20">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center gap-5 select-none opacity-80">
                <div className="w-16 h-16 rounded-[20px] liquid-glass flex items-center justify-center text-neon shadow-[0_0_30px_rgba(111,255,0,0.15)]">
                  <Sparkles size={24} />
                </div>
                <div className="text-center space-y-1">
                  <p className="font-grotesk text-[32px] uppercase tracking-wide">Awaiting Signal</p>
                  <p className="font-mono text-[12px] text-cream/50 max-w-[240px] mx-auto">Fill the parameters and initiate the screening.</p>
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <div key={i} className={`flex flex-col ${m.role === 'system' ? 'items-center' : m.role === 'user' ? 'items-end' : 'items-start'} max-w-full`}>
                  {m.role === 'system' ? (
                    <div className="font-mono text-[9px] uppercase text-neon/80 bg-neon/10 border border-neon/20 px-4 py-1.5 rounded-full my-2">
                      {m.text}
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5 max-w-[85%]">
                      <span className={`font-mono text-[10px] uppercase tracking-widest ${m.role === 'user' ? 'text-cream/50 text-right' : 'text-neon text-left'}`}>
                        {m.role === 'user' ? (name || 'CANDIDATE') : 'PRIYA AI'}
                      </span>
                      <div className={`font-mono text-[13px] leading-relaxed px-5 py-4 shadow-sm ${m.role === 'user' ? 'bg-cream text-background rounded-[20px] rounded-tr-sm' : 'liquid-glass text-cream rounded-[20px] rounded-tl-sm'}`}>
                        {m.text}
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={endRef} />
          </div>

          {/* Status footer */}
          <div className="p-5 border-t border-white/10 flex items-center justify-between bg-black/20 backdrop-blur-md">
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full" style={{ background: isLive ? '#6FFF00' : 'rgba(255,255,255,0.3)', animation: isLive ? 'pulse-dot 2s ease-in-out infinite' : 'none' }} />
              <span className="font-mono text-[11px] uppercase tracking-widest text-cream/60">
                {isLive ? (wsRef.current ? 'WEB CALL ACTIVE' : 'CALL IN PROGRESS') : 'NO ACTIVE CALL'}
              </span>
            </div>
            {wsRef.current && (
              <div className="flex items-end justify-between gap-1 w-24 h-5">
                {bars.map((lvl, i) => (
                  <div key={i} className="flex-1 rounded-full transition-all duration-75"
                    style={{
                      height: `${Math.max(4, lvl * 20)}px`,
                      background: lvl > 0.05 ? '#6FFF00' : 'rgba(255,255,255,0.1)'
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </section>

        {/* ═══ RIGHT PANEL — Info / Scorecard ═══ */}
        <aside className="col-span-12 lg:col-span-3 flex flex-col overflow-y-auto scrollbar-hide space-y-6">
          {!report ? (
            <>
              <div className="liquid-glass rounded-[24px] p-4 lg:p-5">
                <h3 className="font-grotesk uppercase text-[22px] leading-none mb-4 flex items-center justify-between">
                  Telemetry <Activity size={18} className="text-neon" />
                </h3>
                <div className="space-y-4">
                  <InfoRow label="Status" value={
                    isLive ? <span className="px-2 py-0.5 bg-neon/20 text-neon border border-neon/30 rounded-[8px] font-mono text-[10px] uppercase">LIVE</span> :
                    isBusy ? <span className="px-2 py-0.5 bg-white/10 text-cream border border-white/20 rounded-[8px] font-mono text-[10px] uppercase">CONNECT</span> :
                    isDone ? <span className="px-2 py-0.5 bg-black/50 text-cream/50 border border-white/10 rounded-[8px] font-mono text-[10px] uppercase">ENDED</span> :
                    <span className="font-mono text-[11px] text-cream/30">—</span>
                  } />
                  {isLive && <InfoRow label="Duration" value={<span className="font-mono text-[13px] text-cream">{fmt(elapsed)}</span>} />}
                  <InfoRow label="Candidate" value={<span className="font-mono text-[12px] text-cream truncate max-w-[120px]">{name || '—'}</span>} />
                  <InfoRow label="Engine" value={<span className="font-mono text-[11px] text-cream flex items-center gap-1"><Sparkles size={10} className="text-neon"/> Gemini</span>} />
                </div>
              </div>

              <div className="liquid-glass rounded-[24px] p-4 lg:p-5">
                <h3 className="font-grotesk uppercase text-[22px] leading-none mb-4 flex items-center justify-between">
                  Goals <CheckCircle size={18} className="text-neon" />
                </h3>
                <ul className="space-y-3">
                  {['Confirm interest', 'Verify core tech', 'Capture salary', 'Note timeline', 'Assess culture'].map((item, i) => (
                    <li key={i} className="flex items-start gap-2 font-mono text-[11px] uppercase text-cream/70 leading-snug">
                      <span className="text-neon mt-[1px] text-[10px] flex-shrink-0">◆</span> {item}
                    </li>
                  ))}
                </ul>
              </div>

              <Link to="/dashboard" className="liquid-glass rounded-[24px] p-4 lg:p-5 flex items-center justify-between group hover:border-neon/30 border border-white/10 transition-colors">
                <div>
                  <p className="font-mono text-[10px] text-cream/50 uppercase tracking-widest mb-1">Analytics</p>
                  <p className="font-grotesk text-[18px] uppercase text-cream group-hover:text-neon transition-colors">View Dashboard</p>
                </div>
                <div className="w-10 h-10 rounded-[14px] bg-neon/10 border border-neon/20 flex items-center justify-center group-hover:bg-neon/20 transition-colors">
                  <BarChart3 size={18} className="text-neon" />
                </div>
              </Link>
            </>
          ) : (
            <Scorecard report={report} name={name} />
          )}
        </aside>
      </main>

      {/* ── Toast Notification ── */}
      {toast && (
        <div className="fixed bottom-8 right-8 z-50 animate-toast">
          <div className={`px-5 py-3.5 flex items-center gap-3 rounded-[16px] liquid-glass border ${
            toast.type === 'error' ? 'border-red-500/50 text-red-400' : 'border-neon/50 text-neon'
          }`}>
            {toast.type === 'error' ? <AlertTriangle size={18} /> : <CheckCircle size={18} />}
            <span className="font-mono text-[12px] uppercase">{toast.message}</span>
            <button onClick={() => setToast(null)} className="ml-3 opacity-50 hover:opacity-100 transition-opacity">✕</button>
          </div>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="font-mono text-[11px] uppercase text-cream/50 flex-shrink-0">{label}</span>
      <div className="text-right">{value}</div>
    </div>
  );
}

function Scorecard({ report, name }) {
  const [copied, setCopied] = useState(false);
  const outcome = OUTCOME[report.call_outcome] || OUTCOME.CONFUSED;
  const OutIcon = outcome.Icon;
  const score   = typeof report.score === 'number' ? report.score : null;
  const conf    = report.overall_confidence;

  const handleExport = () => {
    navigator.clipboard.writeText(buildExportText(report, name))
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); })
      .catch(() => {});
  };

  const hasDimensions = DIMS.some(d => report[d.key]);
  const hasMetrics = report.salary_expectation_lpa != null || report.current_ctc_lpa != null
    || report.notice_period_days != null || report.joining_timeline || report.other_offers != null;

  return (
    <div className="liquid-glass rounded-[32px] overflow-hidden">
      <div className="p-6 border-b border-white/10 flex items-center justify-between bg-white/5 backdrop-blur-md">
        <h3 className="font-grotesk uppercase text-[22px] leading-none">
          Report
        </h3>
        <button onClick={handleExport}
          className="flex items-center gap-1.5 font-mono text-[10px] uppercase px-3 py-1.5 rounded-[8px] transition-all border"
          style={{ background: copied ? 'rgba(111,255,0,0.1)' : 'rgba(255,255,255,0.05)', borderColor: copied ? 'rgba(111,255,0,0.3)' : 'rgba(255,255,255,0.1)', color: copied ? '#6FFF00' : '#EFF4FF' }}>
          <Copy size={12} /> {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      <div className="p-6 space-y-8">
        <div className="flex items-center gap-5">
          <div className="w-[84px] h-[84px] flex-shrink-0 rounded-[24px] flex flex-col items-center justify-center bg-white/5 border border-white/10">
            <span className="font-grotesk text-[48px] leading-none text-cream">
              {score ?? '—'}
            </span>
            <span className="font-mono text-[9px] text-cream/40 uppercase mt-1">/10 Score</span>
          </div>
          <div className="flex-1 min-w-0 space-y-2">
            <div>
              <p className="font-mono text-[10px] text-cream/50 mb-1.5 uppercase">Outcome</p>
              <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[12px] border font-mono text-[11px] uppercase ${outcome.cls.includes('emerald') ? 'text-neon bg-neon/10 border-neon/30' : outcome.cls.includes('red') ? 'text-red-400 bg-red-500/10 border-red-500/30' : 'text-cream bg-white/5 border-white/10'}`}>
                <OutIcon size={12} /> {outcome.label}
              </div>
            </div>
            {conf != null && (
              <div className="flex items-center gap-1.5 mt-2">
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-neon" />
                <span className="font-mono text-[9px] uppercase text-cream/70">
                  {confLabel(conf)} Conf <span className="text-cream/40">({Math.round(conf * 100)}%)</span>
                </span>
              </div>
            )}
          </div>
        </div>

        {report.vibe_check && (
          <div className="p-4 rounded-[16px] bg-white/5 border border-white/10 font-mono text-[12px] italic text-cream/80 leading-relaxed">
            "{report.vibe_check}"
          </div>
        )}

        <div className="space-y-6">
          {report.summary_bullets?.length > 0 && (
            <div>
              <p className="font-mono text-[10px] text-cream/50 uppercase mb-3">Summary</p>
              <ul className="space-y-2">
                {report.summary_bullets.map((b, i) => (
                  <li key={i} className="flex items-start gap-2.5 font-mono text-[11px] text-cream/80 leading-relaxed">
                    <span className="text-neon mt-[2px] flex-shrink-0 text-[10px]">■</span> {b}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hasMetrics && (
            <div>
              <p className="font-mono text-[10px] text-cream/50 uppercase mb-3">Metrics</p>
              <div className="grid grid-cols-2 gap-3">
                {report.salary_expectation_lpa != null && <MetricTile label="Exp CTC" value={`${report.salary_expectation_lpa} LPA`} />}
                {report.current_ctc_lpa != null        && <MetricTile label="Cur CTC" value={`${report.current_ctc_lpa} LPA`} />}
                {report.notice_period_days != null     && <MetricTile label="Notice" value={`${report.notice_period_days} Days`} />}
                {report.joining_timeline               && <MetricTile label="Joining" value={report.joining_timeline} wide />}
              </div>
            </div>
          )}

          {hasDimensions && (
            <div>
              <p className="font-mono text-[10px] text-cream/50 uppercase mb-3">Dimensions</p>
              <div className="space-y-2.5">
                {DIMS.map(d => {
                  const dim = report[d.key];
                  if (!dim) return null;
                  const DIcon = d.Icon;
                  return (
                    <div key={d.key} className="flex flex-col gap-2 p-3 rounded-[16px] border border-white/10 bg-white/5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <DIcon size={12} className="text-cream/50" />
                          <span className="font-mono text-[10px] uppercase text-cream/80">{d.label}</span>
                        </div>
                        <span className="font-mono text-[11px] text-neon">{dim.score}/10</span>
                      </div>
                      <div className="w-full h-1.5 bg-black/50 rounded-full overflow-hidden">
                        <div className="h-full bg-neon rounded-full" style={{ width: `${(dim.score / 10) * 100}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {report.skills_verified?.length > 0 && (
            <div>
              <p className="font-mono text-[10px] text-cream/50 uppercase mb-3">Skills Verified</p>
              <div className="flex flex-wrap gap-2">
                {report.skills_verified.map((s, i) => (
                  <span key={i} className="font-mono text-[10px] px-3 py-1.5 rounded-[10px] bg-neon/10 border border-neon/20 text-neon uppercase">{s}</span>
                ))}
              </div>
            </div>
          )}

          {report.recommended_next_step && (
            <div className="p-4 rounded-[16px] bg-neon/5 border border-neon/20">
              <p className="font-mono text-[10px] text-neon uppercase mb-2 flex items-center gap-1.5">
                <Zap size={10} /> Recommended Action
              </p>
              <p className="font-mono text-[12px] text-cream/80 leading-relaxed">{report.recommended_next_step}</p>
            </div>
          )}

          {report.hr_flags?.length > 0 && (
            <div>
              <p className="font-mono text-[10px] text-red-400 uppercase mb-3">HR Flags</p>
              <ul className="space-y-2">
                {report.hr_flags.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 font-mono text-[11px] text-red-400 bg-red-500/10 px-3 py-2 rounded-[12px] border border-red-500/20">
                    <span className="text-red-500 mt-[1px] flex-shrink-0">⚠</span> {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricTile({ label, value, wide }) {
  return (
    <div className={`p-3 rounded-[16px] bg-white/5 border border-white/10 ${wide ? 'col-span-2' : ''}`}>
      <p className="font-mono text-[9px] text-cream/50 mb-1 uppercase">{label}</p>
      <p className="font-mono text-[12px] text-cream truncate">{value}</p>
    </div>
  );
}
