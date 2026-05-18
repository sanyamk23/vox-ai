import React, { useRef } from 'react';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  motion,
  useScroll,
  useTransform,
  useMotionValue,
  useSpring,
} from 'framer-motion';

// ─── Scroll progress bar ──────────────────────────────────────────────────────
function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });
  return (
    <motion.div
      className="fixed top-0 left-0 right-0 h-[3px] z-[200] origin-left"
      style={{ scaleX, background: 'linear-gradient(90deg, #6FFF00, #40ffaa)' }}
    />
  );
}

// ─── Ambient orb ─────────────────────────────────────────────────────────────
function Orb({ size = 500, color = '#6FFF00', x = 0, y = 0, delay = 0, opacity = 0.08 }) {
  return (
    <motion.div
      className="absolute rounded-full pointer-events-none"
      style={{
        width: size, height: size,
        left: `calc(50% + ${x}px)`, top: `calc(50% + ${y}px)`,
        transform: 'translate(-50%, -50%)',
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        filter: 'blur(80px)', opacity,
      }}
      animate={{ x: [0, 50, -30, 0], y: [0, -40, 50, 0], scale: [1, 1.15, 0.88, 1] }}
      transition={{ duration: 12, delay, repeat: Infinity, ease: 'easeInOut' }}
    />
  );
}

