# PODX Universal Conversation Contract V1

## Purpose

PODX must be verified as one universal conversational system, not as a collection of product-specific patches. A production release is allowed only when the full lifecycle contract is green across domains and channels.

## Fixed processing contract

Every customer turn must pass through the same conceptual chain:

1. Understand the current user intent.
2. Load durable previous conversation context.
3. Merge updates/corrections without losing known facts.
4. Validate missing/conflicting information.
5. Decide the business action (match, ask, notify, cancel, answer, wait, escalate).
6. Produce a customer-facing response with no internal implementation vocabulary.
7. Prevent duplicate, stale or regressive status messages.
8. Persist the resulting state so the next turn resumes correctly.

No domain runtime may bypass these behavioural guarantees.

## Mandatory release scenario families

The same scenario families must be exercised for Product, Service, Job, Ride and future domains:

- new request
- follow-up update
- question/doubt
- correction
- complaint
- cancellation
- no match
- match found
- counterparty rejection
- timeout
- duplicate inbound webhook
- late/stale event
- restart and resume
- Telugu / English / mixed language
- text / voice semantic equivalence
- internal implementation language never reaches customers

## Release blockers

A build is not production-ready if any of these happen:

- empty customer reply
- internal state/runtime vocabulary appears in a customer reply
- identical pending/waiting status repeats without new information
- an unchanged request moves backwards from a concrete match to generic waiting
- an update is treated as unrelated while durable context exists
- cancellation, correction, complaint or question is routed as an unrelated new request
- deploy/restart loses the active conversation state

## Deployment rule

Do not deploy because a single reproduced symptom is fixed. Merge/deploy only after the universal contract suite and the repository reliability suite are green. Production WhatsApp testing is the final verification layer, not the first place where conversation rules are discovered.
