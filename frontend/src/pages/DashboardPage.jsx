import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  BarChart3,
  CheckCircle,
  Clock,
  Sparkles,
  Users,
  Zap,
  FileText,
  Search,
  MapPin,
  Heart,
  ArrowLeft,
} from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

const formatDate = (isoString) => {
  if (!isoString) return '—';
  const date = new Date(isoString);
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const compactText = (text, length = 160) => {
  if (!text) return '—';
  return text.length > length ? `${text.slice(0, length)}…` : text;
};

export default function DashboardPage() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    const fetchSessions = async () => {
      setLoading(true);
      setError('');

      try {
        const res = await fetch(`${API_BASE}/api/sessions/`);
        const data = await res.json();
        if (res.ok && data.status === 'success') {
          setSessions(data.sessions || []);
        } else {
          setError(data.message || 'Failed to load sessions');
        }
      } catch (err) {
        setError('Could not connect to the API');
      } finally {
        setLoading(false);
      }
    };

    fetchSessions();
  }, []);

  const totalCalls = sessions.length;
  const completedCalls = sessions.filter((s) => !!s.call_outcome).length;
  const averageScore = sessions
    .filter((s) => typeof s.intent_score === 'number')
    .reduce((sum, s) => sum + s.intent_score, 0);
  const scoredCount = sessions.filter((s) => typeof s.intent_score === 'number').length;
  const avgScore = scoredCount ? (averageScore / scoredCount).toFixed(1) : '—';
  const outcomeCounts = sessions.reduce((acc, s) => {
    const key = s.call_outcome || 'Unknown';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const compatibilityCounts = sessions.reduce((acc, s) => {
    const key = (s.candidate_summary || {}).compatibility_level || 'Unknown';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const toggleExpanded = (id) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#0c1119] pb-20">
      <section className="mx-auto max-w-[1180px] px-6 py-10 sm:px-10">
        <div className="mb-6">
          <Link
            to="/app"
            className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-cream/50 hover:text-neon transition-colors"
          >
            <ArrowLeft size={14} /> Back to App
          </Link>
        </div>

        <div className="mb-10 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl space-y-4">
            <p className="inline-flex items-center gap-2 rounded-full border border-neon/20 bg-neon/5 px-4 py-2 text-[11px] uppercase tracking-[0.25em] text-neon">
              <Sparkles className="h-4 w-4" /> Candidate Intelligence Dashboard
            </p>
            <h1 className="text-[42px] font-black uppercase tracking-[-0.04em] text-cream sm:text-[54px]">
              Monitor every call, candidate, and summary in one place.
            </h1>
            <p className="max-w-2xl text-sm leading-7 text-cream/70 sm:text-base">
              See how many candidates were called, review session summaries, compare evaluation outcomes,
              and inspect full details for every candidate screening.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-[28px] border border-white/5 bg-white/5 p-6 shadow-[0_25px_80px_rgba(15,23,42,0.25)]">
              <p className="text-[11px] uppercase tracking-[0.32em] text-cream/60">Total calls</p>
              <div className="mt-4 flex items-center gap-3">
                <Users className="h-6 w-6 text-neon" />
                <div>
                  <p className="text-3xl font-black text-cream">{totalCalls}</p>
                  <p className="text-xs uppercase text-cream/50">candidate sessions</p>
                </div>
              </div>
            </div>
            <div className="rounded-[28px] border border-white/5 bg-white/5 p-6 shadow-[0_25px_80px_rgba(15,23,42,0.25)]">
              <p className="text-[11px] uppercase tracking-[0.32em] text-cream/60">Completed</p>
              <div className="mt-4 flex items-center gap-3">
                <CheckCircle className="h-6 w-6 text-emerald-400" />
                <div>
                  <p className="text-3xl font-black text-cream">{completedCalls}</p>
                  <p className="text-xs uppercase text-cream/50">with outcomes</p>
                </div>
              </div>
            </div>
            <div className="rounded-[28px] border border-white/5 bg-white/5 p-6 shadow-[0_25px_80px_rgba(15,23,42,0.25)]">
              <p className="text-[11px] uppercase tracking-[0.32em] text-cream/60">Average score</p>
              <div className="mt-4 flex items-center gap-3">
                <BarChart3 className="h-6 w-6 text-sky-400" />
                <div>
                  <p className="text-3xl font-black text-cream">{avgScore}</p>
                  <p className="text-xs uppercase text-cream/50">intent score</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <section className="mb-10 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-[32px] border border-white/5 bg-white/5 p-8 shadow-[0_35px_90px_rgba(15,23,42,0.18)]"
          >
            <div className="mb-6 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.35em] text-cream/50">Outcome breakdown</p>
                <h2 className="mt-2 text-2xl font-black text-cream">By call result</h2>
              </div>
              <Search className="h-5 w-5 text-cream/70" />
            </div>

            <div className="space-y-3">
              {Object.entries(outcomeCounts).map(([label, count]) => (
                <div key={label} className="flex items-center justify-between rounded-3xl border border-white/10 bg-slate-950/70 px-4 py-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-cream/50">{label}</p>
                    <p className="mt-1 text-lg font-semibold text-cream">{count} call{count === 1 ? '' : 's'}</p>
                  </div>
                  <span className="rounded-full bg-neon/10 px-3 py-1 text-[11px] uppercase tracking-[0.35em] text-neon">{count}</span>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-[32px] border border-white/5 bg-white/5 p-8 shadow-[0_35px_90px_rgba(15,23,42,0.18)]"
          >
            <div className="mb-6">
              <p className="text-xs uppercase tracking-[0.35em] text-cream/50">Compatibility summary</p>
              <h2 className="mt-2 text-2xl font-black text-cream">Candidate fit</h2>
            </div>

            <div className="space-y-3">
              {Object.entries(compatibilityCounts).map(([label, count]) => (
                <div key={label} className="flex items-center justify-between rounded-3xl border border-white/10 bg-slate-950/70 px-4 py-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-cream/50">{label}</p>
                    <p className="mt-1 text-lg font-semibold text-cream">{count} candidate{count === 1 ? '' : 's'}</p>
                  </div>
                  <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.35em] text-emerald-300">{count}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </section>

        <section className="space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-cream/50">Call history</p>
              <h2 className="mt-2 text-3xl font-black text-cream">Candidate sessions</h2>
            </div>
            <p className="max-w-xl text-sm leading-6 text-cream/60">
              Click any session to expand full candidate and evaluation details, including resume notes, summary, and transcript count.
            </p>
          </div>

          {loading && (
            <div className="rounded-[28px] border border-white/10 bg-slate-950/80 p-12 text-center text-cream/70">
              Loading dashboard…
            </div>
          )}

          {error && (
            <div className="rounded-[28px] border border-red-500/30 bg-red-500/10 p-6 text-red-100">
              {error}
            </div>
          )}

          {!loading && !error && sessions.length === 0 && (
            <div className="rounded-[28px] border border-white/10 bg-slate-950/80 p-12 text-center text-cream/70">
              No candidate sessions have been recorded yet.
            </div>
          )}

          <div className="grid gap-6">
            {sessions.map((session) => {
              const isOpen = expanded[session.call_sid];
              const score = session.intent_score ?? '—';
              const confidence = session.eval_confidence != null ? `${Math.round(session.eval_confidence * 100)}%` : '—';
              const compatibility = (session.candidate_summary || {}).compatibility_level || 'Unknown';

              return (
                <motion.div
                  key={session.call_sid}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="overflow-hidden rounded-[32px] border border-white/5 bg-white/5 shadow-[0_35px_90px_rgba(15,23,42,0.16)]"
                >
                  <button
                    type="button"
                    onClick={() => toggleExpanded(session.call_sid)}
                    className="w-full px-6 py-6 text-left"
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                      <div className="space-y-3">
                        <div className="flex flex-wrap items-center gap-3 text-sm text-cream/60">
                          <span className="inline-flex items-center gap-2 rounded-full border border-neon/15 bg-neon/5 px-3 py-1 text-neon">
                            <Users className="h-4 w-4" /> {session.candidate_name}
                          </span>
                          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-cream/80">
                            <Clock className="h-4 w-4" /> {formatDate(session.created_at)}
                          </span>
                          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-cream/80">
                            <MapPin className="h-4 w-4" /> {session.call_channel || 'web'}
                          </span>
                        </div>

                        <div className="space-y-2">
                          <h3 className="text-xl font-semibold uppercase tracking-tight text-cream">{session.candidate_name || 'Candidate'}</h3>
                          <p className="max-w-3xl text-sm leading-6 text-cream/60">{compactText(session.job_description || session.summary || 'No job or summary text available', 220)}</p>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-end gap-3 text-right">
                        <div className="rounded-3xl border border-white/10 bg-slate-950/75 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Outcome</p>
                          <p className="mt-2 text-lg font-semibold text-cream">{session.call_outcome || 'Pending'}</p>
                        </div>
                        <div className="rounded-3xl border border-white/10 bg-slate-950/75 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Score</p>
                          <p className="mt-2 text-lg font-semibold text-cream">{score}</p>
                        </div>
                        <div className="rounded-3xl border border-white/10 bg-slate-950/75 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Fit</p>
                          <p className="mt-2 text-lg font-semibold text-cream">{compatibility}</p>
                        </div>
                      </div>
                    </div>
                  </button>

                  <motion.div
                    initial={false}
                    animate={{ height: isOpen ? 'auto' : 0, opacity: isOpen ? 1 : 0 }}
                    className="overflow-hidden px-6 transition-all duration-300"
                  >
                    {isOpen && (
                      <div className="space-y-6 border-t border-white/10 py-6">
                        <div className="grid gap-6 lg:grid-cols-3">
                          <div className="space-y-3 rounded-[28px] border border-white/10 bg-slate-950/80 p-5">
                            <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Contact</p>
                            <p className="text-sm text-cream">{session.candidate_phone || 'Not provided'}</p>
                            <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Channel</p>
                            <p className="text-sm text-cream">{session.call_channel || 'web'}</p>
                          </div>
                          <div className="space-y-3 rounded-[28px] border border-white/10 bg-slate-950/80 p-5">
                            <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Transcript</p>
                            <p className="text-sm text-cream">{session.transcript_length} messages</p>
                            <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Confidence</p>
                            <p className="text-sm text-cream">{confidence}</p>
                          </div>
                          <div className="space-y-3 rounded-[28px] border border-white/10 bg-slate-950/80 p-5">
                            <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Created</p>
                            <p className="text-sm text-cream">{formatDate(session.created_at)}</p>
                            <p className="text-[11px] uppercase tracking-[0.35em] text-cream/50">Ended</p>
                            <p className="text-sm text-cream">{formatDate(session.ended_at)}</p>
                          </div>
                        </div>

                        <div className="grid gap-6 lg:grid-cols-2">
                          <div className="rounded-[28px] border border-white/10 bg-slate-950/80 p-6">
                            <div className="flex items-center gap-2 text-sm uppercase tracking-[0.35em] text-cream/50 mb-4">
                              <FileText className="h-4 w-4" /> Resume & JD
                            </div>
                            <p className="text-sm leading-6 text-cream/70 whitespace-pre-line">{compactText(session.resume_text || session.job_description || 'No resume or JD provided', 800)}</p>
                          </div>
                          <div className="rounded-[28px] border border-white/10 bg-slate-950/80 p-6">
                            <div className="flex items-center gap-2 text-sm uppercase tracking-[0.35em] text-cream/50 mb-4">
                              <Heart className="h-4 w-4" /> Candidate Summary
                            </div>
                            <p className="text-sm leading-6 text-cream/70">{(session.candidate_summary || {}).compatibility_reason || 'No summary generated yet.'}</p>
                            {(session.candidate_summary?.summary_bullets || []).length > 0 && (
                              <ul className="mt-4 space-y-2 text-sm text-cream/70">
                                {(session.candidate_summary.summary_bullets || []).map((bullet, idx) => (
                                  <li key={idx} className="flex items-start gap-2">
                                    <span className="mt-1 inline-block h-1.5 w-1.5 rounded-full bg-neon" />
                                    <span>{bullet}</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        </div>

                        <div className="grid gap-6 lg:grid-cols-2">
                          <div className="rounded-[28px] border border-white/10 bg-slate-950/80 p-6">
                            <div className="flex items-center gap-2 text-sm uppercase tracking-[0.35em] text-cream/50 mb-4">
                              <Zap className="h-4 w-4" /> Evaluation Notes
                            </div>
                            <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-cream/70">{compactText(session.eval_reasoning || session.notes?.summary || session.notes?.detail || 'No evaluation notes captured yet.', 900)}</pre>
                          </div>
                          <div className="rounded-[28px] border border-white/10 bg-slate-950/80 p-6">
                            <div className="flex items-center gap-2 text-sm uppercase tracking-[0.35em] text-cream/50 mb-4">
                              <BarChart3 className="h-4 w-4" /> Dimension scores
                            </div>
                            <div className="space-y-3">
                              {session.dimension_scores && Object.entries(session.dimension_scores).length > 0 ? (
                                Object.entries(session.dimension_scores).map(([key, value]) => (
                                  <div key={key} className="rounded-3xl border border-white/10 bg-slate-950/70 px-4 py-3">
                                    <p className="text-xs uppercase tracking-[0.28em] text-cream/50">{key.replace(/_/g, ' ')}</p>
                                    <p className="mt-1 text-sm font-semibold text-cream">{value.score ?? '—'} / 10</p>
                                  </div>
                                ))
                              ) : (
                                <p className="text-sm text-cream/70">No structured dimension scores available.</p>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </motion.div>
                </motion.div>
              );
            })}
          </div>
        </section>
      </section>
    </main>
  );
}
