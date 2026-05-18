import React from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Zap, Bot, Database, PhoneCall, Cpu, Globe } from 'lucide-react';

export default function FeaturesPage() {
  return (
    <div className="relative min-h-screen bg-background text-cream overflow-x-hidden font-sans selection:bg-neon selection:text-background">
      {/* Texture Overlay */}
      <div 
        className="fixed inset-0 z-50 pointer-events-none mix-blend-lighten opacity-60"
        style={{ backgroundImage: 'url(/texture.png)', backgroundSize: 'cover', backgroundPosition: 'center' }}
      />
      
      {/* Background Video */}
      <div className="fixed inset-0 z-0 opacity-30">
        <video 
          className="absolute inset-0 w-full h-full object-cover scale-110"
          autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_055729_72d66327-b59e-4ae9-bb70-de6ccb5ecdb0.mp4"
        />
        <div className="absolute inset-0 bg-background/70" />
      </div>

      {/* Header */}
      <header className="relative z-40 px-6 sm:px-12 py-6 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center bg-neon">
            <Zap size={12} className="text-background" fill="currentColor" />
          </div>
          <div className="font-grotesk text-[20px] uppercase tracking-wide">Clarix.Ai</div>
        </Link>

        <nav className="hidden lg:flex liquid-glass rounded-[28px] px-12 py-4 items-center gap-10">
          {[
            { name: 'Home', path: '/' },
            { name: 'About', path: '/about' },
            { name: 'Features', path: '/features' },
            { name: 'App', path: '/app' },
          ].map(link => (
            <Link key={link.name} to={link.path} className={`font-grotesk text-[13px] uppercase tracking-widest transition-colors ${link.path === '/features' ? 'text-neon' : 'hover:text-neon'}`}>
              {link.name}
            </Link>
          ))}
        </nav>

        <Link to="/app" className="font-grotesk text-xs uppercase text-neon border border-neon px-5 py-2 rounded-full hover:bg-neon hover:text-background transition-all">
          Launch App
        </Link>
      </header>

      <main className="relative z-10 w-full max-w-[1440px] mx-auto px-6 sm:px-12 lg:px-16 pt-32 pb-24">
        <motion.div 
          initial={{ opacity: 0, y: 20 }} 
          animate={{ opacity: 1, y: 0 }} 
          className="mb-32 flex flex-col items-start"
        >
          <h1 className="font-grotesk uppercase text-[60px] md:text-[100px] leading-[0.8] tracking-tighter">
            Platform<br />
            <span className="text-neon">Capabilities</span>
          </h1>
          <span className="font-condiment text-neon text-[32px] md:text-[48px] mix-blend-exclusion mt-6 -rotate-2">Next Gen Architecture</span>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <CapabilityCard icon={Bot} title="Gemini Live" desc="Built on the highest performance WebSocket protocol for near-zero latency voice interactions." delay={0.1} />
          <CapabilityCard icon={Database} title="Dynamic Context" desc="Upload any JD or Resume. Clarix extracts intent and skills instantly to frame the conversation." delay={0.2} />
          <CapabilityCard icon={Cpu} title="Skill Verification" desc="AI identifies actual technical proficiency through deep-dive adaptive questioning." delay={0.3} />
          <CapabilityCard icon={PhoneCall} title="Direct Dial" desc="Outbound calling capabilities via Twilio allow interviews to happen on physical phone lines." delay={0.4} />
          <CapabilityCard icon={Globe} title="Global Language" desc="Switch between English and local dialects fluidly to accommodate diverse talent pools." delay={0.5} />
          <CapabilityCard icon={Zap} title="Instant Scorecard" desc="Comprehensive reporting with rarity scores and hiring recommendations delivered in seconds." delay={0.6} />
        </div>

        <div className="mt-40 text-center">
           <Link to="/app" className="inline-block liquid-glass border border-neon/30 text-neon px-12 py-6 rounded-full font-grotesk text-2xl uppercase tracking-widest hover:bg-neon hover:text-background transition-all duration-500 shadow-[0_0_40px_rgba(111,255,0,0.1)]">
              Experience Clarix Now
           </Link>
        </div>
      </main>
    </div>
  );
}

function CapabilityCard({ icon: Icon, title, desc, delay }) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 30 }} 
      whileInView={{ opacity: 1, y: 0 }} 
      viewport={{ once: true }}
      transition={{ delay }}
      className="liquid-glass rounded-[40px] p-10 border border-white/5 hover:border-neon/20 transition-all duration-500 group shadow-2xl"
    >
      <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-10 group-hover:bg-neon/10 transition-colors">
        <Icon size={32} className="text-cream group-hover:text-neon transition-colors" />
      </div>
      <h3 className="font-grotesk text-[32px] uppercase leading-none tracking-tight mb-6 group-hover:text-neon transition-colors">{title}</h3>
      <p className="font-mono text-xs uppercase tracking-widest text-cream/50 leading-relaxed group-hover:text-cream/80 transition-colors">{desc}</p>
    </motion.div>
  );
}
