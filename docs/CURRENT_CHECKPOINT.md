# PODX AI CONNECT — Current Checkpoint

Date: 2026-08-14

## Direction locked

PODX will move away from menu-heavy, category-first workflows and toward a Universal Need ↔ Offer engine.

Core principle:
- Any user can speak/type naturally in any supported language or local phrasing.
- AI should understand meaning, not depend on fixed examples or a fixed 1–9 category menu.
- Every request is normalized into a universal structure such as:
  - side: NEED or OFFER
  - domain: WORK / WORKERS / SERVICE / PRODUCT / OTHER
  - subject: free-form normalized item/skill/service/product
  - quantity
  - price/budget
  - when/availability
  - location or location_required
  - optional constraints
- Ask only for genuinely missing information, usually location or one essential field.
- Match Party A ↔ Party B using semantic relevance + distance + time + quantity + price/constraints.
- If a direct match exists, return/notify it immediately.
- If no direct match exists, notify relevant opposite-side users and keep the demand active.
- On mutual interest/consent, share registered contact details between the two parties.
- This same engine must cover jobs/workers, services/providers, products/buyers/sellers, and future categories without new hard-coded flows.

## AI stack to preserve

- Voice STT primary: Sarvam Saaras v3.
- Voice STT fallback: Gemini.
- Meaning extraction/reasoning: Gemini (current fast model), but replace rules-heavy intent routing as the primary architecture with a single universal structured extractor.
- Keep current fast WhatsApp text + voice delivery and Sarvam Opus TTS path intact.

## Latest live status

- Worker natural voice flow and location save are working.
- Employer job creation and location save are working.
- Live nearby matching test created Job #3 but returned 0 matches / 0 notifications despite a recently registered nearby Delivery worker. This exposed both a matching issue and the larger architectural problem of too many workflow states.
- PR #62 and PR #64 fixed repeated worker-category menu replay paths.
- Reliability suite after PR #64: 125 tests passing.

## Next development milestone — Universal Flow V1

Build as complete modules, not patches:
1. UniversalRequestExtractor — one AI call returns normalized NEED/OFFER structure from arbitrary natural language.
2. UniversalDemandRepository — persist universal requests/offers independently of old job/product/service tables.
3. UniversalMatcher — find opposite-side matches using subject similarity + location + time + quantity + price/constraints.
4. UniversalConversationService — ask only missing fields; no forced menus.
5. Match → Notify → Interest → Consent → Contact exchange.
6. Wire text and transcribed voice into this path for registered users while keeping old flows as temporary fallback.
7. Add end-to-end tests for unrelated examples, mixed Telugu/English, unknown professions/products, and Party A ↔ Party B matching.
8. Railway deploy → WhatsApp live test.

## Today’s target result

On WhatsApp, natural messages such as a work need, worker need, product need, product offer, or service need should be understood without a menu, ask only the missing field (typically location), then create a universal record and match/notify the opposite party.
