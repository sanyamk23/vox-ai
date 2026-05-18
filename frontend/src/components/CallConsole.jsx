import React, { useMemo, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  CheckCircle2, 
  Circle, 
  Mic2, 
  Volume2, 
  Plus, 
  Pause, 
  PhoneOff, 
  Search, 
  Bell, 
  HelpCircle,
  LayoutDashboard,
  Users,
  Briefcase,
  Settings,
  MessageSquare,
  Phone,
  TrendingUp,
  Sparkles,
  Zap
} from 'lucide-react';

export default function CallConsole({
  name,
  phone,
  elapsed,
  messages,
  endRef,
  onEnd,
  bars,
  fmt,
  status,
  voiceName,
}) {
  const displayVoiceName = voiceName || 'AI';
  // Persistence for the furthest phase reached
  const [furthestPhase, setFurthestPhase] = useState(0);

  // Phase definitions matching the Sarah/Priya recruiter framework
  const phases = useMemo(() => [
    { id: 'greeting', label: 'Greeting & Rapport', keywords: ['hello', 'hi ', 'how are you', 'hope', 'catching'], minTurns: 0 },
    { id: 'intro', label: 'Role Introduction', keywords: ['role', 'position', 'company', 'startup', 'tease', 'describe'], minTurns: 1 }, // Reduced minTurns
    { id: 'tech', label: 'Technical Depth', keywords: ['experience', 'project', 'skill', 'stack', 'build', 'using', 'proud of', 'architected', 'developed', 'implement'], minTurns: 4 }, // Reduced minTurns
    { id: 'motivation', label: 'Motivation & Fit', keywords: ['move', 'consider', 'why', 'culture', 'home', 'haves', 'passion', 'growth', 'environment'], minTurns: 10 }, // Reduced minTurns
    { id: 'logistics', label: 'Logistics & CTC', keywords: ['salary', 'ctc', 'lpa', 'notice', 'current', 'expected', 'join', 'benefits'], minTurns: 16 }, // Reduced minTurns
    { id: 'closing', label: 'Closing Wrap-up', keywords: ['questions', 'next steps', 'update', 'tomorrow', 'bye', '[end_call]', 'talk soon'], minTurns: 20 }, // Reduced minTurns
  ], []);

  // Smarter phase detection logic
  useEffect(() => {
    const fullTranscript = messages.map(m => m.text.toLowerCase()).join(' ');
    const aiMessages = messages.filter(m => m.role === 'assistant' || m.role === 'ai');
    const turnCount = aiMessages.length;

    let currentDetectedIndex = furthestPhase; // Start detection from the furthest phase already reached
    
    for (let i = furthestPhase; i < phases.length; i++) { // Loop from current furthest phase onwards
      const p = phases[i];
      // Criteria: either enough turns have passed OR strong keywords are found in the FULL transcript up to this point
      // Using fullTranscript for a more robust check if the topic was covered at any point
      const hasKeywordsInFullTranscript = p.keywords.some(k => fullTranscript.includes(k));
      const reachedTurnLimit = turnCount >= p.minTurns;

      if (hasKeywordsInFullTranscript || reachedTurnLimit) {
        currentDetectedIndex = i;
      } else {
        // If we can't advance to this phase, we definitely can't advance to later ones
        break;
      }
    }

    // Only update if we've actually advanced to a new phase
    if (currentDetectedIndex > furthestPhase) {
      setFurthestPhase(currentDetectedIndex);
    }

  }, [messages, elapsed, furthestPhase, phases]); // Added elapsed to dependencies to re-evaluate on time progression

  const steps = useMemo(() => {
    return phases.map((p, idx) => {
      let s = 'pending';
      if (idx < furthestPhase) s = 'completed';
      else if (idx === furthestPhase) s = 'active';
      return { ...p, status: s };
    });
  }, [furthestPhase, phases]);

  return (
    <div className="relative min-h-screen bg-background text-cream overflow-hidden font-sans selection:bg-neon selection:text-background">
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

      <div className="relative z-10 flex h-screen overflow-hidden">
        {/* Sidebar */}
        <aside className="w-64 liquid-glass flex flex-col p-6 m-4 mr-0 rounded-[32px] border border-white/10 shadow-2xl">
          <div className="mb-10 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-neon flex items-center justify-center shadow-[0_0_15px_rgba(111,255,0,0.4)]">
               <Zap size={16} className="text-background" fill="currentColor" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-cream font-grotesk leading-none">Clarix AI</h1>
              <p className="text-[9px] font-bold text-neon uppercase tracking-widest mt-1 opacity-80">Autonomous</p>
            </div>
          </div>

          <nav className="flex-1 space-y-1">
            <SidebarItem icon={LayoutDashboard} label="Dashboard" />
            <SidebarItem icon={Users} label="Candidates" active />
            <SidebarItem icon={Briefcase} label="Jobs" />
            <SidebarItem icon={Settings} label="Settings" />
          </nav>

          <button className="mt-auto flex items-center justify-center gap-2 bg-neon text-background py-3.5 rounded-2xl font-black text-xs hover:scale-105 transition-all shadow-[0_0_25px_rgba(111,255,0,0.25)] uppercase tracking-widest">
            <Plus size={16} /> New Campaign
          </button>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Top Header */}
          <header className="h-20 flex items-center justify-between px-10">
            <div className="relative w-[400px]">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-cream/40" size={16} />
              <input 
                type="text" 
                placeholder="Search candidates..." 
                className="w-full bg-white/5 border border-white/10 rounded-full py-2.5 pl-12 pr-6 text-sm text-cream placeholder-cream/20 focus:ring-1 focus:ring-neon outline-none backdrop-blur-md transition-all font-mono uppercase tracking-tighter"
              />
            </div>
            <div className="flex items-center gap-8 text-cream/60">
              <div className="flex gap-4">
                <Bell size={20} className="cursor-pointer hover:text-neon transition-colors" />
                <HelpCircle size={20} className="cursor-pointer hover:text-neon transition-colors" />
              </div>
              <div className="w-px h-6 bg-white/10" />
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold font-mono uppercase tracking-widest text-cream/40">Admin</span>
                <div className="w-10 h-10 rounded-2xl bg-white/10 overflow-hidden border border-white/20 shadow-lg backdrop-blur-md hover:border-neon/50 transition-colors cursor-pointer p-0.5">
                   <img className="rounded-xl w-full h-full object-cover" src={`https://ui-avatars.com/api/?name=${encodeURIComponent(name || 'Clarix')}&background=6FFF00&color=010828&bold=true`} alt="Profile" />
                </div>
              </div>
            </div>
          </header>

          {/* Console Workspace */}
          <main className="flex-1 p-4 lg:p-6 overflow-hidden flex flex-col gap-6">
            
            {/* Candidate Profile Header */}
            <motion.div 
              initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
              className="liquid-glass border border-white/10 rounded-[32px] p-6 flex items-center justify-between shadow-2xl"
            >
              <div className="flex items-center gap-6">
                <div className="w-16 h-16 rounded-2xl bg-neon/10 text-neon flex items-center justify-center text-2xl font-bold uppercase border border-neon/30 shadow-[0_0_20px_rgba(111,255,0,0.1)] font-grotesk relative overflow-hidden">
                  <div className="absolute inset-0 bg-neon/5 animate-pulse" />
                  <span className="relative z-10">{name?.split(' ').map(n => n[0]).join('').slice(0, 2) || 'AS'}</span>
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-cream tracking-tighter font-grotesk uppercase mb-0.5">{name || 'Ankit Sharma'}</h2>
                  <div className="flex items-center gap-3 text-cream/40 text-xs font-mono uppercase tracking-[0.2em]">
                    <Phone size={14} className="text-neon opacity-70" />
                    <span className="mt-0.5">{phone || 'Signal Encrypted'}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-10">
                <div className="flex flex-col items-end">
                   <div className="flex items-center gap-2 bg-neon text-background px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-[0.25em] shadow-[0_0_15px_rgba(111,255,0,0.3)]">
                    <div className="w-1.5 h-1.5 rounded-full bg-background animate-pulse" />
                    Live Signal
                  </div>
                </div>
                <div className="w-px h-10 bg-white/10" />
                <div className="text-right">
                  <p className="text-[10px] font-bold text-cream/30 uppercase tracking-[0.3em] mb-1">Elapsed</p>
                  <p className="text-2xl font-mono font-black text-neon tabular-nums tracking-tighter">{fmt(elapsed)}</p>
                </div>
              </div>
            </motion.div>

            {/* Three-Column View */}
            <div className="flex-1 flex gap-6 overflow-hidden">
              
              {/* Column 1: Progress */}
              <div className="w-72 flex flex-col gap-4 overflow-hidden">
                <div className="liquid-glass border border-white/10 rounded-[32px] flex flex-col flex-1 overflow-hidden">
                  <div className="p-5 border-b border-white/10 bg-white/5 backdrop-blur-md flex items-center justify-between">
                    <h3 className="text-[10px] font-black text-neon uppercase tracking-[0.3em]">Interview Protocol</h3>
                    <Sparkles size={12} className="text-neon opacity-50" />
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 space-y-2 scrollbar-hide">
                    {steps.map((step, idx) => (
                      <motion.div 
                        key={idx} layout
                        className={`flex items-center gap-4 p-3.5 rounded-2xl transition-all border ${step.status === 'active' ? 'bg-neon/10 border-neon/30 shadow-[0_0_20px_rgba(111,255,0,0.05)]' : 'border-transparent'}`}
                      >
                        {step.status === 'completed' ? (
                          <div className="w-6 h-6 rounded-full bg-neon flex items-center justify-center shadow-lg shadow-neon/20">
                             <CheckCircle2 className="text-background" size={14} />
                          </div>
                        ) : step.status === 'active' ? (
                          <div className="w-6 h-6 rounded-full border-2 border-neon flex items-center justify-center bg-background shadow-[0_0_10px_rgba(111,255,0,0.2)]">
                            <div className="w-2.5 h-2.5 rounded-full bg-neon animate-pulse" />
                          </div>
                        ) : (
                          <div className="w-6 h-6 rounded-full border-2 border-white/10 flex items-center justify-center bg-white/5" />
                        )}
                        <span className={`text-[11px] font-bold uppercase tracking-widest ${step.status === 'pending' ? 'text-cream/20' : step.status === 'active' ? 'text-neon' : 'text-cream'}`}>
                          {step.label}
                        </span>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Column 2: Waveform Area */}
              <div className="flex-1 liquid-glass rounded-[40px] flex flex-col items-center justify-center relative overflow-hidden border border-white/10 shadow-2xl">
                 <div className="absolute inset-0 opacity-20 pointer-events-none">
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-neon/20 via-transparent to-transparent animate-pulse" />
                 </div>
                 
                 <div className="text-center z-10 space-y-12 w-full px-12">
                    <div className="space-y-4">
                      <p className="text-[11px] font-black text-neon uppercase tracking-[0.6em] opacity-80 animate-pulse">Neural Link Active</p>
                      <h4 className="text-6xl font-black text-cream tracking-tighter font-grotesk uppercase">{displayVoiceName} AI</h4>
                    </div>

                    {/* Waveform Visualizer */}
                    <div className="flex items-center justify-center gap-2.5 h-40">
                      {bars.map((lvl, i) => (
                        <motion.div 
                          key={i} 
                          animate={{ height: Math.max(8, lvl * 160) }}
                          transition={{ type: "spring", stiffness: 500, damping: 30 }}
                          className="w-2.5 rounded-full bg-neon shadow-[0_0_25px_rgba(111,255,0,0.8)]"
                        />
                      ))}
                    </div>

                    <div className="flex items-center justify-center gap-10 pt-4">
                      <WaveformControl icon={Mic2} label="AI MIC" active />
                      <WaveformControl icon={Volume2} label="SPEAKER" active />
                    </div>
                 </div>
              </div>

              {/* Column 3: Live Transcript */}
              <div className="w-80 flex flex-col gap-4 overflow-hidden">
                <div className="liquid-glass border border-white/10 rounded-[32px] flex flex-col flex-1 overflow-hidden">
                  <div className="p-5 border-b border-white/10 flex items-center justify-between bg-white/5 backdrop-blur-md">
                    <h3 className="text-[10px] font-black text-cream/40 uppercase tracking-[0.3em]">Live Feed</h3>
                    <div className="flex items-center gap-2 bg-neon/10 px-2 py-1 rounded-full border border-neon/20">
                      <div className="w-1.5 h-1.5 rounded-full bg-neon animate-pulse" />
                      <span className="text-[9px] font-black text-neon uppercase">Syncing</span>
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-5 space-y-6 scrollbar-hide bg-black/20">
                    <AnimatePresence>
                      {messages.length === 0 ? (
                        <motion.div 
                          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          className="h-full flex flex-col items-center justify-center opacity-20 text-cream space-y-4"
                        >
                           <MessageSquare size={32} strokeWidth={1} />
                           <p className="font-mono uppercase tracking-[0.3em] text-[9px]">Awaiting Uplink...</p>
                        </motion.div>
                      ) : (
                        messages.map((m, i) => (
                          <motion.div 
                            key={i} 
                            initial={{ opacity: 0, x: m.role === 'user' ? 10 : -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}
                          >
                            <div className="flex items-center gap-2 mb-2">
                              <span className="text-[9px] font-black text-neon uppercase tracking-tighter">{m.role === 'user' ? (name || 'CANDIDATE') : `${displayVoiceName} AI`}</span>
                              <span className="text-[9px] text-cream/30 font-mono">{m.time || nowTime()}</span>
                            </div>
                            <div className={`text-[13px] font-mono font-medium leading-relaxed p-4 rounded-3xl border shadow-2xl ${
                              m.role === 'user' 
                                ? 'bg-cream text-background border-cream rounded-tr-sm' 
                                : 'liquid-glass text-cream border-white/10 rounded-tl-sm'
                            }`}>
                              {m.text}
                            </div>
                          </motion.div>
                        ))
                      )}
                    </AnimatePresence>
                    <div ref={endRef} />
                  </div>
                </div>
              </div>

            </div>
          </main>

          {/* Bottom Actions Footer */}
          <footer className="h-24 px-10 flex items-center justify-between relative z-20">
             <div className="flex items-center gap-6">
                <button className="flex items-center gap-3 bg-white/5 border border-white/10 px-8 py-3.5 rounded-2xl text-[10px] font-black text-cream/70 uppercase tracking-[0.2em] hover:bg-white/10 hover:text-cream transition-all backdrop-blur-md shadow-xl group">
                  <Plus size={16} className="text-neon group-hover:scale-125 transition-transform" /> Internal Note
                </button>
                <button className="flex items-center gap-3 bg-white/5 border border-white/10 px-8 py-3.5 rounded-2xl text-[10px] font-black text-cream/70 uppercase tracking-[0.2em] hover:bg-white/10 hover:text-cream transition-all backdrop-blur-md shadow-xl group">
                  <Pause size={16} className="text-cream/40 group-hover:text-neon transition-colors" /> Pause
                </button>
             </div>
             
             <div className="flex items-center gap-12">
                <div className="flex items-center gap-5">
                  <div className="w-14 h-14 rounded-3xl bg-neon/10 flex items-center justify-center text-neon border border-neon/20 shadow-[0_0_30px_rgba(111,255,0,0.15)] relative overflow-hidden group">
                     <div className="absolute inset-0 bg-neon/5 group-hover:scale-150 transition-transform duration-1000" />
                     <TrendingUp size={24} className="relative z-10" />
                  </div>
                  <div>
                     <p className="text-[10px] font-bold text-cream/30 uppercase tracking-[0.4em] leading-none mb-2">Neural Accuracy</p>
                     <p className="text-2xl font-black text-neon tracking-tighter font-grotesk">94% <span className="text-[10px] font-mono opacity-50 tracking-normal ml-1">MATCH</span></p>
                  </div>
                </div>
                <div className="w-px h-14 bg-white/10" />
                <button 
                  onClick={onEnd}
                  className="bg-red-600 text-white px-14 py-4 rounded-[24px] flex items-center gap-4 font-grotesk text-xl uppercase tracking-[0.15em] hover:bg-red-500 transition-all shadow-[0_0_40px_rgba(239,68,68,0.4)] hover:scale-105 active:scale-95 border-b-[6px] border-red-800"
                >
                  <PhoneOff size={22} /> Terminate
                </button>
             </div>
          </footer>

        </div>
      </div>
    </div>
  );
}

function SidebarItem({ icon: Icon, label, active }) {
  return (
    <div className={`flex items-center gap-5 px-6 py-4 rounded-[20px] cursor-pointer transition-all group ${active ? 'bg-neon text-background shadow-[0_0_30px_rgba(111,255,0,0.35)]' : 'text-cream/30 hover:bg-white/5 hover:text-cream'}`}>
      <Icon size={20} strokeWidth={active ? 3.5 : 2.5} className={active ? 'text-background' : 'group-hover:text-neon transition-colors'} />
      <span className={`text-[13px] font-black uppercase tracking-[0.15em] ${active ? 'opacity-100' : 'opacity-80'}`}>{label}</span>
    </div>
  );
}

function WaveformControl({ icon: Icon, label, active }) {
  return (
    <div className="flex flex-col items-center gap-3 group cursor-pointer">
      <button className={`w-16 h-16 rounded-[24px] border transition-all flex items-center justify-center backdrop-blur-2xl shadow-2xl ${active ? 'bg-white/10 border-white/20 text-neon shadow-neon/10' : 'bg-white/5 border-white/5 text-cream/20'}`}>
        <Icon size={28} />
      </button>
      <span className="text-[10px] font-black text-cream/30 uppercase tracking-[0.3em] group-hover:text-neon transition-colors">{label}</span>
    </div>
  );
}

const nowTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