// ─── Scroll-reveal wrapper ────────────────────────────────────────────────────
function Reveal({ children, delay = 0, y = 50, className = '' }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.9, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

// ─── Marquee ticker ───────────────────────────────────────────────────────────
const TICKER_ITEMS = [
  'GEMINI LIVE', 'REAL-TIME VOICE', 'AI SCREENING', 'ZERO BIAS',
  'INSTANT INSIGHTS', 'TWILIO MEDIA STREAMS', 'MULTILINGUAL', 'AUTONOMOUS RECRUITER',
  'GEMINI LIVE', 'REAL-TIME VOICE', 'AI SCREENING', 'ZERO BIAS',
  'INSTANT INSIGHTS', 'TWILIO MEDIA STREAMS', 'MULTILINGUAL', 'AUTONOMOUS RECRUITER',
];
function Ticker() {
  return (
    <div className="w-full overflow-hidden border-y border-white/5 py-4 bg-background">
      <motion.div
        className="flex gap-10 whitespace-nowrap will-change-transform"
        animate={{ x: ['0%', '-50%'] }}
        transition={{ duration: 24, repeat: Infinity, ease: 'linear' }}
      >
        {TICKER_ITEMS.map((item, i) => (
          <span key={i} className="font-mono text-[11px] uppercase tracking-[0.28em] text-cream/25 flex items-center gap-10 shrink-0">
            {item}
            <span className="text-neon text-[14px]">·</span>
          </span>
        ))}
      </motion.div>
    </div>
  );
}

// ─── 3-D tilt team card ───────────────────────────────────────────────────────
function TeamCard({ videoUrl, index, name, role, delay = 0 }) {
  const cardRef = useRef(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotateX = useSpring(useTransform(y, [-0.5, 0.5], [12, -12]), { stiffness: 200, damping: 25 });
  const rotateY = useSpring(useTransform(x, [-0.5, 0.5], [-12, 12]), { stiffness: 200, damping: 25 });
  const glowOpacity = useMotionValue(0);

  const handleMouse = (e) => {
    if (!cardRef.current) return;
    const r = cardRef.current.getBoundingClientRect();
    x.set((e.clientX - r.left) / r.width - 0.5);
    y.set((e.clientY - r.top) / r.height - 0.5);
    glowOpacity.set(1);
  };
  const handleLeave = () => {
    x.set(0); y.set(0); glowOpacity.set(0);
  };

  return (
    <motion.div
      ref={cardRef}
      style={{ rotateX, rotateY, transformPerspective: 1200 }}
      onMouseMove={handleMouse}
      onMouseLeave={handleLeave}
      initial={{ opacity: 0, y: 70 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.85, delay, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ scale: 1.03, zIndex: 10 }}
      className="liquid-glass rounded-[40px] p-5 border border-white/5 shadow-2xl group cursor-pointer relative"
    >
      {/* outer glow ring */}
      <motion.div
        className="absolute inset-0 rounded-[40px] pointer-events-none"
        style={{ opacity: glowOpacity, boxShadow: '0 0 40px 4px rgba(111,255,0,0.18), inset 0 0 30px rgba(111,255,0,0.06)' }}
        transition={{ duration: 0.2 }}
      />

      <div className="relative w-full aspect-square rounded-[32px] overflow-hidden bg-black/50">
        {/* inner glow on hover */}
        <div className="absolute inset-0 rounded-[32px] opacity-0 group-hover:opacity-100 transition-opacity duration-500 z-10 pointer-events-none"
          style={{ boxShadow: 'inset 0 0 50px rgba(111,255,0,0.12)' }} />

        <video
          className="absolute inset-0 w-full h-full object-cover group-hover:scale-108 transition-transform duration-700"
          autoPlay loop muted playsInline src={videoUrl}
        />

        {/* index badge */}
        <div className="absolute top-5 left-5 font-mono text-[11px] text-cream/30 uppercase tracking-[0.28em] z-20">
          {index}
        </div>

        {/* name + role overlay */}
        <div className="absolute bottom-5 left-5 right-5 liquid-glass rounded-[24px] px-6 py-5 border border-white/10 backdrop-blur-md z-20">
          <motion.div
            className="h-[2px] bg-neon mb-3 origin-left"
            initial={{ width: 28 }}
            whileHover={{ width: 52 }}
            transition={{ duration: 0.3 }}
          />
          <p className="font-grotesk uppercase text-[15px] sm:text-[17px] leading-tight tracking-tight">{name}</p>
          <p className="font-mono text-[9px] sm:text-[10px] text-cream/50 uppercase tracking-[0.18em] mt-1.5 leading-relaxed">{role}</p>
        </div>
      </div>
    </motion.div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  const { scrollYProgress } = useScroll();
  const heroY = useTransform(scrollYProgress, [0, 0.4], [0, -80]);

  return (
    <div className="relative min-h-screen bg-background text-cream overflow-x-hidden font-sans selection:bg-neon selection:text-background">
      <ScrollProgress />

      {/* Texture overlay */}
      <div className="fixed inset-0 z-50 pointer-events-none mix-blend-lighten opacity-60"
        style={{ backgroundImage: 'url(/texture.png)', backgroundSize: 'cover', backgroundPosition: 'center' }} />

      {/* ── HERO ─────────────────────────────────────────────────── */}
      <section className="relative w-full h-screen rounded-b-[32px] overflow-hidden flex flex-col items-center">
        <video className="absolute inset-0 w-full h-full object-cover z-0" autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_045634_e1c98c76-1265-4f5c-882a-4276f2080894.mp4" />
        <div className="absolute inset-0 bg-background/40 z-[1]" />

        {/* ambient orbs */}
        <div className="absolute inset-0 z-[2] overflow-hidden pointer-events-none">
          <Orb size={700} color="#6FFF00" x={-350} y={80}  delay={0}  opacity={0.06} />
          <Orb size={450} color="#3b5bff" x={350}  y={-80} delay={3}  opacity={0.07} />
          <Orb size={300} color="#6FFF00" x={200}  y={200} delay={6}  opacity={0.04} />
        </div>

        <motion.div style={{ y: heroY }} className="relative z-10 w-full max-w-[1831px] px-6 sm:px-12 md:px-16 flex flex-col h-full">
          {/* Nav */}
          <header className="flex items-center justify-between pt-8">
            <motion.div initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.7 }}>
              <Link to="/" className="font-grotesk text-xl sm:text-2xl uppercase tracking-wider hover:text-neon transition-colors">
                Clarix.Ai
              </Link>
            </motion.div>

            <motion.nav initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.15 }}
              className="hidden lg:flex liquid-glass rounded-[28px] px-12 py-5 items-center gap-10">
              {[{ name: 'Home', path: '/' }, { name: 'About', path: '/about' }, { name: 'Features', path: '/features' }, { name: 'App', path: '/app' }].map((link, i) => (
                <motion.div key={link.name} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 + i * 0.07 }}>
                  <Link to={link.path} className="font-grotesk text-[13px] uppercase hover:text-neon transition-colors tracking-widest">
                    {link.name}
                  </Link>
                </motion.div>
              ))}
            </motion.nav>

            <motion.div initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.7 }}
              className="lg:hidden">
              <Link to="/app" className="font-grotesk text-xs uppercase text-neon border border-neon px-4 py-2 rounded-full">
                Launch
              </Link>
            </motion.div>
          </header>

          {/* Hero text */}
          <div className="flex-1 flex flex-col justify-center">
            <div className="relative w-full max-w-[900px] lg:ml-24 xl:ml-32">
              <h1 className="font-grotesk uppercase text-[42px] sm:text-[64px] md:text-[80px] lg:text-[100px] leading-[0.95] tracking-tighter overflow-hidden">
                {['Beyond resumes', 'and ( their )', 'traditional limits'].map((line, i) => (
                  <span key={i} className="block overflow-hidden">
                    <motion.span className="block"
                      initial={{ y: '110%', opacity: 0 }}
                      animate={{ y: 0, opacity: 1 }}
                      transition={{ duration: 1, delay: 0.5 + i * 0.18, ease: [0.16, 1, 0.3, 1] }}
                    >
                      {line}
                    </motion.span>
                  </span>
                ))}
              </h1>

              <motion.span
                className="font-condiment text-neon text-[28px] sm:text-[42px] md:text-[54px] absolute right-4 md:right-12 -bottom-10 md:bottom-2 translate-y-full md:translate-y-0 mix-blend-exclusion opacity-95 normal-case"
                initial={{ opacity: 0, rotate: -10, scale: 0.7 }}
                animate={{ opacity: 0.95, rotate: -2, scale: 1 }}
                transition={{ duration: 0.9, delay: 1.1, ease: [0.16, 1, 0.3, 1] }}
              >
                Ai recruiter
              </motion.span>

              <motion.div className="mt-20 md:mt-12 flex items-center gap-8"
                initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, delay: 1.2, ease: [0.16, 1, 0.3, 1] }}
              >
                <Link to="/app" className="group flex items-center gap-4 bg-neon px-8 py-4 rounded-full hover:scale-105 transition-all duration-300 shadow-[0_0_40px_rgba(111,255,0,0.35)] hover:shadow-[0_0_60px_rgba(111,255,0,0.55)]">
                  <span className="font-grotesk text-background text-lg uppercase tracking-wider">Start Interview</span>
                  <div className="w-8 h-8 rounded-full bg-background flex items-center justify-center group-hover:translate-x-1 transition-transform">
                    <ArrowRight size={18} className="text-neon" />
                  </div>
                </Link>
                <div className="hidden sm:block font-mono text-[11px] uppercase tracking-[0.2em] text-cream/50 max-w-[200px] leading-relaxed">
                  Fully autonomous voice screening in real-time
                </div>
              </motion.div>
            </div>
          </div>

          {/* Scroll indicator */}
          <motion.div
            className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 z-20"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.8, duration: 0.8 }}
          >
            <span className="font-mono text-[9px] uppercase tracking-[0.3em] text-cream/25">Scroll</span>
            <motion.div className="w-[1px] h-10 bg-gradient-to-b from-neon/80 to-transparent"
              animate={{ scaleY: [1, 0.2, 1], opacity: [0.8, 0.2, 0.8] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }} />
          </motion.div>
        </motion.div>
      </section>

      {/* ── TICKER ───────────────────────────────────────────────── */}
      <Ticker />

      {/* ── ABOUT ────────────────────────────────────────────────── */}
      <section className="relative w-full min-h-screen overflow-hidden flex flex-col justify-center py-24">
        <video className="absolute inset-0 w-full h-full object-cover z-0" autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_151551_992053d1-3d3e-4b8c-abac-45f22158f411.mp4" />
        <div className="absolute inset-0 bg-background/55 z-[1]" />

        <div className="relative z-10 w-full max-w-[1831px] mx-auto px-6 sm:px-12 md:px-16 flex flex-col justify-between h-full min-h-[70vh]">
          <div className="flex flex-col lg:flex-row justify-between items-start gap-16 lg:gap-24">
            <Reveal>
              <div className="relative">
                <h2 className="font-grotesk uppercase text-[36px] sm:text-[54px] lg:text-[72px] leading-[0.9]">
                  Hello!<br />I'm clarix
                </h2>
                <span className="font-condiment text-neon text-[42px] sm:text-[60px] lg:text-[84px] absolute right-[-20px] bottom-[-20px] translate-y-1/2 rotate-[-5deg] mix-blend-exclusion normal-case">
                  Clarix
                </span>
              </div>
            </Reveal>

            <Reveal delay={0.15}>
              <div className="font-mono text-[14px] md:text-[18px] uppercase max-w-[320px] leading-relaxed tracking-wider text-cream/90">
                A digital agent fixed beyond time and bias. An exploration of intelligence, voice, and instant screening.
              </div>
            </Reveal>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12 mt-32">
            {[
              'Built on the latest foundation models to ensure accuracy and empathy in every conversation.',
              'Scaling your talent pipeline with infinite capacity and zero fatigue.',
            ].map((text, i) => (
              <Reveal key={i} delay={i * 0.15}>
                <div className="space-y-4">
                  <div className="w-12 h-[2px] bg-neon" />
                  <p className="font-mono text-xs uppercase tracking-widest leading-relaxed text-cream/40">{text}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── TEAM ─────────────────────────────────────────────────── */}
      <section className="relative w-full bg-background py-32 overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <Orb size={800} color="#6FFF00" x={-450} y={50}   delay={0} opacity={0.035} />
          <Orb size={600} color="#3b5bff" x={450}  y={250}  delay={5} opacity={0.045} />
          <Orb size={350} color="#6FFF00" x={100}  y={-150} delay={2} opacity={0.03}  />
        </div>

        <div className="relative w-full max-w-[1831px] mx-auto px-6 sm:px-12 md:px-16">
          <div className="flex flex-col lg:flex-row justify-between items-start lg:items-end gap-12 mb-24">
            <Reveal>
              <div>
                <motion.p className="font-mono text-[11px] uppercase tracking-[0.35em] text-neon mb-6"
                  initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }} transition={{ duration: 0.6 }}>
                  The Builders
                </motion.p>
                <h2 className="font-grotesk uppercase text-[36px] sm:text-[54px] lg:text-[72px] leading-[0.9]">
                  Minds Behind <br />
                  <div className="ml-8 sm:ml-16 lg:ml-32 flex items-baseline gap-4">
                    <span className="font-condiment text-neon normal-case text-[48px] sm:text-[72px] lg:text-[96px]">Clarix</span> AI
                  </div>
                </h2>
              </div>
            </Reveal>

            <Reveal delay={0.2}>
              <Link to="/app" className="group flex flex-col items-center">
                <div className="flex items-center gap-4 hover:opacity-80 transition-opacity">
                  <span className="font-grotesk uppercase text-[32px] sm:text-[48px] lg:text-[64px] leading-none tracking-tighter">LAUNCH</span>
                  <div className="flex flex-col items-start leading-[0.85]">
                    <span className="font-grotesk uppercase text-[20px] sm:text-[32px] lg:text-[40px] tracking-tighter">THE</span>
                    <span className="font-grotesk uppercase text-[20px] sm:text-[32px] lg:text-[40px] tracking-tighter text-neon">APP</span>
                  </div>
                </div>
                <div className="w-full bg-neon h-[4px] md:h-[8px] mt-4 group-hover:scale-x-110 transition-transform origin-left" />
              </Link>
            </Reveal>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            <TeamCard videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_053923_22c0a6a5-313c-474c-85ff-3b50d25e944a.mp4"
              index="01" name="Rishabh Tiwari" role="Chief Visionary · Origin of the Spark" delay={0} />
            <TeamCard videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_054411_511c1b7a-fb2f-42ef-bf6c-32c0b1a06e79.mp4"
              index="02" name="Prerna Shekhawat" role="Neural Conductor · Cognitive Systems" delay={0.1} />
            <TeamCard videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_055427_ac7035b5-9f3b-4289-86fc-941b2432317d.mp4"
              index="03" name="Sanyam Kumar" role="Deep Intelligence Architect · AI Research" delay={0.2} />
            <TeamCard videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_055729_72d66327-b59e-4ae9-bb70-de6ccb5ecdb0.mp4"
              index="04" name="Ajay Singh Rathore" role="Systems Convergence Commander · Full-Stack" delay={0.3} />
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────── */}
      <section className="relative w-full overflow-hidden">
        <video className="w-full h-auto block min-h-[400px] object-cover md:object-contain" autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_055729_72d66327-b59e-4ae9-bb70-de6ccb5ecdb0.mp4" />

        <div className="absolute inset-0 w-full h-full flex flex-col justify-center bg-background/20">
          <div className="relative w-full h-full max-w-[1831px] mx-auto px-8">
            <div className="absolute top-1/2 -translate-y-1/2 right-0 lg:pr-[15%] xl:pr-[20%] px-6 text-right">
              <Reveal y={30}>
                <div className="relative inline-block">
                  <span className="font-condiment text-neon text-[24px] sm:text-[48px] lg:text-[72px] absolute -top-12 -left-8 md:-top-20 md:-left-24 mix-blend-exclusion normal-case rotate-[-8deg]">
                    Hire smarter
                  </span>
                  <h2 className="font-grotesk uppercase text-[20px] sm:text-[40px] md:text-[54px] lg:text-[64px] leading-[1] tracking-tight">
                    {['TRY NOW.', 'REVEAL TRUE TALENT.', 'DEFINE YOUR TEAM.', 'HIRE THE BEST.'].map((line, i) => (
                      <motion.div key={i}
                        className={`${i === 0 ? 'mb-6 lg:mb-10 text-neon' : i === 2 ? 'mb-2 text-cream/80 text-[0.8em]' : 'mb-2'}`}
                        initial={{ opacity: 0, x: 40 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.7, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                      >
                        {line}
                      </motion.div>
                    ))}
                  </h2>
                </div>
              </Reveal>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
