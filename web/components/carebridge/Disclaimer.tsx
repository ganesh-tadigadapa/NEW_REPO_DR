"use client";
/**
 * The project rule is that the disclaimer appears on every UI surface. A rule like that
 * is only met if the person can read it, so it is translated like everything else.
 */
import { useCareBridge } from "./CareBridgeProvider";

export default function Disclaimer() {
  const { t } = useCareBridge();
  return <div className="disclaimer">{t("common.disclaimer")}</div>;
}
