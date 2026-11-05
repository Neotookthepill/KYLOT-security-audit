import { useEffect } from "react";

/**
 * Relie les libellés métier aux contrôles quand le composant historique n'a pas
 * encore d'id/htmlFor. Le lien est refait après chaque rendu/ouverture de dialogue.
 */
export default function useAccessibleLabels() {
  useEffect(() => {
    let frame = 0;
    let seq = 0;
    const isControl = (el) => el && el.matches && el.matches("input:not([type=hidden]), select, textarea, button[role=combobox]");
    const firstControl = (root) => {
      if (!root) return null;
      if (isControl(root)) return root;
      return root.querySelector?.("input:not([type=hidden]), select, textarea, button[role=combobox]") || null;
    };
    const link = () => {
      document.querySelectorAll("label:not([for])").forEach((label) => {
        const text = (label.textContent || "").trim();
        if (!text) return;
        let control = null;
        let node = label.nextElementSibling;
        while (node && !control) {
          control = firstControl(node);
          node = node.nextElementSibling;
        }
        if (!control) control = firstControl(label.parentElement);
        if (!control || !control.id && control.getAttribute("aria-label")) return;
        if (!control.id) control.id = `qy-auto-field-${++seq}`;
        label.htmlFor = control.id;
        if (!control.getAttribute("aria-label")) control.setAttribute("aria-label", text);
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
