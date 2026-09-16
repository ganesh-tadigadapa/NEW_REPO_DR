"use client";
/**
 * ⓘ Why am I seeing this? — the reusable honesty disclosure.
 *
 * Attach it to anything that gives a person advice about their own health. It says where
 * the information came from and what it is not. Both sentences come from the translation
 * layer, so it speaks whatever language the reader chose.
 */
import { useCareBridge } from "./CareBridgeProvider";

export default function WhyThis({ extra }: { extra?: string }) {
  const { t } = useCareBridge();
  return (
    <details className="cb-why">
      <summary>
        <span aria-hidden="true">ⓘ</span> {t("why.label")}
      </summary>
      <p>{t("why.body")}</p>
      {extra && <p>{extra}</p>}
    </details>
  );
}
