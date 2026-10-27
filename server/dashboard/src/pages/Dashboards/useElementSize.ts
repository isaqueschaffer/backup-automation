import { useEffect, useRef, useState, type RefObject } from "react";

export interface ElementSize {
  width: number;
  height: number;
}

export function useElementSize<T extends HTMLElement = HTMLDivElement>(): [RefObject<T>, ElementSize] {
  const ref = useRef<T>(null);
  const [size, setSize] = useState<ElementSize>({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") {
      return;
    }

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        setSize({ width, height });
      }
    });

    observer.observe(el);

    return () => {
      observer.disconnect();
    };
  }, []);

  return [ref, size];
}

export default useElementSize;
