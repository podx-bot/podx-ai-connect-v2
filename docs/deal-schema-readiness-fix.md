# Universal deal schema readiness

This fix prevents product-specific schema noise from blocking live PODX deal completion.

- A standalone quoted price is treated as a lump-sum/whole-deal price unless a per-unit rate is explicitly stated.
- Quantity is therefore not forced when neither side supplied a quantity and the seller quoted a total price.
- Per-unit rates still require quantity when the schema marks quantity as required.
- AI-generated test/debug/internal/temp/mock/sample/placeholder fields are rejected before they can reach seller prompts or missing-field checks.
- Product schema prompts now distinguish transaction units from specification units.

The behavior is product-agnostic and covered by regression tests, including a TV-like offer matching the live WhatsApp failure.