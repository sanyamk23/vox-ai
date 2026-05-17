import React from 'react';
import { Link, useLocation } from 'react-router-dom';

export default function Navbar() {
  const location = useLocation();
  const isApp = location.pathname === '/app';
  const isHome = location.pathname === '/';

  if (isApp || isHome) return null; // App and Home have their own headers

  return (
    <header className="absolute top-0 left-0 right-0 z-50 px-6 sm:px-12 py-6 flex items-center justify-between">
      <Link to="/" className="flex items-center gap-3 group">
        <div className="font-grotesk text-[20px] uppercase tracking-wide text-cream group-hover:text-neon transition-colors">
          Clarix.Ai
        </div>
      </Link>

      <nav className="hidden lg:flex liquid-glass rounded-[28px] px-[40px] py-[16px] items-center gap-8">
        {[
          { name: 'Home', path: '/' },
          { name: 'About', path: '/about' },
          { name: 'Features', path: '/features' },
          { name: 'Dashboard', path: '/dashboard' },
          { name: 'Launch App', path: '/app' },
        ].map(link => (
          <Link key={link.name} to={link.path} className={`font-grotesk text-[13px] uppercase transition-colors ${location.pathname === link.path ? 'text-neon' : 'text-cream hover:text-neon'}`}>
            {link.name}
          </Link>
        ))}
      </nav>

      <div className="flex items-center gap-4">
        <Link to="/app" className="lg:hidden font-grotesk text-[13px] uppercase text-neon border border-neon px-4 py-2 rounded-full">
          Launch App
        </Link>
      </div>
    </header>
  );
}
