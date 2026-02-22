"use client";

import { useState, useEffect, useRef } from "react";

/**
 * Returns a throttled version of the value that updates at most once per `ms`.
 * Useful for expensive renders (e.g., ReactMarkdown) driven by rapid state updates.
 */
export function useThrottle<T>(value: T, ms: number): T {
  const [throttled, setThrottled] = useState(value);
  const lastUpdated = useRef(Date.now());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const now = Date.now();
    const elapsed = now - lastUpdated.current;

    if (elapsed >= ms) {
      // Enough time has passed — update immediately
      lastUpdated.current = now;
      setThrottled(value);
    } else {
      // Schedule a trailing update
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        lastUpdated.current = Date.now();
        setThrottled(value);
      }, ms - elapsed);
    }

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [value, ms]);

  return throttled;
}
