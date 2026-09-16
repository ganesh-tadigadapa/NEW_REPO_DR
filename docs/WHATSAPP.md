# CareBridge — WhatsApp report delivery

The last step of the patient journey:

```
screen → analyse → explain → report → WhatsApp → next action
```

After a screening, the patient's report does not stay trapped inside a website they may
never open again. The **same PDF** — the one the pipeline already generated — is
delivered to the number they already proved is theirs during sign-in, with a short
message in the language they are already reading the result in.

> **What this is not.** WhatsApp delivery is a communication layer. It cannot calculate
> or change a DR grade, a referral, a confidence, a Grad-CAM, an ICDR rule result or a
> clinician review. If this feature were deleted, every clinical behaviour in the service
> would be byte-for-byte what it is today.

---

## 1. What the patient sees

On the result page, after the result and the next steps, a delivery card:

```
📲 DELIVERY
Your screening report is ready
Your detailed CareBridge report has been generated successfully.

  👁 Screened  →  💡 Explained  →  📄 Report ready  →  💬 On WhatsApp

  ┌──────────────────────────────────────────────┐
  │  💬   WhatsApp delivery                       │
  │       +91 ***** 40001                         │
  │  ┌────────────────────────────────────────┐   │
  │  │  💬  Send report on WhatsApp           │   │
  │  └────────────────────────────────────────┘   │
  │  Your PDF will be delivered to your           │
  │  registered WhatsApp number.                  │
  └──────────────────────────────────────────────┘
```

The number is never typed and never shown in full. Button states are
`Send → ⏳ Sending report… → ✓ Report sent successfully` or `⚠ <reason> → ↻ Try again`.

On WhatsApp they receive two things — a message and the PDF as a document:

```
🩺 *CareBridge Screening Report*

Your retinal screening has been completed.

*Screening result*
• DR grade: Grade 2 of 4
• Classification: Moderate NPDR
• Referral status: Referral recommended

*What this means*
Clear changes were seen in the blood vessels at the back of your eye…

📄 Your detailed screening report is attached.

⚠️ This is an AI-assisted screening result, not a medical diagnosis.
   Please show this report to an eye-care professional.
```

Every clinical value in that message is read verbatim from the screening result. The
grade, the label and the referral are copied, never recomputed — `src/delivery/message.py`
contains no threshold and no comparison.

---

## 2. Architecture

```
POST /v1/analyze                     (unchanged medical pipeline)
      │
      ├─→ result + PDF to the browser          ← the existing response, untouched
      ├─→ EvidenceStore                        ← the existing evidence file
      └─→ ReportMediaStore.save(pdf_bytes)     ← NEW: keeps THAT PDF + who owns it

POST /v1/reports/{scan_id}/whatsapp  (authenticated patient)
      │  1. is this report the caller's own?
      │  2. do the PDF bytes still exist?
      │  3. was it just sent?         → return the first delivery, send nothing
      │  4. is WhatsApp configured?   → "not configured", send nothing
      │  5. mint a signed, 15-minute media URL for THIS report only
      │  6. compose the message from the stored result, in the patient's language
      └─ 7. one provider call  (WHATSAPP_PROVIDER = meta | twilio)
                │
                └─→ the provider fetches GET /v1/reports/media/{scan_id}.pdf?token=…
```

Two vendors sit behind one interface, so switching is configuration rather than a diff:

```
WhatsAppReportService              picks the provider, applies the config gate once
      └── WhatsAppProvider         base.py — the interface + the shared error vocabulary
            ├── MetaWhatsAppProvider     meta.py    (free tier CAN send a PDF)
            └── TwilioWhatsAppProvider   twilio.py  (needs a PAID account)
```

Neither provider knows what a scan, an account or a grade is. Each is handed a number, a
URL, a caption and a filename, and returns a `SendResult`. Adding a third vendor means
writing one class and mapping its error codes onto the same vocabulary — no caller and
no frontend string changes.

