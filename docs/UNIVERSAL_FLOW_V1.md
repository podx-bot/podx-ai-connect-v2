# PODX Universal Flow V1

## Goal

Replace menu-heavy primary routing with a universal Party A ↔ Party B model.

Every natural-language message should become one normalized request record with these fields:

- `side`: `NEED` or `OFFER`
- `domain`: `WORK`, `WORKERS`, `SERVICE`, `PRODUCT`, or `OTHER`
- `subject`: normalized free-form thing being needed/offered
- `quantity`: optional numeric quantity
- `unit`: optional quantity unit
- `price`: optional offered/target price
- `currency`: defaults to INR when clearly local and a rupee value is present
- `when_text`: optional free-form time/availability
- `location_text`: optional place mentioned in speech/text
- `location_required`: whether GPS/location is still needed for matching
- `constraints`: optional free-form constraints
- `confidence`: extraction confidence
- `source_text`: original user message

## Matching contract

A match is an opposite-side record with compatible domain/subject and acceptable constraints. Ranking should use:

1. semantic subject relevance
2. geographic distance
3. time/availability overlap
4. quantity compatibility
5. price/budget compatibility
6. freshness

Exact category equality must not be required.

## Conversation contract

- Do not force a menu if the message is understandable.
- Ask only one genuinely missing essential field at a time.
- Location is normally the first missing field for local matching.
- If a direct match exists, show/notify it.
- If no direct match exists, save the demand/offer and notify likely opposite-side candidates.
- Contact details are shared only after interest/consent.

## Compatibility

The current Sarvam STT, Gemini fallback STT, WhatsApp text delivery, and Sarvam Opus voice reply path remain unchanged. Old job/service/product flows remain temporary fallback until Universal Flow V1 reaches live parity.
