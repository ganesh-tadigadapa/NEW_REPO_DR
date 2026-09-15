import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DR Screening — SIH26038",
  description:
    "Explainable AI for diabetic retinopathy screening. Screening triage aid, not a diagnostic device.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Project rule: the disclaimer is on every UI surface, not just the report. */}
        <div className="disclaimer">Screening triage aid — not a diagnostic device</div>
        {children}
      </body>
    </html>
  );
}