| File | Responsibility |
|---|---|
| `src/delivery/config.py` | environment, and the guard that refuses an unreachable media URL |
| `src/delivery/media.py` | the retained PDF, ownership, and the signed-URL scheme |
| `src/delivery/message.py` | the message text, in en / hi / te / pa |
| `src/delivery/whatsapp.py` | picks the configured provider; one place applies the config gate |
| `src/delivery/providers/base.py` | the `WhatsAppProvider` interface and the shared `SendResult` vocabulary |
| `src/delivery/providers/meta.py` | Meta WhatsApp Cloud API; translates its failures into safe codes |
| `src/delivery/providers/twilio.py` | Twilio Messages API; ditto |
| `src/delivery/routes.py` | the two endpoints |

Nothing in `src/api/pipeline.py`, `src/grading/`, `src/explain/`, `src/quality/`,
`src/segment/` or `src/auth/` was modified. `src/api/main.py` gained three things: the
router mount, a `whatsapp` block in `/health`, and one call that hands the
already-generated PDF to the media store.

### Why the PDF is not regenerated

`pipeline.py` renders the PDF into the `/v1/analyze` response, and `EvidenceStore`
deliberately strips it before writing the evidence file. Those exact bytes are therefore
captured at the API layer and kept. No model runs, no Grad-CAM runs, no image is
reprocessed, and the delivered document is byte-identical to the one the patient could
download from the page.

### Why ownership lives in the delivery layer

`/v1/analyze` does not write the caller onto the scan record, on purpose: the screening
result must not depend on who uploaded the image. So the owner is recorded in the
delivery store instead — a separate file, in a separate directory, from the medical
record. `patient_ref` is not copied there, so a name typed into that free-text field can
never reach a WhatsApp message.

---

## 3. How the PDF reaches the provider

**Neither provider accepts a file upload.** Each accepts a URL and fetches the media from
its own network — Twilio via `MediaUrl`, Meta via `document.link`. The same signed URL
serves both. Two consequences, both of which this implementation faces rather than
papers over:

1. **A session token cannot travel to the provider.** So the URL carries an HMAC-SHA256
   signature instead, over `purpose | scan_id | expiry`, keyed with `AUTH_SECRET` and
   domain-separated from session tokens. It is a capability for exactly one report, valid
   for `REPORT_MEDIA_TTL_SECONDS` (default 15 minutes), minted only by the send path,
   only for a report the caller has just proved they own.

2. **`http://localhost:8080/report.pdf` cannot work.** `media_base_ok()` rejects a
   loopback or `.local` host and the send is refused with "WhatsApp delivery is not
   configured" — instead of an opaque Twilio media error minutes into a demo.

