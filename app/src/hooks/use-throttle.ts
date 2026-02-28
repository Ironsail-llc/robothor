"use client";

import { useState, useEffect, useRef } from "react";

/**
 * Returns a throttled version of the value that updates at most once per `ms`.
 * Useful for expensive renders (e.g., ReactMarkdown) driven by rapid state updates.
 */
export function useThrottle<T>(value: T, ms: number): T {
  const [throttled, setThrottled] = useState(value);
  const lastUpdated = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const now = Date.now();
    const elapsed = now - lastUpdated.current;

    if (timerRef.current) clearTimeout(timerRef.current);

    const delay = elapsed >= ms ? 0 : ms - elapsed;
    timerRef.current = setTimeout(() => {
      lastUpdated.current = Date.now();
      setThrottled(value);
    }, delay);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [value, ms]);

  return throttled;
}
