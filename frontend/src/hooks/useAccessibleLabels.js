import { useEffect } from "react";

/**
 * Relie les libellés métier aux contrôles quand le composant historique n'a pas
 * encore d'id/htmlFor. Le lien est refait après chaque rendu/ouverture de dialogue.
 */
export default function useAccessibleLabels() {
  useEffect(() => {
    let frame = 0;
    let seq = 0;
    const link = () => {
      document.querySelectorAll("label:not([for])").forEach((label) => {
        const parent = label.parentElement;
        if (!parent) return;
        const controls = Array.from(parent.querySelectorAll("input:not([type=hidden]), select, textarea"))
          .filter((control) => !control.closest("label") || control.closest("label") === label.parentElement);
        if (controls.length !== 1) return;
        const control = controls[0];
        if (!control.id) control.id = `qy-auto-field-${++seq}`;
        label.htmlFor = control.id;
        if (!control.getAttribute("aria-label")) {
          const text = (label.textContent || "").trim();
          if (text) control.setAttribute("aria-label", text);
        }
      });
    };
    const schedule = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => { frame = 0; link(); });
    };
    link();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
}
