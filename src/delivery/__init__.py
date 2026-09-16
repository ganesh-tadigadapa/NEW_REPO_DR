"""CareBridge delivery — getting an already-finished report to the patient.

Nothing in this package analyses, grades, explains or decides anything. It takes the
report the screening pipeline has ALREADY produced and moves it to a channel the patient
already has. The screening result is the single source of truth; this layer is a
courier.

    src/api/pipeline.py   ->  the result and the PDF          (untouched)
    src/delivery/media    ->  keeps that exact PDF, and who it belongs to
    src/delivery/message  ->  words built from that result, in the patient's language
    src/delivery/whatsapp ->  one Twilio WhatsApp call
    src/delivery/routes   ->  the authenticated endpoint

If this whole package were deleted, every clinical behaviour in the service would be
byte-for-byte what it is today.
"""
