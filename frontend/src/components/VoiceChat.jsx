import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Phone, Activity, Briefcase, User,
  PhoneCall, CheckCircle, XCircle, AlertTriangle,
  MessageSquare, Loader2, Zap, Clock, Sparkles,
  Copy, TrendingUp, Heart, Package, Code2,
  MapPin, DollarSign, Calendar, Users, Building2,
  SlidersHorizontal, FileText, Upload,
} from 'lucide-react';

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

  const endRef       = useRef(null);
  const timerRef     = useRef(null);
  const fileInputRef = useRef(null);
  const pollRef      = useRef(null);

  const setSF = (key, val) => setStructuredFields(prev => ({ ...prev, [key]: val }));

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

  const _startPolling = useCallback((callSid) => {
    clearInterval(pollRef.current);
    let attempts = 0;
    const MAX_ATTEMPTS = 60; // 5 minutes at 5s intervals
    pollRef.current = setInterval(async () => {
      attempts++;
      if (attempts > MAX_ATTEMPTS) { clearInterval(pollRef.current); return; }
      try {
        const r = await fetch(`${API_BASE}/api/session/${callSid}/`);
        if (r.status === 202) return; // still pending
        const data = await r.json();
        if (data.status === 'complete') {
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
        setMessages([{ role: 'system', text: `Outbound call initiated → ${name || phone} · SID ${sid}`, time: nowTime() }]);
        setStatus('connected');
        // Poll for evaluation results — backend saves DB record after call ends
        _startPolling(sid);
      } else { alert(res.message); setStatus('idle'); }
    } catch { alert('Backend unreachable.'); setStatus('idle'); }
  }, [phone, jd, name, resumeText, inputMode, structuredFields]);

  const report = recap ? (() => {
    const d = jsonTry(recap.reason || '{}');
    return { ...d, score: recap.score ?? d.intent_score };
  })() : null;

  const isIdle  = status === 'idle';
  const isLive  = status === 'connected';
  const isBusy  = status === 'connecting';
  const isDone  = status === 'ended';

  // ── Status pill config ──────────────────────────────────────────────────────
  const pill = isLive
    ? { bg: '#f0fdf4', bd: '#bbf7d0', tx: '#16a34a', dot: '#22c55e', label: 'Call In Progress', pulse: true  }
    : isBusy
    ? { bg: '#fffbeb', bd: '#fde68a', tx: '#b45309', dot: '#f59e0b', label: 'Initiating…',      pulse: true  }
    : isDone
    ? { bg: '#f8fafc', bd: '#e2e8f0', tx: '#64748b', dot: '#94a3b8', label: 'Session Ended',    pulse: false }
    : { bg: '#f8fafc', bd: '#e2e8f0', tx: '#94a3b8', dot: '#cbd5e1', label: 'Ready',            pulse: false };

  return (
    <div className="min-h-screen flex flex-col">

      {/* ── Ambient orbs ── */}
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

        <div className="flex items-center gap-4">
          {isLive && (
            <span className="text-[12px] font-mono font-semibold text-slate-500 tabular-nums tracking-tight">{fmt(elapsed)}</span>
          )}
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
        <aside className="col-span-12 lg:col-span-3 flex flex-col gap-3 overflow-y-auto scrollbar-hide"
          style={{ maxHeight: 'calc(100vh - 5rem)' }}>

          {/* Input mode toggle */}
          <section className="glass rounded-2xl p-5">
            <Label icon={<Briefcase size={12} />}>Role Requirements</Label>

            {/* Mode switcher */}
            <div className="flex mt-3 rounded-xl overflow-hidden border border-slate-200/80 bg-slate-50/60">
              {[
                { id: 'prompt',     icon: <FileText size={11} />,          label: 'Prompt'     },
                { id: 'structured', icon: <SlidersHorizontal size={11} />, label: 'Structured' },
              ].map(({ id, icon, label }) => (
                <button
                  key={id}
                  onClick={() => !isLive && setInputMode(id)}
                  disabled={isLive}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 text-[11px] font-semibold transition-all"
                  style={inputMode === id
                    ? { background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', color: '#fff', boxShadow: '0 2px 8px rgba(99,102,241,0.28)' }
                    : { color: '#94a3b8' }}
                >
                  {icon}{label}
                </button>
              ))}
            </div>

            {/* ── Prompt mode ── */}
            {inputMode === 'prompt' && (
              <div className="mt-3">
                <p className="text-[10px] text-slate-400 mb-2 leading-relaxed">
                  Describe the role in plain English — the AI extracts all details automatically.
                </p>
                <textarea
                  rows={8}
                  className="glass-input w-full rounded-xl p-3.5 text-[13px] placeholder-slate-400 resize-none leading-relaxed"
                  placeholder={'e.g. "Senior Python engineer, Bangalore hybrid, 5+ yrs, 25-30 LPA, join within 1 month. Strong FastAPI and Postgres skills needed."'}
                  value={jd} onChange={e => setJd(e.target.value)} disabled={isLive}
                />
              </div>
            )}

            {/* ── Structured mode ── */}
            {inputMode === 'structured' && (
              <div className="mt-3 space-y-3">

                {/* Job title */}
                <div>
                  <p className="text-[10px] font-medium text-slate-400 mb-1">Job Title</p>
                  <input type="text"
                    className="glass-input w-full rounded-xl py-2.5 px-3.5 text-[13px]"
                    placeholder="e.g. Senior Backend Engineer"
                    value={structuredFields.job_title}
                    onChange={e => setSF('job_title', e.target.value)} disabled={isLive} />
                </div>

                {/* Company overview */}
                <div>
                  <p className="text-[10px] font-medium text-slate-400 mb-1 flex items-center gap-1">
                    <Building2 size={9} /> Company Overview
                  </p>
                  <textarea rows={2}
                    className="glass-input w-full rounded-xl p-3 text-[12px] placeholder-slate-400 resize-none leading-relaxed"
                    placeholder="Brief company background…"
                    value={structuredFields.company_overview}
                    onChange={e => setSF('company_overview', e.target.value)} disabled={isLive} />
                </div>

                {/* Team details */}
                <div>
                  <p className="text-[10px] font-medium text-slate-400 mb-1 flex items-center gap-1">
                    <Users size={9} /> Team Details
                  </p>
                  <input type="text"
                    className="glass-input w-full rounded-xl py-2.5 px-3.5 text-[13px]"
                    placeholder="e.g. 8-person platform team, reports to VP Eng"
                    value={structuredFields.team_details}
                    onChange={e => setSF('team_details', e.target.value)} disabled={isLive} />
                </div>

                {/* Required skills */}
                <div>
                  <p className="text-[10px] font-medium text-slate-400 mb-1">Required Skills</p>
                  <input type="text"
                    className="glass-input w-full rounded-xl py-2.5 px-3.5 text-[13px]"
                    placeholder="Python, FastAPI, PostgreSQL, Redis…"
                    value={structuredFields.required_skills}
                    onChange={e => setSF('required_skills', e.target.value)} disabled={isLive} />
                </div>

                {/* Experience + CTC (2-col) */}
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-[10px] font-medium text-slate-400 mb-1">Experience</p>
                    <input type="text"
                      className="glass-input w-full rounded-xl py-2.5 px-3 text-[12px]"
                      placeholder="5+ years"
                      value={structuredFields.years_of_experience}
                      onChange={e => setSF('years_of_experience', e.target.value)} disabled={isLive} />
                  </div>
                  <div>
                    <p className="text-[10px] font-medium text-slate-400 mb-1 flex items-center gap-1">
                      <DollarSign size={9} /> Offered CTC
                    </p>
                    <input type="text"
                      className="glass-input w-full rounded-xl py-2.5 px-3 text-[12px]"
                      placeholder="25-30 LPA"
                      value={structuredFields.ctc_range}
                      onChange={e => setSF('ctc_range', e.target.value)} disabled={isLive} />
                  </div>
                </div>

                {/* Location + Joining (2-col) */}
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-[10px] font-medium text-slate-400 mb-1 flex items-center gap-1">
                      <MapPin size={9} /> Location
                    </p>
                    <input type="text"
                      className="glass-input w-full rounded-xl py-2.5 px-3 text-[12px]"
                      placeholder="Bangalore"
                      value={structuredFields.company_location}
                      onChange={e => setSF('company_location', e.target.value)} disabled={isLive} />
                  </div>
                  <div>
                    <p className="text-[10px] font-medium text-slate-400 mb-1 flex items-center gap-1">
                      <Calendar size={9} /> Joining
                    </p>
                    <input type="text"
                      className="glass-input w-full rounded-xl py-2.5 px-3 text-[12px]"
                      placeholder="Immediate"
                      value={structuredFields.required_joining_timeline}
                      onChange={e => setSF('required_joining_timeline', e.target.value)} disabled={isLive} />
                  </div>
                </div>

                {/* Work location type */}
                <div>
                  <p className="text-[10px] font-medium text-slate-400 mb-1.5">Work Mode</p>
                  <div className="flex gap-1.5">
                    {WORK_LOCATION_OPTIONS.map(opt => {
                      const active = structuredFields.work_location_type === opt;
                      return (
                        <button key={opt} disabled={isLive}
                          onClick={() => setSF('work_location_type', active ? '' : opt)}
                          className="flex-1 py-1.5 rounded-lg text-[11px] font-semibold border transition-all"
                          style={active
                            ? { background: 'rgba(99,102,241,0.12)', borderColor: 'rgba(99,102,241,0.35)', color: '#4f46e5' }
                            : { background: 'rgba(248,250,252,0.8)', borderColor: 'rgba(15,23,42,0.10)', color: '#94a3b8' }
                          }>
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Optional extra JD details */}
                <div>
                  <p className="text-[10px] font-medium text-slate-400 mb-1">Additional JD Details <span className="text-slate-300">(optional)</span></p>
                  <textarea rows={2}
                    className="glass-input w-full rounded-xl p-3 text-[12px] placeholder-slate-400 resize-none leading-relaxed"
                    placeholder="Paste extra JD text or requirements here…"
                    value={jd} onChange={e => setJd(e.target.value)} disabled={isLive} />
                </div>
              </div>
            )}
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

          {/* Resume Upload */}
          <section className="glass rounded-2xl p-5">
            <Label icon={<FileText size={12} />}>Resume <span className="text-slate-300 font-normal normal-case tracking-normal">(optional)</span></Label>
            <div
              className="mt-3 rounded-xl border-2 border-dashed transition-all cursor-pointer"
              style={{
                borderColor: dragOver ? '#6366f1' : resumeStatus === 'ready' ? 'rgba(16,185,129,0.40)' : resumeStatus === 'error' ? 'rgba(239,68,68,0.35)' : 'rgba(99,102,241,0.25)',
                background:  dragOver ? 'rgba(99,102,241,0.05)' : resumeStatus === 'ready' ? 'rgba(16,185,129,0.04)' : 'transparent',
              }}
              onDragOver={(e) => { e.preventDefault(); if (!isLive) setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); if (!isLive) handleResumeFile(e.dataTransfer.files[0]); }}
              onClick={() => { if (!isLive && resumeStatus !== 'uploading') fileInputRef.current?.click(); }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx"
                className="hidden"
                onChange={(e) => handleResumeFile(e.target.files[0])}
              />

              {resumeStatus === 'idle' && (
                <div className="py-5 flex flex-col items-center gap-2">
                  <Upload size={18} className="text-indigo-400" />
                  <p className="text-[11px] text-slate-400 text-center leading-relaxed px-2">
                    Drop PDF or DOCX here<br />or click to browse
                  </p>
                </div>
              )}

              {resumeStatus === 'uploading' && (
                <div className="py-5 flex flex-col items-center gap-2">
                  <Loader2 size={18} className="text-indigo-500 animate-spin" />
                  <p className="text-[11px] text-indigo-600 font-medium">Parsing resume…</p>
                </div>
              )}

              {resumeStatus === 'ready' && (
                <div className="py-4 px-3 flex items-start gap-2.5">
                  <CheckCircle size={15} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold text-emerald-700 truncate">{resumeFile}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">{resumeText.length.toLocaleString()} characters extracted</p>
                  </div>
                </div>
              )}

              {resumeStatus === 'error' && (
                <div className="py-4 px-3 flex items-start gap-2.5">
                  <XCircle size={15} className="text-red-500 flex-shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-[11px] text-red-600 leading-snug">{resumeError}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">Click to try again</p>
                  </div>
                </div>
              )}
            </div>

            {resumeStatus === 'ready' && (
              <button
                onClick={(e) => { e.stopPropagation(); clearResume(); }}
                className="mt-2 w-full text-[10px] text-slate-400 hover:text-red-500 transition-colors text-center"
              >
                ✕ Remove resume
              </button>
            )}
          </section>

          {/* CTA */}
          <div className="space-y-2">
            {isLive ? (
              <div className="w-full py-[11px] rounded-xl text-sm font-semibold flex items-center justify-center gap-2 text-slate-400 border border-dashed border-slate-200 select-none">
                <PhoneCall size={14} className="text-emerald-500" />
                Call in progress…
              </div>
            ) : (
              <button onClick={triggerCall} disabled={isBusy || !phone || phone === '+91'}
                className="btn-primary w-full py-[11px] rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
                {isBusy ? <Loader2 size={14} className="animate-spin" /> : <PhoneCall size={14} />}
                {isBusy ? 'Initiating Call…' : 'Trigger Outbound Call'}
              </button>
            )}
            {(isLive || isDone) && (
              <button onClick={() => { clearInterval(pollRef.current); setStatus('idle'); setMessages([]); setRecap(null); setElapsed(0); setJd(''); setStructuredFields(EMPTY_STRUCTURED); clearResume(); }}
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
                { label: 'Brain',    value: 'Gemini Live' },
                { label: 'Persona',  value: 'Priya · HR screening' },
                { label: 'Channel',  value: 'Outbound call' },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-400">{label}</span>
                  <span className="text-[11px] font-semibold text-indigo-600">{value}</span>
                </div>
              ))}
            </div>
          </section>
        </aside>

        {/* ═══ CENTER — Log ═══ */}
        <section className="col-span-12 lg:col-span-6">
          <div className="glass rounded-2xl flex flex-col" style={{ minHeight: 640 }}>

            {/* Chat header */}
            <div className="px-5 py-4 flex items-center gap-2 border-b border-black/[0.05]">
              <MessageSquare size={13} className="text-indigo-500" />
              <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                Call Log
              </span>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5 scrollbar-hide">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center gap-4 select-none" style={{ minHeight: 340 }}>
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                    style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.10), rgba(139,92,246,0.10))', border: '1px solid rgba(99,102,241,0.14)' }}>
                    <PhoneCall size={22} className="text-indigo-500" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-semibold text-slate-400">Ready to Call</p>
                    <p className="text-xs text-slate-300 mt-1.5">Fill in the candidate details and trigger an outbound call.</p>
                  </div>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div key={i} className="flex justify-center msg-in">
                    <div className="text-[11px] text-slate-400 italic px-4 py-1.5 rounded-full"
                      style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.11)' }}>
                      {m.text}
                    </div>
                  </div>
                ))
              )}
              <div ref={endRef} />
            </div>

            {/* Status footer */}
            <div className="px-5 pb-4 pt-3 border-t border-black/[0.05]">
              <div className="flex items-center gap-2">
                <span className="w-[7px] h-[7px] rounded-full flex-shrink-0"
                  style={{ background: isLive ? '#22c55e' : '#cbd5e1', animation: isLive ? 'pulse-dot 2s ease-in-out infinite' : 'none' }} />
                <span className="text-[10px] font-medium text-slate-400">
                  {isLive ? 'Call in progress — Priya is speaking with the candidate' : 'No active call'}
                </span>
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
                      isLive  ? <Chip color="emerald">Live</Chip> :
                      isBusy  ? <Chip color="amber">Connecting</Chip> :
                      isDone  ? <Chip color="slate">Ended</Chip> :
                      <span className="text-[11px] text-slate-300">—</span>
                    } />
                  {isLive && (
                    <InfoRow label="Duration"
                      value={<span className="text-[12px] font-mono font-semibold text-indigo-600 tabular-nums">{fmt(elapsed)}</span>} />
                  )}
                  <InfoRow label="Candidate"
                    value={<span className="text-[12px] font-medium text-slate-600 truncate max-w-[110px]">{name || '—'}</span>} />
                  <InfoRow label="Channel"
                    value={<span className="text-[12px] text-slate-500">Outbound</span>} />
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
                  Vox mirrors the candidate's language — powered by Gemini Live.
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

