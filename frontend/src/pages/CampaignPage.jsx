import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, Play, Pause, Download, Users, Phone, CheckCircle,
  XCircle, Clock, AlertTriangle, ChevronRight, BarChart3,
  FileSpreadsheet, Mic, RefreshCw, Loader2,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '';

const VOICES = [
  { id: 'sarah',  label: 'Sarah',  lang: 'American English', flag: '🇺🇸' },
  { id: 'priya',  label: 'Priya',  lang: 'Hindi',            flag: '🇮🇳' },
  { id: 'ananya', label: 'Maitri', lang: 'Marathi',          flag: '🇮🇳' },
  { id: 'nisha',  label: 'Hetal',  lang: 'Gujarati',         flag: '🇮🇳' },
  { id: 'simran', label: 'Noor',   label2: 'Noor',   lang: 'Punjabi', flag: '🇮🇳' },
];

const OUTCOME_COLOURS = {
  INTERESTED:         'text-green-400  bg-green-400/10  border-green-400/30',
  NOT_INTERESTED:     'text-red-400    bg-red-400/10    border-red-400/30',
  BUSY:               'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  CALLBACK_REQUESTED: 'text-blue-400   bg-blue-400/10   border-blue-400/30',
  CONFUSED:           'text-purple-400 bg-purple-400/10 border-purple-400/30',
};

const STATUS_COLOURS = {
  pending:   'text-cream/40  bg-white/5   border-white/10',
  calling:   'text-yellow-400 bg-yellow-400/10 border-yellow-400/30 animate-pulse',
  completed: 'text-green-400  bg-green-400/10  border-green-400/30',
  failed:    'text-red-400    bg-red-400/10    border-red-400/30',
};

// ── helpers ────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, accent = false, sub }) {
  return (
    <div className={`rounded-2xl border p-4 flex flex-col gap-1 ${
      accent ? 'bg-neon/10 border-neon/30' : 'bg-white/5 border-white/10'
    }`}>
      <div className="flex items-center gap-2 text-cream/50">
        <Icon size={13} />
        <span className="font-mono text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <p className={`font-mono text-2xl font-bold ${accent ? 'text-neon' : 'text-cream'}`}>{value}</p>
      {sub && <p className="font-mono text-[10px] text-cream/40">{sub}</p>}
    </div>
  );
}

function Badge({ text, className = '' }) {
  if (!text) return null;
  const cls = OUTCOME_COLOURS[text] || 'text-cream/50 bg-white/5 border-white/10';
  return (
    <span className={`inline-block font-mono text-[9px] uppercase px-2 py-0.5 rounded border ${cls} ${className}`}>
      {text.replace('_', ' ')}
    </span>
  );
}

// ── main component ─────────────────────────────────────────────────────────

