"use client";
/**
 * 🔊 Listen — read a passage aloud in the chosen language.
 *
 * Uses the browser's own speech synthesis. Nothing is sent anywhere: the text is already
 * on the device, and a patient's result has no business travelling to a voice API to be
 * turned into sound.
 *
 * Three honest states, and a fourth that matters more than the others:
 *   Listen → Playing… → Stop
 *   and "no {language} voice on this device", which is common and must not be hidden.
 * A device without a Telugu voice keeps the Telugu TEXT and says why it cannot speak it.
 * It never reads Telugu aloud in an English voice.
 */
import { useId } from "react";
import { useCareBridge } from "./CareBridgeProvider";

export default function SpeakButton({
  parts,
  label,
  id,
  small = false,
}: {
  /** The passage, in reading order. Blank entries are dropped. */
  parts: (string | null | undefined)[];
  /** Overrides the default "Listen" label. */
  label?: string;
  /** Stable id when several buttons share a page; auto-generated otherwise. */
  id?: string;
  small?: boolean;
}) {
  const auto = useId();
  const key = id ?? auto;
  const { t, meta, voice, speech, speak, stopSpeaking } = useCareBridge();

  // Voice guidance switched off in the language panel: the control disappears entirely
  // rather than sitting there disabled.
  if (!voice) return null;

  const speaking = speech.speakingId === key;
  const usable = speech.supported && speech.voiceAvailable;

  if (!usable) {
    return (
      <p className="cb-voicenote" role="note">
        <span aria-hidden="true">🔇</span>{" "}
        {speech.supported
          ? t("errors.voiceNoLanguage", { language: meta.nativeName })
          : t("errors.voiceUnsupported")}
      </p>
    );
  }

  return (
    <button
      type="button"
      className={`cb-speak${speaking ? " on" : ""}${small ? " small" : ""}`}
      aria-label={speaking ? t("a11y.stopSpeaking") : t("a11y.speak")}
      aria-pressed={speaking}
      onClick={() => (speaking ? stopSpeaking() : speak(key, parts))}
    >
      <span aria-hidden="true">{speaking ? "⏹" : "🔊"}</span>
      <span>{speaking ? t("common.stop") : (label ?? t("common.listen"))}</span>
      {speaking && <span className="cb-speakdots" aria-hidden="true" />}
    </button>
  );
}
