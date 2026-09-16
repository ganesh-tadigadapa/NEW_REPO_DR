import "./globals.css";
import type { Metadata } from "next";
import AuthProvider from "@/components/AuthProvider";
import CareBridgeProvider from "@/components/carebridge/CareBridgeProvider";
import Disclaimer from "@/components/carebridge/Disclaimer";

export const metadata: Metadata = {
  title: "DR Screening — SIH26038",
  description:
    "Explainable AI for diabetic retinopathy screening. Screening triage aid, not a diagnostic device.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* CareBridge sits OUTSIDE the session, and deliberately: someone who cannot read
            English has to be able to change the language before they can sign in, and
            changing it must never disturb the session. It also owns <html lang>. */}
        <CareBridgeProvider>
          {/* Project rule: the disclaimer is on every UI surface, not just the report. */}
          <Disclaimer />
          {/* The session is read once here and shared by every page, so the navigation and
              the route guards agree about who is signed in. */}
          <AuthProvider>{children}</AuthProvider>
        </CareBridgeProvider>
      </body>
    </html>
  );
}
