# PODX AI CONNECT V2 — Pre-Live Test Matrix

Use this sequence after all production modules are merged. Start with `/health`, then `/readiness`, then run the WhatsApp flows below with fresh test users wherever possible.

## Gate 0 — Infrastructure
- `/health` returns healthy and database is available.
- `/readiness` returns `live_test_ready: true` before live WhatsApp testing.
- PODX platform-side charge remains ₹0 and no payment gateway is required for testing.
- Optional provider warnings (voice/image/maps) may degrade only those features; they must not break text flows.

## Gate 1 — Registration and roles
1. New user sends `Hi`.
2. Complete name/profile and select one role.
3. Re-enter and add/operate a second role where supported.
4. Share location and verify it is persisted.
5. Confirm stale/incomplete sessions can recover to the main menu.

## Gate 2 — Jobs
1. Worker registers category, experience, availability and location.
2. Employer posts a job and location.
3. Verify nearby matching and targeted notification.
4. Employer confirms worker; contact exchange is privacy-safe before confirmation and available after confirmation.
5. Verify location/contact fallback for low-literacy flow.

## Gate 3 — Products / catalogs / demand
1. Seller adds catalog by text.
2. Upload product price-list image/PDF and confirm extracted items.
3. Buyer searches an existing product and receives relevant local offers.
4. Search unavailable product; verify demand capture/admin visibility.
5. Update price/stock and verify eligible buyer re-engagement path.

## Gate 4 — Appointments
1. Customer requests appointment naturally.
2. Provider receives request and accepts/rejects.
3. Customer confirms.
4. Reschedule and cancel paths.
5. Completion and privacy-safe contact exchange.

## Gate 5 — Ride sharing
1. Driver KYC submit → review → approve; verify expiry/renewal status paths.
2. Driver posts ride.
3. Passenger searches route and requests seat.
4. Driver accepts/rejects; seat count updates correctly.
5. Accepted booking unlocks contact with PODX charge ₹0 and no payment step.
6. Maps route enrichment works when configured and fallback works when not configured.
7. Driver records final commercial fare; passenger confirms; `RIDE DONE` is non-blocking.

## Gate 6 — Bike / parcel
1. Customer creates bike/parcel request.
2. Fare estimate and customer confirmation.
3. Rider assignment and privacy-safe contact unlock.
4. Verify PODX platform payment does not block testing.

## Gate 7 — RFQ / events / catering
1. Natural function/event requirement creates master RFQ.
2. Catering/hall/decoration/etc. sub-requirements are extracted.
3. Relevant providers only are targeted from common catalog.
4. Provider quotation → comparison → selection → combined booking summary.
5. Retry does not duplicate provider targets.

## Gate 8 — Business ledger
1. Add receivable/payable using natural Telugu/English.
2. Record received/paid amount.
3. Verify balance and statement.
4. Ensure ledger intent does not route into unrelated modules.

## Gate 9 — Creator / Meet / Customer Desk / alerts
1. Creator attribution/promo-code path.
2. PODX Meet create → discover → join/leave → cancel.
3. Business Customer Desk FAQ/RAG response and unresolved escalation.
4. `ALERTS ON`, `ALERTS OFF`, `ALERTS STATUS`.

## Gate 10 — Voice / media / reliability
1. Voice note: immediate acknowledgement, then text response and voice response when TTS enabled.
2. Image and PDF processing.
3. Location message handling.
4. Force/observe media processing failure: user receives recovery instruction rather than silence.
5. Replay the same Meta message ID: verify one business action / one processing.
6. Check `ADMIN STATUS`, unresolved, KYC, deliveries and RFQ queues.

## Exit criteria
PODX is test-complete only when all critical text flows pass, no payment gate blocks a PODX-owned feature, privacy boundaries hold, duplicate/retry behavior is safe, and any optional-provider degradation produces a clear fallback rather than a dead conversation.
