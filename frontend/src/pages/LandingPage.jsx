import React from 'react';
import { Mail, Twitter, Github, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function LandingPage() {
  return (
    <div className="relative min-h-screen bg-background text-cream overflow-x-hidden font-sans selection:bg-neon selection:text-background">
      {/* Texture Overlay */}
      <div 
        className="fixed inset-0 z-50 pointer-events-none mix-blend-lighten opacity-60"
        style={{
          backgroundImage: 'url(/texture.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center'
        }}
      />

      {/* SECTION 1: HERO */}
      <section className="relative w-full h-screen rounded-b-[32px] overflow-hidden flex flex-col items-center">
        {/* Background Video */}
        <video 
          className="absolute inset-0 w-full h-full object-cover z-0"
          autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_045634_e1c98c76-1265-4f5c-882a-4276f2080894.mp4"
        />
        <div className="absolute inset-0 bg-background/30 z-[1]" />

        <div className="relative z-10 w-full max-w-[1831px] px-6 sm:px-12 md:px-16 flex flex-col h-full">
          {/* Header */}
          <header className="flex items-center justify-between pt-8">
            <Link to="/" className="font-grotesk text-xl sm:text-2xl uppercase tracking-wider hover:text-neon transition-colors">
              Clarix.Ai
            </Link>
            
            <nav className="hidden lg:flex liquid-glass rounded-[28px] px-12 py-5 items-center gap-10">
              {[
                { name: 'Home', path: '/' },
                { name: 'About', path: '/about' },
                { name: 'Features', path: '/features' },
                { name: 'App', path: '/app' },
              ].map(link => (
                <Link key={link.name} to={link.path} className="font-grotesk text-[13px] uppercase hover:text-neon transition-colors tracking-widest">
                  {link.name}
                </Link>
              ))}
            </nav>
            
            <div className="lg:hidden">
              <Link to="/app" className="font-grotesk text-xs uppercase text-neon border border-neon px-4 py-2 rounded-full">
                Launch
              </Link>
            </div>
          </header>

          

          {/* Hero Content */}
          <div className="flex-1 flex flex-col justify-center">
            <div className="relative w-full max-w-[900px] lg:ml-24 xl:ml-32">
              <h1 className="font-grotesk uppercase text-[42px] sm:text-[64px] md:text-[80px] lg:text-[100px] leading-[0.95] tracking-tighter">
                Beyond resumes <br />
                and ( their ) traditional limits
              </h1>
              <span className="font-condiment text-neon text-[28px] sm:text-[42px] md:text-[54px] absolute right-4 md:right-12 -bottom-10 md:bottom-2 translate-y-full md:translate-y-0 -rotate-2 mix-blend-exclusion opacity-95 normal-case">
                Ai recruiter
              </span>
              
              {/* Hero CTA Button */}
              <div className="mt-20 md:mt-12 flex items-center gap-8">
                <Link to="/app" className="group flex items-center gap-4 bg-neon px-8 py-4 rounded-full hover:scale-105 transition-all duration-300">
                  <span className="font-grotesk text-background text-lg uppercase tracking-wider">Start Interview</span>
                  <div className="w-8 h-8 rounded-full bg-background flex items-center justify-center group-hover:translate-x-1 transition-transform">
                    <ArrowRight size={18} className="text-neon" />
                  </div>
                </Link>
                <div className="hidden sm:block font-mono text-[11px] uppercase tracking-[0.2em] text-cream/60 max-w-[200px] leading-relaxed">
                  Fully autonomous voice screening in real-time
                </div>
              </div>
            </div>
          </div>
          
          
        </div>
      </section>

      {/* SECTION 2: ABOUT / INTRO */}
      <section className="relative w-full min-h-screen overflow-hidden flex flex-col justify-center py-24">
        {/* Background Video */}
        <video 
          className="absolute inset-0 w-full h-full object-cover z-0"
          autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_151551_992053d1-3d3e-4b8c-abac-45f22158f411.mp4"
        />
        <div className="absolute inset-0 bg-background/50 z-[1]" />

        <div className="relative z-10 w-full max-w-[1831px] mx-auto px-6 sm:px-12 md:px-16 flex flex-col justify-between h-full min-h-[70vh]">
          
          <div className="flex flex-col lg:flex-row justify-between items-start gap-16 lg:gap-24">
            <div className="relative">
              <h2 className="font-grotesk uppercase text-[36px] sm:text-[54px] lg:text-[72px] leading-[0.9]">
                Hello!<br />
                I'm clarix
              </h2>
              <span className="font-condiment text-neon text-[42px] sm:text-[60px] lg:text-[84px] absolute right-[-20px] bottom-[-20px] translate-x-0 translate-y-1/2 rotate-[-5deg] mix-blend-exclusion normal-case">
                Clarix
              </span>
            </div>
            <div className="font-mono text-[14px] md:text-[18px] uppercase max-w-[320px] leading-relaxed tracking-wider text-cream/90">
              A digital agent fixed beyond time and bias. An exploration of intelligence, voice, and instant screening.
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12 mt-32">
             <div className="space-y-4">
                <div className="w-12 h-[2px] bg-neon" />
                <p className="font-mono text-xs uppercase tracking-widest leading-relaxed text-cream/40">
                  Built on the latest foundation models to ensure accuracy and empathy in every conversation.
                </p>
             </div>
             <div className="space-y-4">
                <div className="w-12 h-[2px] bg-neon" />
                <p className="font-mono text-xs uppercase tracking-widest leading-relaxed text-cream/40">
                  Scaling your talent pipeline with infinite capacity and zero fatigue.
                </p>
             </div>
          </div>
        </div>
      </section>

      {/* SECTION 3: TEAM */}
      <section className="relative w-full bg-background py-32">
        <div className="w-full max-w-[1831px] mx-auto px-6 sm:px-12 md:px-16">

          <div className="flex flex-col lg:flex-row justify-between items-start lg:items-end gap-12 mb-24">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-neon mb-6">The Builders</p>
              <h2 className="font-grotesk uppercase text-[36px] sm:text-[54px] lg:text-[72px] leading-[0.9]">
                Minds Behind <br />
                <div className="ml-8 sm:ml-16 lg:ml-32 flex items-baseline gap-4">
                  <span className="font-condiment text-neon normal-case text-[48px] sm:text-[72px] lg:text-[96px]">Clarix</span> AI
                </div>
              </h2>
            </div>

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
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            <TeamCard
              videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_053923_22c0a6a5-313c-474c-85ff-3b50d25e944a.mp4"
              index="01"
              name="Rishabh Tiwari"
              role="Chief Visionary · Origin of the Spark"
            />
            <TeamCard
              videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_054411_511c1b7a-fb2f-42ef-bf6c-32c0b1a06e79.mp4"
              index="02"
              name="Prerna Shekhawat"
              role="Neural Conductor · Cognitive Systems"
            />
            <TeamCard
              videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_055427_ac7035b5-9f3b-4289-86fc-941b2432317d.mp4"
              index="03"
              name="Sanyam Kumat"
              role="Deep Intelligence Architect · AI Research"
            />
            <TeamCard
              videoUrl="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_055729_72d66327-b59e-4ae9-bb70-de6ccb5ecdb0.mp4"
              index="04"
              name="Ajay Singh Rathore"
              role="Systems Convergence Commander · Full-Stack"
            />
          </div>
        </div>
      </section>

      {/* SECTION 4: CTA */}
      <section className="relative w-full overflow-hidden">
        <video 
          className="w-full h-auto block min-h-[400px] object-cover md:object-contain"
          autoPlay loop muted playsInline
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260331_055729_72d66327-b59e-4ae9-bb70-de6ccb5ecdb0.mp4"
        />

        <div className="absolute inset-0 w-full h-full flex flex-col justify-center bg-background/20">
          <div className="relative w-full h-full max-w-[1831px] mx-auto px-8">
            
            

            {/* Right Aligned Text */}
            <div className="absolute top-1/2 -translate-y-1/2 right-0 lg:pr-[15%] xl:pr-[20%] px-6 text-right">
              <div className="relative inline-block">
                <span className="font-condiment text-neon text-[24px] sm:text-[48px] lg:text-[72px] absolute -top-12 -left-8 md:-top-20 md:-left-24 mix-blend-exclusion normal-case rotate-[-8deg]">
                  Hire smarter
                </span>
                <h2 className="font-grotesk uppercase text-[20px] sm:text-[40px] md:text-[54px] lg:text-[64px] leading-[1] tracking-tight">
                  <div className="mb-6 lg:mb-10 text-neon">TRY NOW.</div>
                  <div className="mb-2">REVEAL TRUE TALENT.</div>
                  <div className="mb-2 text-cream/80 text-[0.8em]">DEFINE YOUR TEAM.</div>
                  <div>HIRE THE BEST.</div>
                </h2>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function SocialButton({ icon: Icon }) {
  return (
    <button className="w-[50px] h-[50px] sm:w-[60px] sm:h-[60px] flex items-center justify-center liquid-glass rounded-[1.25rem] hover:bg-white/10 transition-all hover:scale-110 active:scale-95 border border-white/5">
      <Icon size={22} className="text-cream" />
    </button>
  );
}

function ResponsiveSocialButton({ icon: Icon, hasBorder }) {
  return (
    <button className={`w-[15vw] h-[15vw] sm:w-[120px] sm:h-[120px] md:w-[140px] md:h-[140px] lg:w-[160px] lg:h-[160px] flex items-center justify-center hover:bg-white/10 transition-colors ${hasBorder ? 'border-b border-white/10' : ''}`}>
      <Icon className="w-1/3 h-1/4 text-cream" />
    </button>
  );
}

function TeamCard({ videoUrl, index, name, role, flip = false }) {
  return (
    <div className="liquid-glass rounded-[40px] p-5 hover:bg-white/10 transition-all duration-500 group border border-white/5 shadow-2xl">
      <div className="relative w-full aspect-square rounded-[32px] overflow-hidden bg-black/50">
        <video
          className={`absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-700${flip ? ' scale-x-[-1]' : ''}`}
          autoPlay loop muted playsInline
          src={videoUrl}
        />

        {/* Index badge — top left */}
        <div className="absolute top-5 left-5 font-mono text-[11px] text-cream/35 uppercase tracking-[0.25em]">
          {index}
        </div>

        {/* Name + role overlay — bottom */}
        <div className="absolute bottom-5 left-5 right-5 liquid-glass rounded-[24px] px-6 py-5 border border-white/10 backdrop-blur-md">
          <div className="w-7 h-[2px] bg-neon mb-3" />
          <p className="font-grotesk uppercase text-[15px] sm:text-[17px] leading-tight tracking-tight">{name}</p>
          <p className="font-mono text-[9px] sm:text-[10px] text-cream/50 uppercase tracking-[0.18em] mt-1.5 leading-relaxed">{role}</p>
        </div>
      </div>
    </div>
  );
}
