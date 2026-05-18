import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence, useMotionValue, useSpring } from 'framer-motion';
import {
  BarChart3, CheckCircle, Clock, Sparkles, Users, Zap, FileText,
  MapPin, Heart, ArrowLeft, MessageSquare, Phone, PhoneMissed,
  TrendingUp, AlertTriangle, Star, RefreshCw, ChevronDown, ChevronUp,
  Shield, Target, Award, Briefcase, DollarSign, CalendarClock,
  ThumbsUp, ThumbsDown, Activity, Eye, BadgeCheck, Layers,
  ArrowRight, Info, XCircle, CheckCircle2,
} from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const clip = (text, n = 200) => {
  if (!text) return '—';
  return text.length > n ? `${text.slice(0, n)}…` : text;
};

const pct = (n, total) => (total ? Math.round((n / total) * 100) : 0);

// ── Color maps ────────────────────────────────────────────────────────────────

const OUTCOME_STYLE = {
  INTERESTED:         { text: 'text-emerald-400', bg: 'bg-emerald-400/10', border: 'border-emerald-400/25' },
  CALLBACK_REQUESTED: { text: 'text-sky-400',     bg: 'bg-sky-400/10',     border: 'border-sky-400/25' },
  NOT_INTERESTED:     { text: 'text-red-400',     bg: 'bg-red-400/10',     border: 'border-red-400/25' },
  BUSY:               { text: 'text-amber-400',   bg: 'bg-amber-400/10',   border: 'border-amber-400/25' },
  CONFUSED:           { text: 'text-purple-400',  bg: 'bg-purple-400/10',  border: 'border-purple-400/25' },
};
const outcomeStyle = (o) => OUTCOME_STYLE[(o||'').toUpperCase()] || { text:'text-cream/40', bg:'bg-white/5', border:'border-white/10' };

const COMPAT_STYLE = {
  green:  { text: 'text-emerald-400', bg: 'bg-emerald-400/10', border: 'border-emerald-400/25', bar: 'bg-emerald-400' },
  yellow: { text: 'text-amber-400',   bg: 'bg-amber-400/10',   border: 'border-amber-400/25',   bar: 'bg-amber-400' },
  red:    { text: 'text-red-400',     bg: 'bg-red-400/10',     border: 'border-red-400/25',     bar: 'bg-red-400' },
};
const compatStyle = (l) => COMPAT_STYLE[(l||'').toLowerCase()] || { text:'text-cream/40', bg:'bg-white/5', border:'border-white/10', bar:'bg-white/20' };

const REC_STYLE = {
  shortlist: { text: 'text-emerald-400', bg: 'bg-emerald-400/10', border: 'border-emerald-400/30' },
  hold:      { text: 'text-amber-400',   bg: 'bg-amber-400/10',   border: 'border-amber-400/30' },
  reject:    { text: 'text-red-400',     bg: 'bg-red-400/10',     border: 'border-red-400/30' },
};
const recStyle = (r) => REC_STYLE[(r||'').toLowerCase()] || { text:'text-cream/40', bg:'bg-white/5', border:'border-white/10' };

const ENG_STYLE = {
  high:   { text: 'text-emerald-400', bg: 'bg-emerald-400/10', border: 'border-emerald-400/20' },
  medium: { text: 'text-amber-400',   bg: 'bg-amber-400/10',   border: 'border-amber-400/20' },
  low:    { text: 'text-red-400',     bg: 'bg-red-400/10',     border: 'border-red-400/20' },
};
const engStyle = (e) => ENG_STYLE[(e||'').toLowerCase()] || { text:'text-cream/40', bg:'bg-white/5', border:'border-white/10' };

const scoreColor = (s) => {
  if (s == null) return 'text-cream/30';
  if (s >= 8)   return 'text-emerald-400';
  if (s >= 6)   return 'text-amber-400';
  return 'text-red-400';
};

const scoreBar = (s) => {
  if (s == null) return 'bg-white/10';
  if (s >= 8)   return 'bg-emerald-400';
  if (s >= 6)   return 'bg-amber-400';
  return 'bg-red-400';
};

// ── Status helpers ────────────────────────────────────────────────────────────

const getStatus = (s) => {
  if (s.intent_score != null) return 'evaluated';
  if ((s.transcript_length || 0) > 0) return 'answered';
  return 'pending';
};

