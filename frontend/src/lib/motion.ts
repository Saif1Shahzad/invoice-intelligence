import { useEffect, type RefObject, type DependencyList } from "react";
import { animate, createScope, stagger } from "animejs";

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Staggered entrance for `[data-anim]` children inside root. Scoped + reverted on cleanup. */
export function useStaggerIn(root: RefObject<HTMLElement | null>, deps: DependencyList = []) {
  useEffect(() => {
    if (!root.current || prefersReducedMotion()) return;
    const scope = createScope({ root: root as RefObject<HTMLElement> }).add(() => {
      animate("[data-anim]", {
        opacity: [0, 1],
        translateY: [10, 0],
        delay: stagger(45),
        duration: 420,
        ease: "outQuad",
      });
    });
    return () => scope.revert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** One-shot pulse to confirm a highlighted field. */
export function pulse(el: Element | null) {
  if (!el || prefersReducedMotion()) return;
  return animate(el, { scale: [1, 1.03, 1], duration: 380, ease: "outQuad" });
}

export function slideIn(el: Element | null) {
  if (!el || prefersReducedMotion()) return;
  return animate(el, { translateX: ["100%", "0%"], opacity: [0.6, 1], duration: 360, ease: "outCubic" });
}

