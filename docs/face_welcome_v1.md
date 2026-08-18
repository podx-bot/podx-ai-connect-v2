# Face Welcome V1

Face Welcome is an optional business feature, not a mandatory part of Universal Profile registration.

## Enrollment contract

1. Ask the customer whether they want Face Welcome enabled for future visits.
2. Continue only after explicit consent.
3. Capture the face at the business enrollment point and convert it to a biometric template using the configured recognition provider.
4. Store only the template reference in the PODX Face Welcome profile contract; raw customer photos are outside this contract.
5. Mark the profile as `ENROLLED` only when consent is active and a template exists.
6. A camera match may trigger a greeting only for an enrolled, consent-active profile.
7. The customer can disable Face Welcome. Disabling revokes matching and removes the template reference from the active profile.

## Profile states

- `NOT_ENROLLED`
- `ENROLLED`
- `DISABLED`

## Registration boundary

Universal registration must not require a face photo. Face Welcome enrollment happens later, when the feature is actually used at a participating business.
