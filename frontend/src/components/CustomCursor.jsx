import { useEffect, useState } from 'react';
import { motion, useMotionValue, useSpring } from 'framer-motion';

export default function CustomCursor() {
  const [visible, setVisible] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [clicked, setClicked] = useState(false);

  const mouseX = useMotionValue(-300);
  const mouseY = useMotionValue(-300);

  // Dot snaps almost instantly
  const dotX = useSpring(mouseX, { stiffness: 3000, damping: 100 });
  const dotY = useSpring(mouseY, { stiffness: 3000, damping: 100 });
  // Ring lags pleasantly behind
  const ringX = useSpring(mouseX, { stiffness: 110, damping: 16 });
  const ringY = useSpring(mouseY, { stiffness: 110, damping: 16 });

  useEffect(() => {
    // Skip on touch-only devices
    if (window.matchMedia('(hover: none)').matches) return;

    const move  = (e) => { mouseX.set(e.clientX); mouseY.set(e.clientY); setVisible(true); };
    const leave = () => setVisible(false);
    const enter = () => setVisible(true);
    const down  = () => setClicked(true);
    const up    = () => setClicked(false);

    document.addEventListener('mousemove',  move);
    document.addEventListener('mouseleave', leave);
    document.addEventListener('mouseenter', enter);
    document.addEventListener('mousedown',  down);
    document.addEventListener('mouseup',    up);

    const hoverIn  = () => setHovered(true);
    const hoverOut = () => setHovered(false);
    const attach = () => {
      document.querySelectorAll('a, button, [data-cursor]').forEach(el => {
        el.addEventListener('mouseenter', hoverIn);
        el.addEventListener('mouseleave', hoverOut);
      });
    };
    attach();
    // re-attach when DOM changes (SPA navigation)
    const observer = new MutationObserver(attach);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      document.removeEventListener('mousemove',  move);
      document.removeEventListener('mouseleave', leave);
      document.removeEventListener('mouseenter', enter);
      document.removeEventListener('mousedown',  down);
      document.removeEventListener('mouseup',    up);
      observer.disconnect();
    };
  }, []);

  return (
    <>
      {/* Dot */}
      <motion.div
        className="fixed top-0 left-0 rounded-full bg-neon pointer-events-none z-[9999] mix-blend-difference"
        style={{ x: dotX, y: dotY, translateX: '-50%', translateY: '-50%' }}
        animate={{
          width:   hovered ? 14 : clicked ? 5 : 8,
          height:  hovered ? 14 : clicked ? 5 : 8,
          opacity: visible ? 1 : 0,
        }}
        transition={{ duration: 0.12 }}
      />
      {/* Ring */}
      <motion.div
        className="fixed top-0 left-0 rounded-full border pointer-events-none z-[9998]"
        style={{ x: ringX, y: ringY, translateX: '-50%', translateY: '-50%' }}
        animate={{
          width:       hovered ? 56 : clicked ? 22 : 36,
          height:      hovered ? 56 : clicked ? 22 : 36,
          opacity:     visible ? (hovered ? 0.8 : 0.45) : 0,
          borderColor: hovered ? 'rgba(111,255,0,0.8)' : 'rgba(111,255,0,0.35)',
          borderWidth: hovered ? 1.5 : 1,
        }}
        transition={{ duration: 0.18 }}
      />
    </>
  );
}
