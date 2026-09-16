"use client";
/**
 * One place that turns an ICDR category difference into words.
 *
 * Both the comparison card and the journey list render the same change, and they must
 * never word it differently. The NUMBER always comes from the backend — this decides
 * nothing about what changed, only how to say it in the reader's language.
 */
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";

export function useChangeLabel() {
  const { t } = useCareBridge();
  return (change: number): string => {
    if (change === 0) return t("passport.categorySame");
    const n = Math.abs(change);
    // The unit is a separate key per language, so each picks its own singular and
    // plural rather than English's rule being assumed for all of them — the same split
    // `src/passport/message.py` makes for the WhatsApp text.
    const unit = t(n === 1 ? "passport.categoryUnitOne" : "passport.categoryUnitMany");
    return t(change > 0 ? "passport.categoryHigher" : "passport.categoryLower",
             { n, unit });
  };
}
