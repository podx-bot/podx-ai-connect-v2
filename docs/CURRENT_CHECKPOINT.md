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

## Real-time unresolved demand handling — mandatory

The platform's main motive is not just to search a catalog; it is to connect two people whose needs can satisfy each other, even when the exact item/service/job is not already listed.

When a direct match is not found:
- Keep the NEED or OFFER active instead of ending the conversation.
- Identify related registered users by semantic category/subject, capability/profile, geography and other constraints even if they have not explicitly listed the exact item in advance.
- Send a lightweight targeted request to the relevant opposite-side users asking whether they can fulfill the need/offer.
- Do not blast everyone; rank and widen progressively by relevance and radius.
- Maintain live status such as: request active, candidates found, notifications sent, interested responses, nearest distance and last update time.
- Tell the requester simple status updates such as: no direct match yet, N relevant people were contacted, X responded, nearest match is Y km away.
- If nobody responds, keep the request on hold and continue matching when new users/offers appear.
- New registrations or newly added offers should be checked against active opposite-side needs so old requests can be fulfilled later.
- When an opposite party says interested/can provide/can do the work, confirm consent and connect both registered parties; share contact details only at the appropriate consent step.
- This real-time hold → target → notify → respond → connect loop is the core scalable behavior for millions of users and requests.
- Performance goal: when relevant supply exists, aim for seconds-to-minutes perceived resolution; do not promise a fixed time when no supply exists.

## Mandatory image-first capability

Image-based understanding/search is a first-class input path, not an optional later feature.

- A buyer can send a product photo, screenshot, cropped image, label, packaging image, catalogue image, or menu image instead of knowing the product name.
- A seller can send one or more product photos and PODX should create/attach an OFFER record with the visual evidence plus any extracted/declared price, quantity, brand/model and location.
- The same image path must work for services/work examples where an image helps identify the requirement.
- Image understanding should normalize into the same Universal Need ↔ Offer structure used by text/voice, so text, voice and image all enter one matching engine.
- Preserve the original image reference plus derived metadata/features for future visual similarity search.
- If exact identification is uncertain, ask one short clarification instead of forcing menus.
- For matching, support semantic text similarity plus visual similarity when image features are available.
- Results may include the seller/provider image so the opposite party can confirm visually before contact exchange.
- PODX may generate a lightweight presentation image/card when useful for a user-facing result/menu/catalog, but generation must never block the first text result.

### Image performance requirements

- Fast path first: acknowledge receipt immediately, then process image asynchronously where possible.
- Do not ZIP ordinary images just for speed; ZIP normally adds packaging overhead and does not materially reduce already-compressed JPEG/WebP images.
- Prefer direct media download/upload, bounded dimensions, thumbnails/previews, WebP/JPEG optimization, cached media references and object/media storage rather than repeated re-downloads.
- Keep the original only when needed; create a small normalized analysis copy and a tiny preview for fast WhatsApp/UI use.
- Avoid base64 in hot paths except where an API strictly requires it.
- Reuse downloaded bytes during the same request pipeline; do not download the same WhatsApp media multiple times.
- Return text/search result first when available; send richer image/card result immediately after if generation/rendering takes longer.
- Design for seconds-level end-to-end perception, with image analysis and visual search measured separately from network/media transfer.

## AI stack to preserve

- Voice STT primary: Sarvam Saaras v3.
- Voice STT fallback: Gemini.
- Meaning extraction/reasoning: Gemini (current fast model), but replace rules-heavy intent routing as the primary architecture with a single universal structured extractor.
- Image understanding: multimodal AI path feeding the same universal extractor/record schema.
- Keep current fast WhatsApp text + voice delivery and Sarvam Opus TTS path intact.

## Latest live status

- Worker natural voice flow and location save are working.
- Employer job creation and location save are working.
- Live nearby matching test created Job #3 but returned 0 matches / 0 notifications despite a recently registered nearby Delivery worker. This exposed both a matching issue and the larger architectural problem of too many workflow states.
- PR #62 and PR #64 fixed repeated worker-category menu replay paths.
- Reliability suite after PR #64: 125 tests passing.
- Universal Flow V1 extractor foundation has started via Issue #65 / PR #66.

## Next development milestone — Universal Flow V1

Build as complete modules, not patches:
1. UniversalRequestExtractor — one AI call returns normalized NEED/OFFER structure from arbitrary natural language.
2. UniversalDemandRepository — persist universal requests/offers independently of old job/product/service tables, including active/hold lifecycle.
3. UniversalMatcher — find opposite-side matches using subject similarity + location + time + quantity + price/constraints.
4. UniversalTargetingService — find related registered users even when the exact item/service is not explicitly listed, with progressive relevance/radius widening.
5. UniversalConversationService — ask only missing fields; no forced menus.
6. Match → Hold → Target → Notify → Interest → Consent → Contact exchange.
7. UniversalImageInput — ingest WhatsApp image/screenshot/crop, create fast normalized preview, run multimodal understanding, attach visual metadata/reference to universal record and enable visual similarity hooks.
8. Live request status — counts contacted/responded, nearest distance, request age/last update, and simple WhatsApp status messages.
9. Wire text, transcribed voice and image into the same path for registered users while keeping old flows as temporary fallback.
10. Add end-to-end tests for unrelated examples, mixed Telugu/English, unknown professions/products, image-only product requests/offers, unresolved demand broadcast and Party A ↔ Party B matching.
11. Railway deploy → WhatsApp live test.

## Today’s target result

On WhatsApp, natural messages such as a work need, worker need, product need, product offer, service need, or an image-only product request/offer should be understood without a menu, ask only the missing field (typically location), then create a universal record. If a direct match is absent, keep it active, target related opposite-side users, send requests, report simple live status and connect the two parties as soon as someone responds with interest.