const STATUS_CFG = {
  evaluated: { label: 'Evaluated',  cls: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20', Icon: BadgeCheck },
  answered:  { label: 'Answered',   cls: 'text-sky-400 bg-sky-400/10 border-sky-400/20',             Icon: Phone },
  pending:   { label: 'No Answer',  cls: 'text-amber-400 bg-amber-400/10 border-amber-400/20',       Icon: PhoneMissed },
};

// ── Checkpoint map ────────────────────────────────────────────────────────────

const CHECKPOINTS = [
  { key: 'greeting',            label: 'Greeting & Rapport' },
  { key: 'recruiter-intro',     label: 'Role Introduction' },
  { key: 'candidate-intro',     label: 'Candidate Intro' },
  { key: 'technical-screening', label: 'Technical Depth' },
  { key: 'work-mode',           label: 'Work Mode' },
  { key: 'compensation',        label: 'Compensation' },
  { key: 'role-alignment',      label: 'Role Alignment' },
  { key: 'availability',        label: 'Availability' },
];

// ── Ambient orb (matches landing page) ───────────────────────────────────────
function Orb({ size = 500, color = '#6FFF00', x = 0, y = 0, delay = 0, opacity = 0.06 }) {
  return (
    <motion.div
      className="absolute rounded-full pointer-events-none"
      style={{
        width: size, height: size,
        left: `calc(50% + ${x}px)`, top: `calc(50% + ${y}px)`,
        transform: 'translate(-50%, -50%)',
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        filter: 'blur(90px)', opacity,
      }}
      animate={{ x: [0, 40, -25, 0], y: [0, -35, 45, 0], scale: [1, 1.12, 0.9, 1] }}
      transition={{ duration: 14, delay, repeat: Infinity, ease: 'easeInOut' }}
    />
  );
}

// ── Mini components ───────────────────────────────────────────────────────────

const Pill = ({ children, style, size = 'sm' }) => (
  <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-black uppercase tracking-[0.2em] ${size === 'xs' ? 'text-[9px]' : 'text-[10px]'} ${style.text} ${style.bg} ${style.border}`}>
    {children}
  </span>
);

const SectionHeader = ({ icon: Icon, label }) => (
  <div className="flex items-center gap-2 mb-4">
    <Icon size={13} className="text-neon/50 flex-shrink-0" />
    <p className="text-[10px] font-black uppercase tracking-[0.4em] text-cream/40">{label}</p>
  </div>
);

const DataPoint = ({ label, value, accent }) => (
  <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3">
    <p className="text-[10px] uppercase tracking-[0.3em] text-cream/35 mb-1">{label}</p>
    <p className={`text-sm font-bold ${accent || 'text-cream'}`}>{value ?? '—'}</p>
  </div>
);

const ScoreBar = ({ score, label, confidence, evidence }) => {
  const width = score != null ? `${score * 10}%` : '0%';
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.25em] text-cream/50">{label}</p>
        <div className="flex items-center gap-2">
          {confidence != null && (
            <span className="text-[9px] text-cream/30 font-mono">{Math.round(confidence * 100)}% conf.</span>
          )}
          <span className={`text-lg font-black ${scoreColor(score)}`}>
            {score ?? '—'}<span className="text-xs text-cream/20 font-normal">/10</span>
          </span>
        </div>
      </div>
      <div className="h-1.5 w-full rounded-full bg-white/5">
        <div className={`h-1.5 rounded-full transition-all ${scoreBar(score)}`} style={{ width }} />
      </div>
      {(evidence || []).length > 0 && (
        <ul className="mt-2 space-y-1">
          {evidence.slice(0, 3).map((e, i) => (
            <li key={i} className="text-[11px] text-cream/40 leading-5 pl-3 border-l border-white/10 italic">"{e}"</li>
          ))}
        </ul>
      )}
    </div>
  );
};

// ── KPI card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon: Icon, color, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
      className="liquid-glass rounded-[24px] border border-white/[0.06] p-5 relative overflow-hidden group"
    >
      {/* subtle neon corner accent */}
      <div className={`absolute top-0 right-0 w-16 h-16 rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500`}
        style={{ background: `radial-gradient(circle at top right, rgba(111,255,0,0.08), transparent)` }} />
      <div className="flex items-start justify-between mb-3">
        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/40">{label}</p>
        <Icon size={15} className={`${color} opacity-50`} />
      </div>
      <p className={`text-3xl font-black font-grotesk ${color}`}>{value}</p>
      <p className="text-[10px] font-mono text-cream/25 mt-1.5 uppercase tracking-wider">{sub}</p>
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Dashboard
// ═══════════════════════════════════════════════════════════════════════════════

export default function DashboardPage() {
  const [sessions, setSessions]     = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState('');
  const [expanded, setExpanded]     = useState({});
  const [sortBy, setSortBy]         = useState('created_at');
  const [filterStatus, setFilter]   = useState('all');
  const [refreshing, setRefreshing] = useState(false);

  const fetchSessions = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setLoading(true);
    setError('');
    try {
      const res  = await fetch(`${API_BASE}/api/sessions/`);
      const data = await res.json();
      if (res.ok && data.status === 'success') setSessions(data.sessions || []);
      else setError(data.message || 'Failed to load sessions');
    } catch { setError('Could not connect to the API'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  useEffect(() => {
    const cutoff = Date.now() - 30 * 60 * 1000;
    const hasActive = sessions.some(s => !s.ended_at && new Date(s.created_at).getTime() > cutoff);
    if (!hasActive) return;
    const id = setInterval(() => fetchSessions(true), 10000);
    return () => clearInterval(id);
  }, [sessions, fetchSessions]);

  // ── Analytics ───────────────────────────────────────────────────────────────

  const total         = sessions.length;
  const answered      = sessions.filter(s => (s.transcript_length || 0) > 0).length;
  const evaluated     = sessions.filter(s => s.intent_score != null).length;
  const interested    = sessions.filter(s => (s.call_outcome || '').toUpperCase() === 'INTERESTED').length;
  const shortlisted   = sessions.filter(s => (s.candidate_summary?.recommendation || '') === 'shortlist').length;
  const hrFlagged     = sessions.filter(s => (s.notes?.hr_flags || []).length > 0).length;

  const scoredSes     = sessions.filter(s => typeof s.intent_score === 'number');
  const avgScore      = scoredSes.length ? (scoredSes.reduce((a, s) => a + s.intent_score, 0) / scoredSes.length).toFixed(1) : null;

  const avgConfidence = (() => {
    const c = sessions.filter(s => s.eval_confidence != null);
    return c.length ? Math.round(c.reduce((a, s) => a + s.eval_confidence, 0) / c.length * 100) : null;
  })();

  const outcomeCounts = sessions.reduce((acc, s) => {
    const k = s.call_outcome || 'Pending'; acc[k] = (acc[k] || 0) + 1; return acc;
  }, {});

  const compatCounts = sessions.reduce((acc, s) => {
    const k = s.candidate_summary?.compatibility_level || 'unknown'; acc[k] = (acc[k] || 0) + 1; return acc;
  }, {});

  const dimAvg = (() => {
    const dims = { technical_fit: [], communication: [], motivation_fit: [], logistics_fit: [] };
    sessions.forEach(s => {
      Object.keys(dims).forEach(k => {
        const v = (s.dimension_scores || {})[k];
        if (v?.score != null) dims[k].push(v.score);
      });
    });
    return Object.fromEntries(
      Object.entries(dims).map(([k, arr]) => [k, arr.length ? (arr.reduce((a, v) => a + v, 0) / arr.length).toFixed(1) : null])
    );
  })();

  const skillFreq = sessions.flatMap(s => s.notes?.skills_verified || [])
    .reduce((acc, sk) => { acc[sk] = (acc[sk] || 0) + 1; return acc; }, {});
  const topSkills = Object.entries(skillFreq).sort((a, b) => b[1] - a[1]).slice(0, 10);

  const filtered = sessions
    .filter(s => filterStatus === 'all' || getStatus(s) === filterStatus)
    .sort((a, b) => {
      if (sortBy === 'score')  return (b.intent_score ?? -1) - (a.intent_score ?? -1);
      if (sortBy === 'name')   return a.candidate_name.localeCompare(b.candidate_name);
      return new Date(b.created_at) - new Date(a.created_at);
    });

  const toggle = (id) => setExpanded(p => ({ ...p, [id]: !p[id] }));

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <main className="relative min-h-screen bg-background text-cream overflow-x-hidden pb-28 font-sans selection:bg-neon selection:text-background">

      {/* Ambient orbs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <Orb size={900} color="#6FFF00" x={-500} y={100}  delay={0} opacity={0.028} />
        <Orb size={700} color="#3b5bff" x={500}  y={300}  delay={4} opacity={0.035} />
        <Orb size={400} color="#6FFF00" x={200}  y={600}  delay={8} opacity={0.02}  />
      </div>

      <div className="relative z-10 mx-auto max-w-[1320px] px-6 py-10 sm:px-10">

        {/* ── Page header ──────────────────────────────────────────────────── */}
        <div className="mb-12">
          <Link to="/app" className="inline-flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.3em] text-cream/35 hover:text-neon transition-colors mb-6">
            <ArrowLeft size={12} /> Back to App
          </Link>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-start justify-between gap-6 flex-wrap"
          >
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.35em] text-neon mb-4 flex items-center gap-2">
                <Sparkles size={11} /> Recruitment Command Centre
              </p>
              <h1 className="font-grotesk uppercase text-[42px] sm:text-[58px] leading-none tracking-tighter">
                Candidate Pipeline<br />
                <span className="text-neon">Intelligence</span>
              </h1>
              <div className="w-20 h-[3px] bg-neon mt-5" />
            </div>

            <motion.button
              onClick={() => fetchSessions(true)}
              disabled={refreshing}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              className="mt-2 liquid-glass inline-flex items-center gap-2 rounded-2xl border border-white/[0.08] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-cream/50 hover:border-neon/40 hover:text-neon transition-all disabled:opacity-40"
            >
              <RefreshCw size={12} className={refreshing ? 'animate-spin text-neon' : ''} />
              Refresh
            </motion.button>
          </motion.div>
        </div>

        {/* ── Tier 1: Primary KPIs ─────────────────────────────────────────── */}
        <div className="mb-6 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {[
            { label: 'Total Calls',   value: total,       sub: 'initiated',        icon: Phone,         color: 'text-neon' },
            { label: 'Answered',      value: answered,    sub: `${pct(answered, total)}% pickup`,       icon: CheckCircle,   color: 'text-sky-400' },
            { label: 'Evaluated',     value: evaluated,   sub: 'AI scored',        icon: BarChart3,     color: 'text-violet-400' },
            { label: 'Interested',    value: interested,  sub: 'want to proceed',  icon: Star,          color: 'text-emerald-400' },
            { label: 'Shortlisted',   value: shortlisted, sub: 'ready to advance', icon: Target,        color: 'text-emerald-300' },
            { label: 'HR Flagged',    value: hrFlagged,   sub: 'need review',      icon: AlertTriangle, color: 'text-red-400' },
          ].map(({ label, value, sub, icon, color }, i) => (
            <KpiCard key={label} label={label} value={value} sub={sub} icon={icon} color={color} delay={i * 0.07} />
          ))}
        </div>

        {/* ── Tier 2: Quality metrics row ──────────────────────────────────── */}
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              icon: Award, iconColor: 'text-amber-400',
              label: 'Avg Intent Score',
              value: avgScore != null
                ? <>{<span className={scoreColor(parseFloat(avgScore))}>{avgScore}</span>}<span className="text-sm text-cream/30 ml-1">/10</span></>
                : <span className="text-cream/30">—</span>,
            },
            {
              icon: Activity, iconColor: 'text-violet-400',
              label: 'Eval Confidence',
              value: <span className="text-violet-400">{avgConfidence != null ? `${avgConfidence}%` : '—'}</span>,
            },
            {
              icon: TrendingUp, iconColor: 'text-sky-400',
              label: 'Answer Rate',
              value: <span className="text-sky-400">{total ? `${pct(answered, total)}%` : '—'}</span>,
            },
            {
              icon: Layers, iconColor: 'text-emerald-400',
              label: 'Conversion',
              value: <span className="text-emerald-400">{answered ? `${pct(interested, answered)}%` : '—'}</span>,
              sub: 'answered → interested',
            },
          ].map(({ icon: Icon, iconColor, label, value, sub }, i) => (
            <motion.div key={label}
              initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.42 + i * 0.07, ease: [0.16, 1, 0.3, 1] }}
              className="liquid-glass rounded-[24px] border border-white/[0.06] px-6 py-5 flex items-center gap-4"
            >
              <Icon size={28} className={`${iconColor} flex-shrink-0 opacity-70`} />
              <div>
                <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35">{label}</p>
                <p className="text-3xl font-black font-grotesk mt-1">{value}</p>
                {sub && <p className="text-[10px] font-mono text-cream/25 mt-0.5">{sub}</p>}
              </div>
            </motion.div>
          ))}
        </div>

        {/* ── Tier 3: Insights panels ──────────────────────────────────────── */}
        <div className="mb-8 grid gap-6 lg:grid-cols-3">

          {/* Outcome breakdown */}
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className="liquid-glass rounded-[28px] border border-white/[0.06] p-6"
          >
            <SectionHeader icon={BarChart3} label="Call Outcomes" />
            {Object.keys(outcomeCounts).length === 0
              ? <p className="text-sm text-cream/25 font-mono">No data yet</p>
              : <div className="space-y-2.5">
                  {Object.entries(outcomeCounts).sort((a, b) => b[1] - a[1]).map(([label, count]) => {
                    const st = outcomeStyle(label);
                    return (
                      <div key={label} className={`flex items-center justify-between rounded-2xl border px-4 py-3 ${st.bg} ${st.border}`}>
                        <span className={`text-[11px] font-black uppercase tracking-[0.2em] ${st.text}`}>{label}</span>
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1 rounded-full bg-white/10">
                            <div className={`h-1 rounded-full ${st.text.replace('text-', 'bg-')}`} style={{ width: `${pct(count, total)}%` }} />
                          </div>
                          <span className="text-sm font-black text-cream w-6 text-right">{count}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
            }
          </motion.div>

          {/* Compatibility pipeline */}
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.77, ease: [0.16, 1, 0.3, 1] }}
            className="liquid-glass rounded-[28px] border border-white/[0.06] p-6"
          >
            <SectionHeader icon={Layers} label="Compatibility Pipeline" />
            {Object.keys(compatCounts).length === 0
              ? <p className="text-sm text-cream/25 font-mono">No data yet</p>
              : <div className="space-y-4">
                  {['green', 'yellow', 'red', 'unknown'].map(level => {
                    const count = compatCounts[level] || 0;
                    if (!count) return null;
                    const cs = compatStyle(level);
                    return (
                      <div key={level}>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className={`text-[10px] font-black uppercase tracking-[0.3em] ${cs.text}`}>{level}</span>
                          <span className="text-sm font-black text-cream">{count} <span className="text-cream/30 text-xs font-normal">({pct(count, total)}%)</span></span>
                        </div>
                        <div className="h-2 rounded-full bg-white/5">
                          <motion.div className={`h-2 rounded-full ${cs.bar}`} initial={{ width: 0 }} animate={{ width: `${pct(count, total)}%` }} transition={{ duration: 0.8, ease: 'easeOut' }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
            }
          </motion.div>

          {/* Verified skills cloud */}
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.84, ease: [0.16, 1, 0.3, 1] }}
            className="liquid-glass rounded-[28px] border border-white/[0.06] p-6"
          >
            <SectionHeader icon={Briefcase} label="Verified Skills Intelligence" />
            {topSkills.length === 0
              ? <p className="text-sm text-cream/25 font-mono">No verified skills yet</p>
              : <div className="flex flex-wrap gap-2">
                  {topSkills.map(([skill, count]) => (
                    <span key={skill} className="inline-flex items-center gap-1.5 rounded-full border border-neon/25 bg-neon/5 px-3 py-1 text-[10px] font-black uppercase tracking-[0.15em] text-neon">
                      {skill}
                      <span className="rounded-full bg-neon/20 px-1.5 py-0.5 text-[9px]">{count}</span>
                    </span>
                  ))}
                </div>
            }
          </motion.div>
        </div>

        {/* ── Avg dimension scores ─────────────────────────────────────────── */}
        {evaluated > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.9, ease: [0.16, 1, 0.3, 1] }}
            className="mb-8 liquid-glass rounded-[28px] border border-white/[0.06] p-6"
          >
            <SectionHeader icon={Activity} label="Average Dimension Scores — Across All Evaluated Calls" />
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { key: 'technical_fit',  label: 'Technical Fit' },
                { key: 'communication',  label: 'Communication' },
                { key: 'motivation_fit', label: 'Motivation Fit' },
                { key: 'logistics_fit',  label: 'Logistics Fit' },
              ].map(({ key, label }) => {
                const val = parseFloat(dimAvg[key]);
                return (
                  <div key={key} className="space-y-2">
                    <div className="flex justify-between">
                      <p className="text-[10px] font-mono uppercase tracking-[0.25em] text-cream/40">{label}</p>
                      <span className={`text-lg font-black ${scoreColor(val)}`}>{dimAvg[key] ?? '—'}</span>
                    </div>
                    <div className="h-2 rounded-full bg-white/5">
                      <motion.div className={`h-2 rounded-full ${scoreBar(val)}`} initial={{ width: 0 }}
                        animate={{ width: dimAvg[key] ? `${val * 10}%` : '0%' }} transition={{ duration: 0.9, ease: 'easeOut' }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* ── Top candidates table ─────────────────────────────────────────── */}
        {scoredSes.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.95, ease: [0.16, 1, 0.3, 1] }}
            className="mb-8 liquid-glass rounded-[28px] border border-white/[0.06] p-6"
          >
            <SectionHeader icon={TrendingUp} label="Top Candidates — Ranked by Intent Score" />
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-white/[0.07]">
                    {['Rank','Candidate','Score','Outcome','Fit','Recommendation','Current CTC','Expected CTC','Notice','Engagement','Called'].map(h => (
                      <th key={h} className="pb-3 pr-4 text-left text-[9px] font-mono uppercase tracking-[0.35em] text-cream/25 font-normal whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...scoredSes].sort((a, b) => b.intent_score - a.intent_score).slice(0, 8).map((s, i) => {
                    const n = s.notes || {};
                    const cs = s.candidate_summary || {};
                    return (
                      <tr key={s.id ?? i} className="border-b border-white/[0.04] hover:bg-neon/[0.02] transition-colors">
                        <td className="py-3 pr-4 text-cream/20 font-black text-xs">#{i + 1}</td>
                        <td className="py-3 pr-4">
                          <p className="font-semibold text-cream text-sm">{s.candidate_name}</p>
                          <p className="text-[10px] text-cream/30 font-mono">{s.candidate_phone || '—'}</p>
                        </td>
                        <td className="py-3 pr-4">
                          <span className={`text-2xl font-black font-grotesk ${scoreColor(s.intent_score)}`}>{s.intent_score}</span>
                          <span className="text-cream/20 text-xs">/10</span>
                        </td>
                        <td className="py-3 pr-4"><Pill style={outcomeStyle(s.call_outcome)} size="xs">{s.call_outcome || '—'}</Pill></td>
                        <td className="py-3 pr-4"><Pill style={compatStyle(cs.compatibility_level)} size="xs">{cs.compatibility_level || '—'}</Pill></td>
                        <td className="py-3 pr-4"><Pill style={recStyle(cs.recommendation)} size="xs">{cs.recommendation || '—'}</Pill></td>
                        <td className="py-3 pr-4 text-cream/50 text-xs font-mono">{n.current_ctc_lpa != null ? `${n.current_ctc_lpa} LPA` : '—'}</td>
                        <td className="py-3 pr-4 text-cream/50 text-xs font-mono">{n.salary_expectation_lpa != null ? `${n.salary_expectation_lpa} LPA` : '—'}</td>
                        <td className="py-3 pr-4 text-cream/50 text-xs font-mono">{n.notice_period_days != null ? `${n.notice_period_days}d` : '—'}</td>
                        <td className="py-3 pr-4">
                          {n.engagement_level ? <Pill style={engStyle(n.engagement_level)} size="xs">{n.engagement_level}</Pill> : <span className="text-cream/20">—</span>}
                        </td>
                        <td className="py-3 text-cream/25 text-xs whitespace-nowrap font-mono">{fmt(s.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}

        {/* ── Session list ─────────────────────────────────────────────────── */}
        <div className="space-y-5">
          <motion.div
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 1.0, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="text-[10px] font-mono uppercase tracking-[0.35em] text-cream/35">Full call log</p>
              <h2 className="mt-1 text-2xl font-grotesk uppercase tracking-tight text-cream">All Candidate Sessions</h2>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex rounded-2xl border border-white/[0.08] liquid-glass overflow-hidden">
                {['all', 'evaluated', 'answered', 'pending'].map(f => (
                  <button key={f} onClick={() => setFilter(f)}
                    className={`px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] transition-colors ${filterStatus === f ? 'bg-neon text-background' : 'text-cream/40 hover:text-cream'}`}>
                    {f}
                  </button>
                ))}
              </div>
              <select value={sortBy} onChange={e => setSortBy(e.target.value)}
                className="liquid-glass rounded-2xl border border-white/[0.08] bg-background px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-cream/45 outline-none">
                <option value="created_at">Latest first</option>
                <option value="score">Highest score</option>
                <option value="name">Name A–Z</option>
              </select>
            </div>
          </motion.div>

          {loading && (
            <div className="liquid-glass rounded-[28px] border border-white/[0.06] p-14 text-center text-cream/30 font-mono text-sm">
              Loading sessions…
            </div>
          )}
          {error && (
            <div className="rounded-[28px] border border-red-500/20 bg-red-500/5 p-5 text-red-300 text-sm">{error}</div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div className="liquid-glass rounded-[28px] border border-white/[0.06] p-14 text-center text-cream/30 font-mono text-sm">
              {filterStatus === 'all' ? 'No sessions recorded yet. Place your first call to get started.' : `No ${filterStatus} sessions found.`}
            </div>
          )}

          <div className="grid gap-4">
            {filtered.map((session, idx) => (
              <CandidateCard
                key={session.id ?? session.call_sid ?? idx}
                session={session}
                isOpen={!!expanded[session.id ?? session.call_sid ?? idx]}
                onToggle={() => toggle(session.id ?? session.call_sid ?? idx)}
              />
            ))}
          </div>
        </div>

      </div>
    </main>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CandidateCard — collapsed + fully expanded
// ═══════════════════════════════════════════════════════════════════════════════

function CandidateCard({ session, isOpen, onToggle }) {
  const n   = session.notes || {};
  const cs  = session.candidate_summary || {};
  const ds  = session.dimension_scores || {};
  const ic  = session.interview_context || {};
  const st  = getStatus(session);
  const cfg = STATUS_CFG[st];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="liquid-glass overflow-hidden rounded-[28px] border border-white/[0.06]"
    >
      {/* ── Collapsed header ─────────────────────────────────────────────── */}
      <button type="button" onClick={onToggle}
        className="w-full px-7 py-5 text-left hover:bg-neon/[0.02] transition-colors">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">

          {/* Left: Identity + meta */}
          <div className="flex items-start gap-5">
            <div className="flex-shrink-0 w-12 h-12 rounded-2xl bg-neon/10 border border-neon/25 flex items-center justify-center text-neon font-black text-lg uppercase font-grotesk">
              {(session.candidate_name || 'C')[0]}
            </div>
            <div className="space-y-2 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-bold text-cream uppercase tracking-tight font-grotesk">
                  {session.candidate_name || 'Candidate'}
                </span>
                <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-[0.2em] ${cfg.cls}`}>
                  <cfg.Icon size={10} /> {cfg.label}
                </span>
                {cs.recommendation && <Pill style={recStyle(cs.recommendation)}>{cs.recommendation}</Pill>}
                {n.engagement_level && <Pill style={engStyle(n.engagement_level)}>{n.engagement_level} engagement</Pill>}
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-cream/30 font-mono">
                {session.candidate_phone && <span className="flex items-center gap-1"><Phone size={10} />{session.candidate_phone}</span>}
                <span className="flex items-center gap-1"><Clock size={10} />{fmt(session.created_at)}</span>
                <span className="flex items-center gap-1"><MapPin size={10} />{session.call_channel || 'twilio'}</span>
                {(session.transcript_length || 0) > 0 && (
                  <span className="flex items-center gap-1"><MessageSquare size={10} />{session.transcript_length} messages</span>
                )}
                {ic.job_title && <span className="flex items-center gap-1"><Briefcase size={10} />{ic.job_title}</span>}
              </div>
              {n.vibe_check && (
                <p className="text-[11px] text-cream/35 italic leading-5 max-w-xl font-mono">"{n.vibe_check}"</p>
              )}
            </div>
          </div>

          {/* Right: Key numbers */}
          <div className="flex flex-wrap items-center gap-2.5 flex-shrink-0">
            <div className="rounded-2xl border border-white/[0.08] bg-background/60 px-4 py-3 text-center min-w-[60px]">
              <p className="text-[9px] font-mono uppercase tracking-[0.3em] text-cream/25">Score</p>
              <p className={`text-2xl font-black font-grotesk mt-0.5 ${scoreColor(session.intent_score)}`}>{session.intent_score ?? '—'}</p>
            </div>
            {session.call_outcome && (
              <div className={`rounded-2xl border px-4 py-3 text-center ${outcomeStyle(session.call_outcome).bg} ${outcomeStyle(session.call_outcome).border}`}>
                <p className="text-[9px] font-mono uppercase tracking-[0.3em] text-cream/25">Outcome</p>
                <p className={`text-[11px] font-black uppercase mt-0.5 ${outcomeStyle(session.call_outcome).text}`}>{session.call_outcome}</p>
              </div>
            )}
            {cs.compatibility_level && (
              <div className={`rounded-2xl border px-4 py-3 text-center ${compatStyle(cs.compatibility_level).bg} ${compatStyle(cs.compatibility_level).border}`}>
                <p className="text-[9px] font-mono uppercase tracking-[0.3em] text-cream/25">Fit</p>
                <p className={`text-[11px] font-black uppercase mt-0.5 ${compatStyle(cs.compatibility_level).text}`}>{cs.compatibility_level}</p>
              </div>
            )}
            {n.notice_period_days != null && (
              <div className="rounded-2xl border border-white/[0.08] bg-background/60 px-4 py-3 text-center">
                <p className="text-[9px] font-mono uppercase tracking-[0.3em] text-cream/25">Notice</p>
                <p className="text-[11px] font-black text-cream mt-0.5">{n.notice_period_days === 0 ? 'Immediate' : `${n.notice_period_days}d`}</p>
              </div>
            )}
            {n.salary_expectation_lpa != null && (
              <div className="rounded-2xl border border-white/[0.08] bg-background/60 px-4 py-3 text-center">
                <p className="text-[9px] font-mono uppercase tracking-[0.3em] text-cream/25">Exp. CTC</p>
                <p className="text-[11px] font-black text-cream mt-0.5">{n.salary_expectation_lpa} LPA</p>
              </div>
            )}
            {(n.hr_flags || []).length > 0 && (
              <div className="rounded-2xl border border-red-400/20 bg-red-400/5 px-4 py-3 text-center">
                <p className="text-[9px] font-mono uppercase tracking-[0.3em] text-red-400/50">Flags</p>
                <p className="text-[11px] font-black text-red-400 mt-0.5">{n.hr_flags.length}</p>
              </div>
            )}
            <div className="rounded-full border border-white/[0.08] bg-background/50 p-2.5 text-cream/25">
              {isOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </div>
          </div>

        </div>
      </button>

      {/* ── Expanded panel ───────────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div key="body"
            initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.28 }}
            className="overflow-hidden">
            <div className="border-t border-white/[0.06] px-7 py-7 space-y-8">

              {/* 1 ── Executive Decision */}
              <Section icon={Target} label="Executive Decision">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <DataPoint label="Intent Score" value={session.intent_score != null ? `${session.intent_score} / 10` : null} accent={scoreColor(session.intent_score)} />
                  <DataPoint label="Eval Confidence" value={session.eval_confidence != null ? `${Math.round(session.eval_confidence * 100)}%` : null} />
                  <DataPoint label="Call Outcome" value={session.call_outcome} accent={outcomeStyle(session.call_outcome).text} />
                  <DataPoint label="Compatibility" value={cs.compatibility_level ? cs.compatibility_level.toUpperCase() : null} accent={cs.compatibility_level ? compatStyle(cs.compatibility_level).text : null} />
                </div>
                {n.recommended_next_step && (
                  <div className="mt-4 flex items-start gap-3 rounded-2xl border border-neon/15 bg-neon/[0.04] px-5 py-4">
                    <ArrowRight size={14} className="text-neon flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-[10px] font-mono uppercase tracking-[0.35em] text-neon/50 mb-1">Recommended Next Step</p>
                      <p className="text-sm text-cream/75 leading-6">{n.recommended_next_step}</p>
                    </div>
                  </div>
                )}
                {cs.recommendation && (
                  <div className="mt-3 flex items-start gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.02] px-5 py-4">
                    <Info size={14} className="text-cream/25 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-[10px] font-mono uppercase tracking-[0.35em] text-cream/35">Recommendation</p>
                        <Pill style={recStyle(cs.recommendation)}>{cs.recommendation}</Pill>
                      </div>
                      <p className="text-sm text-cream/55 leading-6">{cs.recommendation_reason || '—'}</p>
                    </div>
                  </div>
                )}
              </Section>

              {/* 2 ── Logistics */}
              <Section icon={DollarSign} label="Logistics & Availability">
                <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  <DataPoint label="Current CTC" value={n.current_ctc_lpa != null ? `${n.current_ctc_lpa} LPA` : null} />
                  <DataPoint label="Expected CTC" value={n.salary_expectation_lpa != null ? `${n.salary_expectation_lpa} LPA` : null} />
                  {ic.ctc_range && <DataPoint label="Offered Range" value={ic.ctc_range} accent="text-neon" />}
                  <DataPoint label="Notice Period" value={n.notice_period_days != null ? (n.notice_period_days === 0 ? 'Immediate' : `${n.notice_period_days} days`) : null} />
                  <DataPoint label="Joining Timeline" value={n.joining_timeline} />
                  <DataPoint label="Other Offers" value={n.other_offers === true ? 'Yes — competing offers' : n.other_offers === false ? 'No other offers' : null}
                    accent={n.other_offers === true ? 'text-amber-400' : 'text-emerald-400'} />
                  {ic.work_location_type && <DataPoint label="Work Mode" value={ic.work_location_type} />}
                  {ic.company_location && <DataPoint label="Location" value={ic.company_location} />}
                </div>
              </Section>

              {/* 3 ── Checkpoints */}
              {(n.checkpoints_completed || []).length > 0 && (
                <Section icon={CheckCircle2} label={`Screening Checkpoints — ${n.checkpoints_completed.length}/8 Covered`}>
                  <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
                    {CHECKPOINTS.map(cp => {
                      const done = (n.checkpoints_completed || []).includes(cp.key);
                      return (
                        <div key={cp.key} className={`flex items-center gap-3 rounded-2xl border px-4 py-3 ${done ? 'border-emerald-400/20 bg-emerald-400/[0.04]' : 'border-white/[0.05] bg-white/[0.02]'}`}>
                          {done
                            ? <CheckCircle2 size={14} className="text-emerald-400 flex-shrink-0" />
                            : <XCircle size={14} className="text-white/10 flex-shrink-0" />
                          }
                          <span className={`text-[11px] font-semibold uppercase tracking-[0.15em] ${done ? 'text-emerald-300' : 'text-cream/20'}`}>{cp.label}</span>
                        </div>
                      );
                    })}
                  </div>
                </Section>
              )}

              {/* 4 ── Dimension Scorecard */}
              {Object.values(ds).some(v => v != null) && (
                <Section icon={BarChart3} label="AI Dimension Scorecard — With Evidence">
                  <div className="grid gap-6 sm:grid-cols-2">
                    {[
                      { key: 'technical_fit',  label: 'Technical Fit' },
                      { key: 'communication',  label: 'Communication' },
                      { key: 'motivation_fit', label: 'Motivation Fit' },
                      { key: 'logistics_fit',  label: 'Logistics Fit' },
                    ].filter(({ key }) => ds[key] != null).map(({ key, label }) => (
                      <div key={key} className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5">
                        <ScoreBar score={ds[key].score} label={label} confidence={ds[key].confidence} evidence={ds[key].evidence} />
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* 5 ── Behavioural Signals */}
              {(n.interest_indicators?.length > 0 || n.concern_indicators?.length > 0 || n.tone_signals?.length > 0) && (
                <Section icon={Activity} label="Behavioural Signals & Engagement">
                  <div className="grid gap-5 sm:grid-cols-3">
                    {n.interest_indicators?.length > 0 && (
                      <div className="rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.04] p-5">
                        <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] text-emerald-400/60 mb-3">
                          <ThumbsUp size={11} /> Interest Signals
                        </p>
                        <ul className="space-y-2">
                          {n.interest_indicators.map((x, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-cream/55 leading-5">
                              <span className="mt-1.5 w-1 h-1 rounded-full bg-emerald-400 flex-shrink-0" />{x}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {n.concern_indicators?.length > 0 && (
                      <div className="rounded-2xl border border-red-400/15 bg-red-400/[0.04] p-5">
                        <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] text-red-400/60 mb-3">
                          <ThumbsDown size={11} /> Concern Signals
                        </p>
                        <ul className="space-y-2">
                          {n.concern_indicators.map((x, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-cream/55 leading-5">
                              <span className="mt-1.5 w-1 h-1 rounded-full bg-red-400 flex-shrink-0" />{x}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {n.tone_signals?.length > 0 && (
                      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5">
                        <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] text-cream/35 mb-3">
                          <Eye size={11} /> Tone Observations
                        </p>
                        <ul className="space-y-2">
                          {n.tone_signals.map((x, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-cream/55 leading-5">
                              <span className="mt-1.5 w-1 h-1 rounded-full bg-white/25 flex-shrink-0" />{x}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                  {n.engagement_level && (
                    <div className="mt-4 flex items-center gap-3">
                      <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35">Overall Engagement:</p>
                      <Pill style={engStyle(n.engagement_level)}>{n.engagement_level}</Pill>
                    </div>
                  )}
                </Section>
              )}

              {/* 6 ── Fit Analysis */}
              {(cs.match_points?.length > 0 || cs.gap_points?.length > 0 || cs.missing_skills?.length > 0 || cs.red_flags?.length > 0) && (
                <Section icon={Layers} label="Role Fit Analysis">
                  <div className="grid gap-5 sm:grid-cols-2">
                    {cs.match_points?.length > 0 && (
                      <div className="rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.04] p-5">
                        <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] text-emerald-400/60 mb-3">
                          <CheckCircle size={11} /> Match Points
                        </p>
                        <ul className="space-y-2">
                          {cs.match_points.map((x, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-cream/60 leading-5">
                              <CheckCircle size={11} className="text-emerald-400 flex-shrink-0 mt-0.5" />{x}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {cs.gap_points?.length > 0 && (
                      <div className="rounded-2xl border border-amber-400/15 bg-amber-400/[0.04] p-5">
                        <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] text-amber-400/60 mb-3">
                          <AlertTriangle size={11} /> Gap Points
                        </p>
                        <ul className="space-y-2">
                          {cs.gap_points.map((x, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-cream/60 leading-5">
                              <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-400 flex-shrink-0" />{x}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                  {cs.missing_skills?.length > 0 && (
                    <div className="mt-4">
                      <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35 mb-2">Missing Required Skills</p>
                      <div className="flex flex-wrap gap-2">
                        {cs.missing_skills.map(sk => (
                          <span key={sk} className="rounded-full border border-red-400/20 bg-red-400/5 px-3 py-1 text-[10px] font-black uppercase tracking-[0.15em] text-red-300">{sk}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {cs.red_flags?.length > 0 && (
                    <div className="mt-4 space-y-2">
                      <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-red-400/50 flex items-center gap-2"><Shield size={10} /> Hard Blockers</p>
                      {cs.red_flags.map((f, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-red-300 leading-5">
                          <XCircle size={11} className="flex-shrink-0 mt-0.5" />{f}
                        </div>
                      ))}
                    </div>
                  )}
                  {cs.compatibility_reason && (
                    <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
                      <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/30 mb-1">Compatibility Verdict</p>
                      <p className="text-sm text-cream/65 leading-6">{cs.compatibility_reason}</p>
                    </div>
                  )}
                </Section>
              )}

              {/* 7 ── HR Notes & Skills */}
              <Section icon={Shield} label="HR Notes & Verified Skills">
                <div className="grid gap-5 sm:grid-cols-2">
                  <div>
                    {(n.hr_flags || []).length > 0 ? (
                      <div className="rounded-2xl border border-red-400/15 bg-red-400/[0.04] p-5">
                        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-red-400/50 mb-3 flex items-center gap-2">
                          <AlertTriangle size={11} /> HR Flags — Action Required
                        </p>
                        <ul className="space-y-2">
                          {n.hr_flags.map((f, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-red-200/75 leading-5">
                              <Shield size={10} className="flex-shrink-0 mt-0.5 text-red-400" />{f}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-emerald-400/10 bg-emerald-400/[0.04] px-5 py-4 flex items-center gap-3">
                        <Shield size={14} className="text-emerald-400" />
                        <p className="text-sm text-emerald-300">No HR flags raised</p>
                      </div>
                    )}
                  </div>
                  <div>
                    {(n.skills_verified || []).length > 0 ? (
                      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5">
                        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35 mb-3 flex items-center gap-2">
                          <BadgeCheck size={11} /> Skills Confirmed on Call
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {n.skills_verified.map(sk => (
                            <span key={sk} className="rounded-full border border-neon/25 bg-neon/5 px-3 py-1 text-[10px] font-black uppercase tracking-[0.15em] text-neon">{sk}</span>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] px-5 py-4">
                        <p className="text-sm text-cream/25 font-mono">No skills verified on this call</p>
                      </div>
                    )}
                  </div>
                </div>
                {n.vibe_check && (
                  <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.02] px-5 py-4">
                    <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/30 mb-1.5">Vibe Check</p>
                    <p className="text-sm text-cream/65 leading-6 italic">"{n.vibe_check}"</p>
                  </div>
                )}
              </Section>

              {/* 8 ── AI Reasoning */}
              <Section icon={Zap} label="AI Evaluation Reasoning">
                {(n.summary_bullets || cs.summary_bullets || []).length > 0 && (
                  <div className="mb-4 rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5">
                    <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35 mb-3">Key Observations</p>
                    <ul className="space-y-2">
                      {(n.summary_bullets?.length ? n.summary_bullets : cs.summary_bullets || []).map((b, i) => (
                        <li key={i} className="flex items-start gap-2.5 text-sm text-cream/60 leading-6">
                          <span className="mt-2 inline-block w-1.5 h-1.5 rounded-full bg-neon flex-shrink-0" />{b}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {(session.eval_reasoning || n.reasoning) && (
                  <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5">
                    <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35 mb-3">Evaluator Reasoning</p>
                    <p className="text-sm text-cream/55 leading-7 whitespace-pre-wrap">
                      {session.eval_reasoning || n.reasoning}
                    </p>
                  </div>
                )}
              </Section>

              {/* 9 ── Role Context */}
              {(session.job_description || session.resume_text) && (
                <Section icon={FileText} label="Role Context & Resume">
                  <div className="grid gap-5 sm:grid-cols-2">
                    {session.job_description && (
                      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5">
                        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35 mb-3">Job Description</p>
                        <p className="text-xs text-cream/45 leading-6 whitespace-pre-line">{clip(session.job_description, 800)}</p>
                      </div>
                    )}
                    {session.resume_text && (
                      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5">
                        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-cream/35 mb-3">Candidate Resume</p>
                        <p className="text-xs text-cream/45 leading-6 whitespace-pre-line">{clip(session.resume_text, 800)}</p>
                      </div>
                    )}
                  </div>
                </Section>
              )}

              {/* 10 ── Transcript */}
              {(session.transcript || []).length > 0 && (
                <Section icon={MessageSquare} label={`Full Call Transcript — ${session.transcript.length} Messages`}>
                  <div className="max-h-[600px] overflow-y-auto space-y-3 pr-1 rounded-2xl border border-white/[0.07] bg-background/60 p-5">
                    {session.transcript.map((msg, i) => {
                      const isAI = msg.role === 'assistant';
                      return (
                        <div key={i} className={`flex gap-3 ${isAI ? '' : 'flex-row-reverse'}`}>
                          <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-black uppercase ${isAI ? 'bg-neon/15 text-neon border border-neon/25' : 'bg-white/[0.07] text-cream/50 border border-white/[0.08]'}`}>
                            {isAI ? 'AI' : (session.candidate_name?.[0] || 'C')}
                          </div>
                          <div className={`max-w-[78%] rounded-2xl px-4 py-3 ${isAI ? 'bg-neon/[0.04] border border-neon/10 rounded-tl-sm' : 'bg-white/[0.04] border border-white/[0.07] rounded-tr-sm'}`}>
                            <p className={`text-[9px] font-black font-mono uppercase tracking-[0.25em] mb-1 ${isAI ? 'text-neon/45' : 'text-cream/20'}`}>
                              {isAI ? 'Priya AI' : (session.candidate_name || 'Candidate')}
                            </p>
                            <p className="text-sm text-cream/65 leading-6">{msg.content}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Section>
              )}

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({ icon: Icon, label, children }) {
  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4 pb-3 border-b border-white/[0.05]">
        <div className="w-6 h-6 rounded-lg bg-neon/[0.07] border border-neon/15 flex items-center justify-center">
          <Icon size={12} className="text-neon/50" />
        </div>
        <p className="text-[10px] font-black font-mono uppercase tracking-[0.4em] text-cream/35">{label}</p>
      </div>
      {children}
    </div>
  );
}
