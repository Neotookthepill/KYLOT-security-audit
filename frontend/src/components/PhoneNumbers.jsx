import React from "react";
import { Phone } from "lucide-react";
import { phoneHref, splitPhoneNumbers } from "@/lib/phone";

/**
 * Affiche un ou plusieurs numéros, chacun avec son propre lien tel:.
 * Les valeurs contenant « / » sont découpées sans modifier le texte source.
 */
export default function PhoneNumbers({
  value,
  className = "",
  linkClassName = "",
  iconSize = 12,
  showIcon = true,
}) {
  const numbers = splitPhoneNumbers(value);
  if (!numbers.length) return null;

  return (
    <span className={`inline-flex flex-col items-start gap-0.5 ${className}`.trim()}>
      {numbers.map((number, index) => {
        const href = phoneHref(number);
        const content = (
          <>
            {showIcon && <Phone size={iconSize} className="shrink-0" aria-hidden="true" />}
            <span>{number}</span>
          </>
        );
        if (!href) {
          return <span key={`${number}-${index}`} className={linkClassName}>{content}</span>;
        }
        return (
          <a
            key={`${number}-${index}`}
            href={href}
            className={`inline-flex min-h-6 items-center gap-1 py-0.5 hover:underline ${linkClassName}`.trim()}
            aria-label={`Appeler le ${number}`}
            onClick={(event) => event.stopPropagation()}
          >
            {content}
          </a>
        );
      })}
    </span>
  );
}
