# PODX Conversation OS V1

## Core invariant
PODX must never interpret a user turn in isolation. Every decision is based on:

`previous PODX turn + expected reply + current user turn + active goal/state + pending action`.

## Pipeline
1. Normalize text/voice/image input.
2. Load persistent ConversationState.
3. ConversationKernel resolves turn kind and meaning.
4. Merge only newly supplied fields into active state.
5. Route the planned action to the appropriate commerce/service tool.
6. Response planner creates a concise natural reply.
7. Response guard checks contradictions, repeats, unsupported facts and empty output.
8. Persist the complete turn ledger.

## Turn kinds
- NEW_REQUEST
- UPDATE_EXISTING
- CLARIFICATION
- QUESTION
- CONFIRMATION
- CANCELLATION
- NEW_TOPIC
- UNKNOWN

## State contract
The state must be channel-neutral and reusable by WhatsApp, app and web. It carries goal, active flow/entity, known fields, missing fields, pending action, previous PODX message/intent, expected reply type and latest user turn.

## Testing contract
Every production conversation bug becomes a golden regression conversation. Live WhatsApp verification happens only after automated conversation simulations pass. The first locked regression is: `10 kg chicken కావాలి → బోన్లెస్ కావాలి`, where the second turn updates the active request and preserves quantity/intent/context.
