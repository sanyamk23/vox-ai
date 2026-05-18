import React from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Zap } from 'lucide-react';

export default function AboutPage() {
  return (
    <div className="relative min-h-screen bg-background text-cream overflow-x-hidden font-sans selection:bg-neon selection:text-background">
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
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_151551_992053d1-3d3e-4b8c-abac-45f22158f411.mp4"
        />
        <div className="absolute inset-0 bg-background/60" />
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
            <Link key={link.name} to={link.path} className={`font-grotesk text-[13px] uppercase tracking-widest transition-colors ${link.path === '/about' ? 'text-neon' : 'hover:text-neon'}`}>
              {link.name}
            </Link>
          ))}
        </nav>

        <Link to="/app" className="font-grotesk text-xs uppercase text-neon border border-neon px-5 py-2 rounded-full hover:bg-neon hover:text-background transition-all">
          Launch App
        </Link>
      </header>

      <main className="relative z-10 w-full max-w-[1440px] mx-auto px-6 sm:px-12 lg:px-16 pt-32 pb-24 flex flex-col items-center">
        <motion.div 
          initial={{ opacity: 0, y: 20 }} 
          animate={{ opacity: 1, y: 0 }} 
          className="text-center mb-32"
        >
          <div className="relative inline-block">
             <span className="font-condiment text-neon text-[40px] md:text-[60px] absolute -top-12 -left-12 rotate-[-10deg] mix-blend-exclusion">Our</span>
             <h1 className="font-grotesk uppercase text-[60px] md:text-[120px] leading-[0.8] tracking-tighter">
                Story
             </h1>
          </div>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-24 items-center w-full">
          <motion.div 
            initial={{ opacity: 0, x: -30 }} 
            animate={{ opacity: 1, x: 0 }} 
            transition={{ delay: 0.2 }}
            className="space-y-8"
          >
            <h2 className="font-grotesk text-[42px] uppercase leading-none tracking-tight">Radical Transparency in Hiring.</h2>
            <div className="space-y-6 font-mono text-sm md:text-lg text-cream/70 uppercase leading-relaxed tracking-wide">
              <p>We believe that hiring is fundamentally broken. It's slow, biased, and incredibly resource-intensive. Clarix.Ai was built to solve this by creating a direct bridge between JD and Talent.</p>
              <p>By leveraging state-of-the-art Gemini Live Voice AI, we have created an agent capable of conducting hyper-realistic, empathetic, and real-time technical interviews.</p>
            </div>
          </motion.div>
          
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }} 
            animate={{ opacity: 1, scale: 1 }} 
            transition={{ delay: 0.4 }} 
            className="liquid-glass rounded-[48px] p-12 lg:p-16 flex flex-col justify-center border border-white/5 shadow-2xl"
          >
            <h3 className="font-condiment text-neon text-[48px] md:text-[72px] normal-case -rotate-2 mb-8">Values</h3>
            <ul className="space-y-6 font-mono text-xs md:text-base uppercase tracking-[0.2em] text-cream">
              <li className="flex items-center gap-6"><div className="w-3 h-3 bg-neon rounded-full shadow-[0_0_15px_#6FFF00]" /> Uncompromising Speed</li>
              <li className="flex items-center gap-6"><div className="w-3 h-3 bg-neon rounded-full shadow-[0_0_15px_#6FFF00]" /> Zero Bias Analysis</li>
              <li className="flex items-center gap-6"><div className="w-3 h-3 bg-neon rounded-full shadow-[0_0_15px_#6FFF00]" /> Real-time Empathy</li>
              <li className="flex items-center gap-6"><div className="w-3 h-3 bg-neon rounded-full shadow-[0_0_15px_#6FFF00]" /> Infinite Scale</li>
            </ul>
          </motion.div>
        </div>

        <div className="mt-48 w-full border-t border-white/10 pt-20 flex flex-col lg:flex-row justify-between gap-12 opacity-40">
           <div className="font-mono text-xs uppercase tracking-widest max-w-xs">Clarix.Ai is a product of deep research in conversational intelligence and recruitment logistics.</div>
           <div className="font-mono text-xs uppercase tracking-widest max-w-xs">© 2026 CLARIX LABS. ALL RIGHTS RESERVED. BEYOND EARTH AND FAMILIAR BOUNDARIES.</div>
        </div>
      </main>
    </div>
  );
}