// ── Compatibility config ────────────────────────────────────────────────────
const COMPAT = {
  green:  { dot: '🟢', label: 'Strong Match',    bg: 'rgba(5,150,105,0.07)',  bd: 'rgba(5,150,105,0.22)',  tx: '#065f46', hd: '#059669' },
  yellow: { dot: '🟡', label: 'Partial Match',   bg: 'rgba(245,158,11,0.07)', bd: 'rgba(245,158,11,0.22)', tx: '#78350f', hd: '#d97706' },
  red:    { dot: '🔴', label: 'Weak Match',       bg: 'rgba(239,68,68,0.07)',  bd: 'rgba(239,68,68,0.22)',  tx: '#7f1d1d', hd: '#dc2626' },
};
const RECOMMEND = {
  shortlist: { label: 'Shortlist',    bg: 'rgba(5,150,105,0.10)',  bd: 'rgba(5,150,105,0.30)',  tx: '#065f46' },
  hold:      { label: 'Hold',         bg: 'rgba(245,158,11,0.10)', bd: 'rgba(245,158,11,0.30)', tx: '#78350f' },
  reject:    { label: 'Reject',       bg: 'rgba(239,68,68,0.10)',  bd: 'rgba(239,68,68,0.30)',  tx: '#7f1d1d' },
};