What the endpoint deliberately does *not* do: serve a directory, accept a path, accept a
filename, or expose anything reachable by guessing. `{scan_id}` is reduced to
`[A-Za-z0-9_-]` before use — `..`, `/` and `\` do not survive — and the file path is then
built by the store, so it is inside the media directory by construction. Wrong token,
missing token, expired token and a token minted for a different report all return the
same `404`, as does an unauthorised fetch: a different answer would confirm that a report
exists.

**The honest limitation:** anyone holding the signed URL within its lifetime can fetch
that one PDF. That is inherent to "a third party must fetch the media", and is the same
trade every signed object-storage URL makes. It is bounded to one report, to a few
minutes, and to a URL that only ever existed inside a Twilio API call.

Responses carry `Cache-Control: no-store`, `X-Robots-Tag: noindex` and
`X-Content-Type-Options: nosniff`.

---

## 4. Meta WhatsApp Cloud API setup (the demo provider)

Set `WHATSAPP_PROVIDER=meta`. This is the provider to use for the SIH demo, because
**Meta's free tier sends PDF documents and a Twilio trial cannot** (see §5).

### Console steps

1. **developers.facebook.com → My Apps → Create App → "Business".**
2. In the new app, **Add product → WhatsApp → Set up.** Meta creates a test business
   phone number and a WhatsApp Business Account for you. No payment method, no
   number purchase, no business verification is needed to send to test recipients.
3. Open **WhatsApp → API Setup**. That one screen has everything:
   - **Phone number ID** → `META_WHATSAPP_PHONE_NUMBER_ID`.
     It is the *numeric id* under the "From" number, **not** the phone number.
     Pasting the number here is the commonest setup mistake, so the API refuses it
     by name at startup rather than letting Graph answer with something unrelated.
   - **WhatsApp Business Account ID** → `META_WHATSAPP_BUSINESS_ACCOUNT_ID`
     (not needed to send; recorded because it sits next to the number id and the two
     are easy to confuse).
   - **Temporary access token** → `META_WHATSAPP_ACCESS_TOKEN`.
4. **Add the patient's number as a recipient.** Same screen, the **"To"** field →
   *Manage phone number list* → add the number → confirm the code sent to that phone.
   While the app is in test mode, only numbers on this list can be messaged; anything
   else is refused with code `131030`, which the UI renders as
   *"This number is not on the WhatsApp test recipient list yet."*
5. **Open the 24-hour window.** From that phone, send any WhatsApp message *to* the
   test business number. Free-form document messages are only allowed inside the
   24 hours following a message from the patient; outside it Meta answers `131047` and
   an approved template would be required.

> **The temporary token expires in 24 hours.** It is long enough to work in rehearsal
> and fail during the demo. Before presenting, generate a permanent one:
> **business.facebook.com → Business settings → Users → System users → Add**, assign
> the app with `whatsapp_business_messaging` **and** `whatsapp_business_management`,
> then *Generate new token* with no expiry. An expired token surfaces as code `190`,
> which the preflight names explicitly.

### Configuration

```bash
WHATSAPP_PROVIDER=meta
META_WHATSAPP_PHONE_NUMBER_ID=123456789012345
META_WHATSAPP_ACCESS_TOKEN=…            # backend only, never in web/
PUBLIC_BASE_URL=https://<your-tunnel>   # Meta fetches the PDF over the internet
```

### Preflight

```bash
make whatsapp-check                     # configuration only, sends nothing
make whatsapp-check TO=+91XXXXXXXXXX    # sends ONE real message
```

It checks the switch, the credentials, the numeric-id mistake, whether the media URL is
publicly fetchable, and whether Meta accepts the token — naming the expired-token case
(`190`) explicitly, because that is the failure most likely to appear on demo day.

---

## 5. Twilio setup

### Twilio Verify ≠ Twilio WhatsApp

They share an account and nothing else. **Working OTP tells you nothing about whether
WhatsApp will send.**

| | Twilio Verify (existing) | Twilio WhatsApp (new) |
|---|---|---|
| Purpose | OTP sign-in | report delivery |
| Host | `verify.twilio.com/v2` | `api.twilio.com/2010-04-01` |
| Resource | `Services/{VA…}/Verifications` | `Accounts/{AC…}/Messages.json` |
| Needs | a Verify Service SID | a WhatsApp sender + recipient opt-in |
| Recipient eligibility | Verify's verified-tester list | has joined the sandbox / 24h window |

### On a trial account (what we have)

A trial account cannot have an approved WhatsApp sender, so delivery goes through the
**Twilio WhatsApp Sandbox**:

1. **Twilio Console → Messaging → Try it out → Send a WhatsApp message.** Note the
   sandbox number (usually `+1 415 523 8886`) and the join code, e.g. `join amber-tiger`.
2. **Every recipient opts in themselves.** From the phone that will receive the report,
   send `join <your-code>` on WhatsApp to the sandbox number. Without this, Twilio
   answers error `63003` — there is no WhatsApp channel for that number — and the app
   shows "This number has not joined WhatsApp messaging from us yet."
3. **The 24-hour session window.** A freeform message with media is only permitted within
   24 hours of the recipient's last inbound message. Joining the sandbox starts that
   window; it resets each time they message the sandbox. Outside it, Twilio answers
   `63016` and a pre-approved template would be required. For a demo, have the recipient
   send any message to the sandbox shortly beforehand.
4. **Sandbox opt-ins expire** after roughly 72 hours of inactivity. Re-send `join <code>`.

Trial accounts also prefix outbound messages with a Twilio trial notice. That is a Twilio
behaviour and cannot be removed without upgrading.

### Making the API reachable

Local development — one command:

```bash
scripts/dev_tunnel.sh           # Cloudflare quick tunnel, no account needed
```

It starts the tunnel, writes `PUBLIC_BASE_URL=https://<id>.trycloudflare.com` into
`.env`, and holds the terminal. **Restart the API afterwards** — config is read at
import. The URL dies with the terminal, so a fresh run means a fresh URL and another
API restart. `ngrok http 8080` works equally well if you prefer it.