export default function CampaignPage() {
  // ── state ────────────────────────────────────────────────────────────────
  const [step, setStep]               = useState('setup');   // setup | validated | dashboard
  const [dragOver, setDragOver]       = useState(false);
  const [file, setFile]               = useState(null);
  const [uploading, setUploading]     = useState(false);
  const [error, setError]             = useState('');

  // campaign config
  const [campaignName, setCampaignName] = useState('');
  const [jd, setJd]                     = useState('');
  const [voiceId, setVoiceId]           = useState('priya');
  const [delaySec, setDelaySec]         = useState(30);
  const [maxRetries, setMaxRetries]     = useState(1);

  // after upload
  const [validation, setValidation]   = useState(null);   // {total_uploaded, valid, invalid, duplicates, ...}
  const [campaignId, setCampaignId]   = useState(null);

  // dashboard
  const [campaign, setCampaign]       = useState(null);
  const [polling, setPolling]         = useState(false);
  const pollRef                        = useRef(null);

  const fileInputRef = useRef(null);

  // ── polling ──────────────────────────────────────────────────────────────
  const fetchCampaign = useCallback(async (id) => {
    try {
      const r = await fetch(`${API_BASE}/api/campaigns/${id}/`);
      if (!r.ok) return;
      const data = await r.json();
      setCampaign(data);
      if (data.status === 'completed' || data.status === 'paused') {
        setPolling(false);
      }
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    if (polling && campaignId) {
      pollRef.current = setInterval(() => fetchCampaign(campaignId), 4000);
    } else {
      clearInterval(pollRef.current);
    }
    return () => clearInterval(pollRef.current);
  }, [polling, campaignId, fetchCampaign]);

  // ── upload ───────────────────────────────────────────────────────────────
  const handleFile = (f) => {
    if (!f) return;
    if (!f.name.match(/\.(xlsx|xls)$/i)) {
      setError('Please upload an Excel file (.xlsx or .xls)');
      return;
    }
    setFile(f);
    setError('');
  };

  const handleUpload = async () => {
    if (!file) { setError('Please select an Excel file'); return; }
    setUploading(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('campaign_name', campaignName || `Campaign ${new Date().toLocaleDateString()}`);
      form.append('job_description', jd);
      form.append('voice_id', voiceId);
      form.append('delay_seconds', delaySec);
      form.append('max_retries', maxRetries);

      const r = await fetch(`${API_BASE}/api/campaigns/create/`, { method: 'POST', body: form });
      const data = await r.json();
      if (!r.ok) { setError(data.error || 'Upload failed'); return; }

      setValidation(data.validation);
      setCampaignId(data.campaign_id);
      setStep('validated');
    } catch (e) {
      setError('Network error — please try again');
    } finally {
      setUploading(false);
    }
  };

  const handleStart = async () => {
    try {
      const r = await fetch(`${API_BASE}/api/campaigns/${campaignId}/start/`, { method: 'POST' });
      const data = await r.json();
      if (!r.ok) { setError(data.error || 'Failed to start'); return; }
      await fetchCampaign(campaignId);
      setStep('dashboard');
      setPolling(true);
    } catch { setError('Network error'); }
  };

  const handlePause = async () => {
    try {
      await fetch(`${API_BASE}/api/campaigns/${campaignId}/pause/`, { method: 'POST' });
      setPolling(false);
      await fetchCampaign(campaignId);
    } catch { /* ignore */ }
  };

  const handleResume = async () => {
    try {
      await fetch(`${API_BASE}/api/campaigns/${campaignId}/start/`, { method: 'POST' });
      setPolling(true);
      await fetchCampaign(campaignId);
    } catch { /* ignore */ }
  };

  const handleExport = () => {
    window.open(`${API_BASE}/api/campaigns/${campaignId}/export/`, '_blank');
  };

  const stats = campaign?.stats || {};
  const pct   = stats.completion_pct ?? 0;

  // ── render ───────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0f] text-cream pt-20 px-4 pb-16">
      <div className="max-w-4xl mx-auto">

        {/* Header */}
        <motion.div initial={{ opacity: 0, y: -16 }} animate={{ opacity: 1, y: 0 }} className="mb-10">
          <p className="font-mono text-[10px] text-neon uppercase tracking-widest mb-2">Bulk Recruitment</p>
          <h1 className="text-3xl font-bold text-cream">Campaign Caller</h1>
          <p className="text-cream/40 text-sm mt-1 font-mono">Upload candidates → AI screens them → track results live</p>
        </motion.div>

        {/* Step indicator */}
        <div className="flex items-center gap-2 mb-8 font-mono text-[10px] uppercase tracking-wider">
          {['Setup', 'Validate', 'Call'].map((s, i) => {
            const active = (i === 0 && step === 'setup') || (i === 1 && step === 'validated') || (i === 2 && step === 'dashboard');
            const done   = (i === 0 && step !== 'setup') || (i === 1 && step === 'dashboard');
            return (
              <React.Fragment key={s}>
                <span className={`px-3 py-1 rounded-full border transition-all ${
                  done   ? 'bg-neon/20 border-neon/40 text-neon' :
                  active ? 'bg-white/10 border-white/30 text-cream' :
                           'border-white/10 text-cream/30'
                }`}>{s}</span>
                {i < 2 && <ChevronRight size={12} className="text-cream/20" />}
              </React.Fragment>
            );
          })}
        </div>

        <AnimatePresence mode="wait">

          {/* ── SETUP ─────────────────────────────────────────────────────── */}
          {step === 'setup' && (
            <motion.div key="setup" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="space-y-6">

              {/* Campaign name + JD */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Campaign Name</label>
                  <input
                    value={campaignName}
                    onChange={e => setCampaignName(e.target.value)}
                    placeholder="e.g. Backend Engineers — May 2025"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 font-mono text-sm text-cream placeholder:text-cream/20 focus:outline-none focus:border-neon/50"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Voice / Language</label>
                  <div className="grid grid-cols-5 gap-1.5">
                    {VOICES.map(v => (
                      <button
                        key={v.id}
                        onClick={() => setVoiceId(v.id)}
                        className={`flex flex-col items-center gap-0.5 p-2 rounded-xl border text-center transition-all ${
                          voiceId === v.id
                            ? 'bg-neon/15 border-neon/50 text-neon'
                            : 'bg-white/5 border-white/10 text-cream/50 hover:bg-white/10'
                        }`}
                      >
                        <span className="text-base">{v.flag}</span>
                        <span className="font-mono text-[9px] uppercase">{v.label2 || v.label}</span>
                        <span className="font-mono text-[8px] text-cream/30 leading-tight">{v.lang}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* JD */}
              <div className="space-y-1.5">
                <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Job Description <span className="text-cream/30">(optional but recommended)</span></label>
                <textarea
                  value={jd}
                  onChange={e => setJd(e.target.value)}
                  rows={4}
                  placeholder="Paste the job description here — the AI will ask targeted questions based on this..."
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 font-mono text-sm text-cream placeholder:text-cream/20 focus:outline-none focus:border-neon/50 resize-none"
                />
              </div>

              {/* Call settings */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="font-mono text-[10px] text-neon uppercase tracking-wider">
                    Delay between calls: <span className="text-cream">{delaySec}s</span>
                  </label>
                  <input
                    type="range" min={10} max={120} step={5} value={delaySec}
                    onChange={e => setDelaySec(+e.target.value)}
                    className="w-full accent-[#39ff14]"
                  />
                  <div className="flex justify-between font-mono text-[9px] text-cream/30">
                    <span>10s</span><span>2 min</span>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="font-mono text-[10px] text-neon uppercase tracking-wider">Max Retries</label>
                  <div className="flex gap-2">
                    {[0, 1, 2].map(n => (
                      <button key={n} onClick={() => setMaxRetries(n)}
                        className={`flex-1 py-2 rounded-xl border font-mono text-sm transition-all ${
                          maxRetries === n ? 'bg-neon/15 border-neon/50 text-neon' : 'bg-white/5 border-white/10 text-cream/50 hover:bg-white/10'
                        }`}
                      >{n}</button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Excel Upload */}
              <div className="space-y-1.5">
                <label className="font-mono text-[10px] text-neon uppercase tracking-wider flex items-center gap-1.5">
                  <FileSpreadsheet size={11} /> Candidate Excel File
                </label>
                <div
                  onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={e => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
                  onClick={() => fileInputRef.current?.click()}
                  className={`relative cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
                    dragOver ? 'border-neon/60 bg-neon/5' :
                    file      ? 'border-neon/30 bg-neon/5' :
                                'border-white/10 bg-white/3 hover:border-white/20 hover:bg-white/5'
                  }`}
                >
                  <input ref={fileInputRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={e => handleFile(e.target.files[0])} />
                  {file ? (
                    <div className="flex flex-col items-center gap-2">
                      <FileSpreadsheet size={28} className="text-neon" />
                      <p className="font-mono text-sm text-cream">{file.name}</p>
                      <p className="font-mono text-[10px] text-cream/40">{(file.size / 1024).toFixed(1)} KB — click to change</p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-2">
                      <Upload size={28} className="text-cream/30" />
                      <p className="font-mono text-sm text-cream/60">Drag & drop your Excel file here</p>
                      <p className="font-mono text-[10px] text-cream/30">or click to browse — .xlsx / .xls</p>
                      <div className="mt-3 inline-block font-mono text-[9px] text-cream/30 border border-white/10 rounded-lg px-3 py-1">
                        Required columns: <span className="text-cream/60">Name</span> · <span className="text-cream/60">Phone</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {error && (
                <div className="flex items-center gap-2 text-red-400 font-mono text-xs bg-red-400/10 border border-red-400/20 rounded-xl px-4 py-3">
                  <AlertTriangle size={14} /> {error}
                </div>
              )}

              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="w-full py-3.5 rounded-xl bg-neon text-black font-mono text-sm font-bold uppercase tracking-wider hover:bg-neon/90 active:scale-[.98] transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {uploading ? <><Loader2 size={16} className="animate-spin" /> Uploading & Validating…</> : <><Upload size={16} /> Upload & Validate Candidates</>}
              </button>
            </motion.div>
          )}

          {/* ── VALIDATED ─────────────────────────────────────────────────── */}
          {step === 'validated' && validation && (
            <motion.div key="validated" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-6">

              <div className="rounded-2xl border border-white/10 bg-white/3 p-6">
                <p className="font-mono text-[10px] text-neon uppercase tracking-wider mb-4">Validation Summary</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard icon={Users}       label="Total Uploaded" value={validation.total_uploaded} />
                  <StatCard icon={CheckCircle} label="Valid"          value={validation.valid}          accent />
                  <StatCard icon={XCircle}     label="Invalid"        value={validation.invalid} />
                  <StatCard icon={AlertTriangle} label="Duplicates"   value={validation.duplicates} />
                </div>
              </div>

              {/* Invalid details */}
              {validation.invalid_details?.length > 0 && (
                <details className="rounded-2xl border border-red-400/20 bg-red-400/5 p-4">
                  <summary className="font-mono text-[10px] text-red-400 uppercase tracking-wider cursor-pointer">
                    {validation.invalid_details.length} invalid entries (click to view)
                  </summary>
                  <div className="mt-3 space-y-1">
                    {validation.invalid_details.map((d, i) => (
                      <div key={i} className="flex items-center gap-3 font-mono text-[11px] text-cream/60">
                        <span className="text-red-400/60">Row {i + 2}</span>
                        <span>{d.name || '—'}</span>
                        <span className="text-cream/30">{d.phone || '—'}</span>
                        <span className="text-red-400">{d.error}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {validation.valid === 0 ? (
                <div className="text-center py-8">
                  <XCircle size={32} className="text-red-400 mx-auto mb-2" />
                  <p className="font-mono text-sm text-red-400">No valid candidates to call.</p>
                  <button onClick={() => setStep('setup')} className="mt-4 font-mono text-[11px] text-neon underline">Go back and fix the file</button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="rounded-2xl border border-neon/20 bg-neon/5 p-4 font-mono text-sm text-cream">
                    <span className="text-neon font-bold">{validation.valid} candidates</span> ready to be called by{' '}
                    <span className="text-neon">{VOICES.find(v => v.id === voiceId)?.label2 || VOICES.find(v => v.id === voiceId)?.label}</span> in{' '}
                    <span className="text-neon">{VOICES.find(v => v.id === voiceId)?.lang}</span>.
                  </div>
                  <div className="flex gap-3">
                    <button onClick={() => setStep('setup')} className="flex-1 py-3 rounded-xl border border-white/10 font-mono text-sm text-cream/60 hover:bg-white/5 transition-all">
                      ← Back
                    </button>
                    <button onClick={handleStart} className="flex-[2] py-3 rounded-xl bg-neon text-black font-mono text-sm font-bold uppercase tracking-wider hover:bg-neon/90 active:scale-[.98] transition-all flex items-center justify-center gap-2">
                      <Play size={16} /> Start Calling Now
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          )}

          {/* ── DASHBOARD ─────────────────────────────────────────────────── */}
          {step === 'dashboard' && campaign && (
            <motion.div key="dashboard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">

              {/* Campaign header */}
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`inline-block w-2 h-2 rounded-full ${
                      campaign.status === 'running'   ? 'bg-neon animate-pulse' :
                      campaign.status === 'completed' ? 'bg-green-400' :
                      campaign.status === 'paused'    ? 'bg-yellow-400' : 'bg-cream/30'
                    }`} />
                    <span className="font-mono text-[10px] text-cream/40 uppercase">{campaign.status}</span>
                  </div>
                  <h2 className="text-xl font-bold text-cream">{campaign.name}</h2>
                  <p className="font-mono text-[11px] text-cream/40 mt-0.5">
                    Voice: {VOICES.find(v => v.id === campaign.voice_id)?.label2 || campaign.voice_id} · {VOICES.find(v => v.id === campaign.voice_id)?.lang}
                  </p>
                </div>
                <div className="flex gap-2">
                  {campaign.status === 'running' && (
                    <button onClick={handlePause} className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-yellow-400/30 text-yellow-400 font-mono text-xs uppercase hover:bg-yellow-400/10 transition-all">
                      <Pause size={12} /> Pause
                    </button>
                  )}
                  {campaign.status === 'paused' && (
                    <button onClick={handleResume} className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-neon/30 text-neon font-mono text-xs uppercase hover:bg-neon/10 transition-all">
                      <Play size={12} /> Resume
                    </button>
                  )}
                  <button onClick={() => fetchCampaign(campaignId)} className="p-2 rounded-xl border border-white/10 text-cream/40 hover:bg-white/5 transition-all">
                    <RefreshCw size={14} />
                  </button>
                  <button onClick={handleExport} className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-white/10 text-cream/60 font-mono text-xs uppercase hover:bg-white/5 transition-all">
                    <Download size={12} /> Export
                  </button>
                </div>
              </div>

              {/* Progress bar */}
              <div className="rounded-2xl border border-white/10 bg-white/3 p-5">
                <div className="flex justify-between items-center mb-3">
                  <span className="font-mono text-[10px] text-cream/50 uppercase tracking-wider flex items-center gap-1.5">
                    <BarChart3 size={11} /> Campaign Progress
                  </span>
                  <span className="font-mono text-sm text-cream font-bold">
                    {stats.completed ?? 0} / {stats.total ?? 0} calls completed — <span className="text-neon">{pct}%</span>
                  </span>
                </div>
                <div className="h-3 bg-white/10 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-neon rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                  />
                </div>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard icon={Users}       label="Total"       value={stats.total ?? 0} />
                <StatCard icon={Clock}       label="Pending"     value={stats.pending ?? 0} />
                <StatCard icon={Phone}       label="Completed"   value={stats.completed ?? 0} accent />
                <StatCard icon={XCircle}     label="Failed"      value={stats.failed ?? 0} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <StatCard icon={CheckCircle} label="Interested"      value={stats.interested ?? 0}     accent sub="Ready for next round" />
                <StatCard icon={XCircle}     label="Not Interested"  value={stats.not_interested ?? 0} sub="Opted out" />
              </div>

              {/* Candidate table */}
              <div className="rounded-2xl border border-white/10 overflow-hidden">
                <div className="px-5 py-3 border-b border-white/10 flex items-center gap-2">
                  <Users size={13} className="text-neon" />
                  <span className="font-mono text-[10px] uppercase tracking-wider text-cream/60">Candidates</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/5">
                        {['#', 'Name', 'Phone', 'Status', 'Outcome', 'Duration', 'Summary'].map(h => (
                          <th key={h} className="text-left px-4 py-2.5 font-mono text-[9px] uppercase text-cream/30 tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(campaign.candidates || []).map((c, i) => (
                        <tr key={c.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                          <td className="px-4 py-3 font-mono text-[11px] text-cream/30">{i + 1}</td>
                          <td className="px-4 py-3 font-mono text-[12px] text-cream font-medium">{c.name}</td>
                          <td className="px-4 py-3 font-mono text-[11px] text-cream/50">{c.phone}</td>
                          <td className="px-4 py-3">
                            <span className={`font-mono text-[9px] uppercase px-2 py-0.5 rounded border ${STATUS_COLOURS[c.status] || ''}`}>
                              {c.status}
                            </span>
                          </td>
                          <td className="px-4 py-3"><Badge text={c.call_outcome} /></td>
                          <td className="px-4 py-3 font-mono text-[11px] text-cream/50">
                            {c.call_duration ? `${Math.round(c.call_duration / 60)}m ${c.call_duration % 60}s` : '—'}
                          </td>
                          <td className="px-4 py-3 font-mono text-[10px] text-cream/40 max-w-xs truncate">{c.ai_summary || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {(!campaign.candidates || campaign.candidates.length === 0) && (
                    <div className="text-center py-10 font-mono text-sm text-cream/30">No candidates yet.</div>
                  )}
                </div>
              </div>

            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </div>
  );
}