function Scorecard({ report, name }) {
  const [copied, setCopied] = useState(false);
  const outcome = OUTCOME[report.call_outcome] || OUTCOME.CONFUSED;
  const OutIcon = outcome.Icon;
  const score   = typeof report.score === 'number' ? report.score : null;
  const conf    = report.overall_confidence;
  const cs      = report.candidate_summary || null;
  const compat  = cs ? (COMPAT[cs.compatibility_level] || COMPAT.yellow) : null;
  const rec     = cs ? (RECOMMEND[cs.recommendation] || RECOMMEND.hold) : null;

  const handleExport = () => {
    navigator.clipboard.writeText(buildExportText(report, name))
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); })
      .catch(() => {});
  };

  const hasDimensions = DIMS.some(d => report[d.key]);
  const hasMetrics = report.salary_expectation_lpa != null || report.current_ctc_lpa != null
    || report.notice_period_days != null || report.joining_timeline || report.other_offers != null;

  return (
    <div className="space-y-3" style={{ animation: 'scoreDrop 0.35s ease-out' }}>

      {/* ── Candidate Compatibility Summary ── */}
      {cs && compat && (
        <section className="rounded-2xl p-5" style={{ background: compat.bg, border: `1.5px solid ${compat.bd}` }}>

          {/* Header row */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-[18px] leading-none">{compat.dot}</span>
              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.07em]" style={{ color: compat.hd }}>
                  {compat.label}
                </p>
                <p className="text-[10px] font-medium mt-0.5" style={{ color: compat.tx }}>
                  {cs.compatibility_reason}
                </p>
              </div>
            </div>
            {rec && (
              <span className="text-[10px] font-bold px-2.5 py-1 rounded-lg border flex-shrink-0"
                style={{ background: rec.bg, borderColor: rec.bd, color: rec.tx }}>
                {rec.label}
              </span>
            )}
          </div>

          {/* Summary bullets */}
          {cs.summary_bullets?.length > 0 && (
            <ul className="space-y-1 mb-3">
              {cs.summary_bullets.map((b, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[11px] leading-snug" style={{ color: compat.tx }}>
                  <span className="flex-shrink-0 mt-[2px] opacity-60">·</span>{b}
                </li>
              ))}
            </ul>
          )}

          {/* Match / Gap columns */}
          {(cs.match_points?.length > 0 || cs.gap_points?.length > 0) && (
            <div className="grid grid-cols-2 gap-2 mt-2">
              {cs.match_points?.length > 0 && (
                <div className="rounded-xl p-2.5" style={{ background: 'rgba(5,150,105,0.10)', border: '1px solid rgba(5,150,105,0.20)' }}>
                  <p className="text-[9px] font-bold uppercase tracking-wider text-emerald-700 mb-1.5">Matches</p>
                  <ul className="space-y-1">
                    {cs.match_points.slice(0, 4).map((m, i) => (
                      <li key={i} className="text-[10px] text-emerald-800 leading-snug flex gap-1">
                        <span className="flex-shrink-0">✓</span>{m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {cs.gap_points?.length > 0 && (
                <div className="rounded-xl p-2.5" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.18)' }}>
                  <p className="text-[9px] font-bold uppercase tracking-wider text-red-700 mb-1.5">Gaps</p>
                  <ul className="space-y-1">
                    {cs.gap_points.slice(0, 4).map((g, i) => (
                      <li key={i} className="text-[10px] text-red-800 leading-snug flex gap-1">
                        <span className="flex-shrink-0">✗</span>{g}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Missing skills */}
          {cs.missing_skills?.length > 0 && (
            <div className="mt-3">
              <p className="text-[9px] font-bold uppercase tracking-wider mb-1.5" style={{ color: compat.hd }}>
                Missing Skills
              </p>
              <div className="flex flex-wrap gap-1">
                {cs.missing_skills.map((s, i) => (
                  <span key={i} className="text-[10px] font-semibold px-2 py-0.5 rounded-md"
                    style={{ background: 'rgba(239,68,68,0.10)', border: '1px solid rgba(239,68,68,0.22)', color: '#b91c1c' }}>
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Red flags */}
          {cs.red_flags?.length > 0 && (
            <div className="mt-3 space-y-1">
              {cs.red_flags.map((f, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[10px] font-medium" style={{ color: '#b91c1c' }}>
                  <AlertTriangle size={10} className="flex-shrink-0 mt-[1px]" />
                  {f}
                </div>
              ))}
            </div>
          )}

          {cs.recommendation_reason && (
            <p className="text-[10px] italic mt-3 opacity-70" style={{ color: compat.tx }}>
              {cs.recommendation_reason}
            </p>
          )}
        </section>
      )}

      {/* ── Hero ── */}
      <section className="glass rounded-2xl p-5">
        <div className="flex items-center justify-between mb-4">
          <Label icon={<Activity size={12} />}>Screening Report</Label>
          <button onClick={handleExport}
            className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1.5 rounded-lg transition-all"
            style={{ background: copied ? 'rgba(16,185,129,0.10)' : 'rgba(99,102,241,0.08)',
                     border: `1px solid ${copied ? 'rgba(16,185,129,0.25)' : 'rgba(99,102,241,0.18)'}`,
                     color: copied ? '#059669' : '#6366f1' }}>
            <Copy size={10} />
            {copied ? 'Copied!' : 'Export'}
          </button>
        </div>

        <div className="flex items-start gap-4 mb-4">
          {/* Score */}
          <div className="w-[72px] h-[72px] flex-shrink-0 rounded-2xl flex flex-col items-center justify-center"
            style={{ background: scoreBg(score), border: `1.5px solid ${scoreBd(score)}` }}>
            <span className="text-[30px] font-black leading-none" style={{ color: scoreColor(score) }}>
              {score ?? '—'}
            </span>
            <span className="text-[9px] text-slate-400 font-semibold mt-0.5">/10</span>
          </div>

          <div className="flex-1 min-w-0 space-y-2">
            <div>
              <p className="text-[10px] text-slate-400 mb-1.5 font-medium">Call Outcome</p>
              <div className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-semibold ${outcome.cls}`}>
                <OutIcon size={11} />
                {outcome.label}
              </div>
            </div>
            {conf != null && (
              <div className="flex items-center gap-1.5">
                <span className="w-[6px] h-[6px] rounded-full flex-shrink-0"
                  style={{ background: confColor(conf) }} />
                <span className="text-[10px] font-semibold" style={{ color: confColor(conf) }}>
                  {confLabel(conf)} Confidence
                </span>
                <span className="text-[10px] text-slate-400">({Math.round(conf * 100)}%)</span>
              </div>
            )}
          </div>
        </div>

        {report.vibe_check && (
          <blockquote className="text-[12px] text-slate-500 italic leading-relaxed border-l-2 pl-3 mt-1"
            style={{ borderColor: 'rgba(99,102,241,0.30)' }}>
            "{report.vibe_check}"
          </blockquote>
        )}
      </section>

      {/* ── Evaluation Dimensions ── */}
      {hasDimensions && (
        <section className="glass rounded-2xl p-5">
          <Label icon={<TrendingUp size={12} />}>Evaluation Dimensions</Label>
          <div className="grid grid-cols-2 gap-2 mt-3">
            {DIMS.map(({ key, label, Icon: DimIcon, color, bg, bd }) => {
              const dim = report[key];
              if (!dim) return null;
              return (
                <div key={key} className="rounded-xl p-3" style={{ background: bg, border: `1px solid ${bd}` }}>
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-1">
                      <DimIcon size={9} style={{ color }} />
                      <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color }}>
                        {label}
                      </span>
                    </div>
                    <span className="text-[18px] font-black leading-none" style={{ color }}>
                      {dim.score}
                    </span>
                  </div>
                  <div className="h-[3px] rounded-full mb-2" style={{ background: 'rgba(0,0,0,0.08)' }}>
                    <div className="h-full rounded-full transition-all"
                      style={{ width: `${Math.round((dim.confidence ?? 0) * 100)}%`, background: color, opacity: 0.65 }} />
                  </div>
                  {dim.evidence?.[0] && (
                    <p className="text-[10px] text-slate-500 leading-snug line-clamp-2">
                      "{dim.evidence[0]}"
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Key Metrics ── */}
      {hasMetrics && (
        <section className="glass rounded-2xl p-5">
          <Label icon={<Activity size={12} />}>Key Metrics</Label>
          <div className="grid grid-cols-2 gap-2 mt-3">
            {report.salary_expectation_lpa != null && (
              <MetricTile label="Expected CTC" value={`${report.salary_expectation_lpa} LPA`} />
            )}
            {report.current_ctc_lpa != null && (
              <MetricTile label="Current CTC" value={`${report.current_ctc_lpa} LPA`} />
            )}
            {report.notice_period_days != null && (
              <MetricTile label="Notice" value={`${report.notice_period_days} days`} />
            )}
            {report.other_offers != null && (
              <MetricTile label="Other Offers" value={report.other_offers ? 'Yes ⚡' : 'No'} />
            )}
            {report.joining_timeline && (
              <MetricTile label="Joining" value={report.joining_timeline} wide />
            )}
          </div>
        </section>
      )}

      {/* ── Verified Skills ── */}
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

      {/* ── Summary ── */}
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

      {/* ── Recommended Action ── */}
      {report.recommended_next_step && (
        <section className="rounded-2xl p-4"
          style={{ background: 'rgba(238,242,255,0.90)', border: '1px solid rgba(99,102,241,0.22)' }}>
          <div className="flex items-center gap-1.5 mb-2">
            <Zap size={11} className="text-indigo-500" fill="currentColor" />
            <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-indigo-600">
              Recommended Action
            </span>
          </div>
          <p className="text-[12px] text-indigo-900 leading-relaxed font-medium">
            {report.recommended_next_step}
          </p>
        </section>
      )}

      {/* ── HR Flags ── */}
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
