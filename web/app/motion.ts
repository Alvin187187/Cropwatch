"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { RefObject } from "react";

gsap.registerPlugin(useGSAP);

const MOTION = "(prefers-reduced-motion: no-preference)";

export function useMotion<T extends HTMLElement>(
  ref: RefObject<T | null>,
  build: () => void,
  deps: unknown[],
) {
  useGSAP(() => {
    const root = ref.current;
    if (!root) return;
    const mm = gsap.matchMedia();
    mm.add(MOTION, build, root);
    return () => mm.revert();
  }, { scope: ref, dependencies: deps });
}
