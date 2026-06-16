import React, { useEffect, useRef, useState } from "react";

export function Reveal({ children, delay = 0, className = "", as: Tag = "div", ...rest }) {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setShown(true); io.disconnect(); }
    }, { threshold: 0.12 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <Tag ref={ref} className={`reveal ${shown ? "in" : ""} ${className}`}
      style={{ transitionDelay: `${delay}ms` }} {...rest}>
      {children}
    </Tag>
  );
}

export function CountUp({ value, decimals = 0, duration = 1100, suffix = "", prefix = "" }) {
  const ref = useRef(null);
  const [val, setVal] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const start = performance.now();
      const tick = (now) => {
        const t = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - t, 3);
        setVal(value * eased);
        if (t < 1) raf = requestAnimationFrame(tick); else setVal(value);
      };
      raf = requestAnimationFrame(tick);
    }, { threshold: 0.4 });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [value, duration]);
  return (
    <span ref={ref}>
      {prefix}
      {val.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
      {suffix}
    </span>
  );
}

export function Segmented({ options, value, onChange, variant = "" }) {
  return (
    <div className={`seg ${variant}`} role="tablist">
      {options.map((o) => {
        const v = typeof o === "object" ? o.value : o;
        const label = typeof o === "object" ? o.label : o;
        return (
          <button key={v} className={v === value ? "on" : ""} onClick={() => onChange(v)}
            role="tab" aria-selected={v === value}>
            {label}
          </button>
        );
      })}
    </div>
  );
}

export function SegLabel({ children }) {
  return <span className="seg-label">{children}</span>;
}