While that tunnel is up, every route on :8080 is reachable from the internet. The
report PDFs are not browsable because of it — `/v1/reports/media/{id}.pdf` still needs
an HMAC signature scoped to one scan id and expiring in `REPORT_MEDIA_TTL_SECONDS` —
but stop the tunnel when the demo is over.

Deployed: set `PUBLIC_BASE_URL` to the Cloud Run / Render URL. Nothing else changes.

### Trial accounts cannot send the PDF (verified 2026-09-16)

A Twilio **trial** account cannot deliver a PDF on WhatsApp by any route. Probed
directly against the live API, with the 24-hour session window confirmed OPEN:

| Attempt | Result |
|---|---|
| `MediaUrl` (any URL, ours or a public one) | 400, code `0` — "trial accounts have limited parameter access" |
| freeform `Body`, no template | 400, code `21654` — "ContentSid Required" |
| `ContentSid` pointing at another account's template | 400, code `21655` — "The ContentSid is Invalid" |
| Content API v1/v2 — create or list a template | 401, code `20003` — "not available on a Trial account" |
| Conversations API (the other media route) | 401, code `20003` |
| Verify API (control — proves the credentials are fine) | 200 |

Identical from the classic sandbox sender and the "Try out WhatsApp" sender, so it is an
**account-tier gate**, not a sender, opt-in or session-window problem. `MediaUrl` is
refused during parameter validation, before Twilio ever fetches the URL — so a perfect
media URL cannot help, and the tunnel is not the problem.

The one thing that works on a trial is the Console's own Tryout UI, which sends a
Twilio-provided template (visible in the logs as an `MM…` message). Its ContentSid is
not readable through the API on a trial, and that template has no media header, so it
could not carry the report anyway.

**The fix is Console → Billing → upgrade (add funds) to leave trial.** No code change is
needed afterwards: the send already posts `From`/`To`/`Body`/`MediaUrl`, which is the
supported path on a paid account. Confirm with `make whatsapp-check`.

### Configuration

```bash
WHATSAPP_MODE=live                       # or "disabled"
WHATSAPP_ENABLED=1
TWILIO_ACCOUNT_SID=AC…                   # same account as Verify
TWILIO_AUTH_TOKEN=…                      # same token as Verify
TWILIO_WHATSAPP_FROM=whatsapp:+1XXXXXXXXXX  # YOUR sender — see below
PUBLIC_BASE_URL=https://<your-public-host>
REPORT_MEDIA_TTL_SECONDS=900
STORE_REPORT_PDF=1
WHATSAPP_RESEND_COOLDOWN_SECONDS=60
```

All of it is backend-only. None of these names appears in `web/`, nothing reaches the
browser, and `/health` reports only *whether* delivery would work — never a SID, a token,
a sender number or a URL.

There is deliberately **no mode that reports a fake success.** `WHATSAPP_MODE=disabled`
makes no Twilio call and the UI says delivery is unavailable.

### Preflight

```bash
make whatsapp-check                    # checks configuration, sends nothing
make whatsapp-check TO=+91XXXXXXXXXX   # sends ONE real message
```

This talks to Twilio directly, so it separates "is the channel configured" from "is the
app wired up".

---

## 6. API

### `POST /v1/reports/{scan_id}/whatsapp`

Authenticated (any signed-in account). Request:

```json
{ "language": "hi" }
```

`language` is a presentation preference, allow-listed to `en|hi|te|pa`, defaulting to
English. **There is no recipient field**, and adding one changes nothing: the number is
read from the authenticated session, so a caller has nowhere to put a number of their
choosing.

Success (`200`):

```json
{ "success": true, "channel": "whatsapp", "message": "Report sent successfully",
  "to_masked": "+91 ***** 40001", "sent_at": "2026-09-16T09:05:00Z", "duplicate": false }
```

Failure carries the same shape with `success: false` and a stable `code` the frontend
maps to a translated sentence:

| code | HTTP | meaning |
|---|---|---|
| `not_configured` / `provider_unconfigured` / `sender_not_whatsapp` | 503 | operator configuration |
| `recipient_not_reachable` | 400 | the number has not joined WhatsApp messaging from us |
| `session_window_closed` | 409 | outside the 24-hour freeform window |
| `invalid_recipient`, `recipient_opted_out` | 400 | the number cannot or will not receive |
| `rate_limited` | 429 | Twilio throttling |
| `media_unreachable` | 502 | Twilio could not fetch the PDF |
| `provider_unreachable` / `provider_error` | 502 | network, timeout, or an unmapped Twilio error |
| `report_not_ready` | 409 | the retained PDF is gone |
| `already_sending` | 409 | a send for this report is in flight |
| `report_not_found` | 404 | no such report, **or** not the caller's — deliberately identical |

Raw Twilio messages, error URLs and exception text never reach the client. The numeric
Twilio code is logged server-side, because it is what makes a failed demo debuggable and
it is not sensitive.

### `GET /v1/reports/media/{scan_id}.pdf?token=…`

Unauthenticated by necessity, capability-scoped by design. Twilio is the caller. Excluded
from the OpenAPI schema.

---

## 7. Duplicate sends

Three layers, none of them a messaging system:

1. **Frontend in-flight lock** — a ref checked inside the click handler, so it is correct
   before React re-renders. A triple tap issues one request.
2. **Backend in-flight set** — one send at a time per report, per process.
3. **Delivery record + cooldown** — a second request within
   `WHATSAPP_RESEND_COOLDOWN_SECONDS` returns the *first* delivery, truthfully marked
   `duplicate: true`. No second Twilio call, and no false claim that something new was
   sent. This one survives a restart, because it reads the record on disk.

---

## 8. Privacy and safety

- Twilio credentials are backend-only; they are never logged, returned or sent to the
  browser.
- The recipient is logged **masked** (`+91 ***** 40001`). The full number appears in no
  log line.
- The message body is never logged — it contains a clinical result.
- The delivery record stores the masked number only; the full one stays in the account
  record, where it already was.
- `patient_ref` is not copied into the delivery metadata, so a name typed there cannot
  reach WhatsApp.
- The disclaimer is the last line of every message, in every language.
- The AI result is never described as a diagnosis.

**On WhatsApp itself:** messages are end-to-end encrypted in transit, but this sends a
clinical document to a consumer messaging platform, at the patient's own request, to
their own number. For a production deployment that is a consent and data-governance
decision — not a purely technical one — and should be recorded as such.

---

## 9. Tests

`tests/test_whatsapp_delivery.py` (49 tests) and `web/tests/whatsapp.test.tsx`
(24 tests). **No test sends a real WhatsApp message**: Twilio is replaced by a callable
that records what it was asked to do, and `fetch` is stubbed in the frontend suite.

Covered: authenticated send, unauthenticated rejection, ownership enforcement, missing
report, missing configuration, localhost refusal, disabled mode, eight distinct Twilio
failures, network failure, accepted-then-failed, duplicate protection, cooldown expiry,
path traversal, token scope and expiry, all four message languages, the disclaimer, and
that no secret or patient identifier appears in any response.
