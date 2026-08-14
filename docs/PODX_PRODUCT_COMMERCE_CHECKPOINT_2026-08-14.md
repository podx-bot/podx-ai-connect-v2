# PODX AI CONNECT — Product Commerce Checkpoint

Date: 2026-08-14

## Current live status
- Image product recognition works.
- NEED/OFFER matching works.
- WhatsApp outbound match notification works.
- Interactive Interested / Not Interested buttons work.
- Live testing exposed a buyer/seller role-direction reversal in the new lead-conversion flow; this must be fixed before marking the sprint complete.

## Locked buyer/seller conversion flow
1. Buyer expresses NEED / interest in a product.
2. Seller has the matching OFFER/product.
3. Buyer presses Interested.
4. Seller receives availability confirmation and presses Confirm (or Decline).
5. After seller Confirm, BUYER — never seller — receives two choices: Order Continue or Direct Talk.
6. Order Continue: buyer supplies/selects delivery address and order details; PODX sends seller a qualified order/lead summary.
7. Direct Talk: contact details may be exchanged according to consent/privacy rules.

Rules: Interest = Buyer action. Availability confirmation = Seller action. Delivery address = Buyer data. Qualified order summary = Seller receives it. Internal IDs/commands remain hidden behind WhatsApp buttons.

## Seller comfort / AI Product Desk
Seller comfort is a primary design requirement because a seller may handle many buyers. PODX should answer repetitive product questions on the seller's behalf using a Smart Product Profile/FAQ. Seller-confirmed information has priority. Never invent seller-specific price, stock, warranty, return or delivery promises. Unknown questions can be escalated once to the seller and the confirmed answer saved for future use.

## Standard addresses
Seller: Standard Business/Pickup Address, optional shop name, map location, delivery availability/radius, later multiple branches.
Buyer: Saved Delivery Address with Home/Work/Other labels and Change Address option.
Privacy: do not expose full addresses during initial matching; reveal only when required by confirmed order/delivery workflow.

## Local Instant Delivery / Dispatch Engine
Reusable engine for products, food, parcels and later ride/taxi-like flows. Buyer can choose Pickup, Normal Delivery or Instant Delivery. For Instant Delivery, rank nearby registered delivery partners, send Accept/Decline job cards, atomically lock the task to the first valid acceptance, then share pickup/drop details only at the required stages and track ACCEPTED -> PICKED_UP -> ON_THE_WAY -> DELIVERED.

Common core: Location -> Nearby provider -> Accept -> Atomic task lock -> Controlled location sharing -> Status tracking -> Complete.

## Smart Grocery RFQ / Local Quote Engine
Buyer sends a handwritten/printed grocery list photo or text. PODX structures and confirms the list, sends it to relevant nearby grocery/kirana sellers, collects per-item rates/availability, calculates basket totals and ranks useful Top 3/Top 5 choices. Ranking considers total price, item coverage, rating, distance, delivery and reliability, not price alone. Buyer can see Best Value, Lowest Price or Compare Top Sellers. Seller competitor identities/private quotations are not exposed. Optional Split Basket may be recommended only when savings remain meaningful after delivery costs/inconvenience. Reusable for groceries, building materials, electricals, hardware, restaurant/raw-material supplies and other list-based purchasing.

## Zero-Touch Face Welcome / Visit Session
Future in-store premium feature, opt-in only.
- Goal: customer should not need to open phone, QR or scanner merely to be recognized when entering/leaving a participating store.
- Customer profile may include optional Face Welcome enrollment and preferred language.
- Face recognition is identification only, never authorization for payment, address/contact disclosure or other sensitive actions.
- Store-facing data must be minimized; do not expose phone, address, purchase history or full PODX profile merely because a face matched.
- Personalized public speaker announcements are not desired. Personalized welcome/thank-you should go privately to the recognized customer's mobile/WhatsApp, subject to applicable messaging consent/template rules.
- Visit state prevents repeated greetings: ENTRY -> Welcome once -> ACTIVE VISIT -> EXIT -> Thank You once -> SESSION CLOSED.
- If Face Welcome is OFF, recognition/greeting must not occur. Provide deletion/revocation controls and QR/WhatsApp fallback where appropriate.

## PODX In-Store AI Salesman / Visual Shopping Assistant
Premium-store assistant that starts after an opted-in customer is recognized/enters a store.
- Customer receives a private personalized welcome on their mobile.
- Customer can use phone camera + text/voice to show a product and ask questions.
- Vision can identify/understand the product; store-confirmed catalog data supplies current price, stock, offers, variants and store location/aisle/floor.
- PODX can explain features, compare products, shortlist products by budget/need, answer FAQs and guide the customer to the product location like a salesperson.
- Never guess live price, stock, discounts or aisle/location from vision alone; these must come from seller/store-confirmed data.
- Desired experience: Zero-Touch Welcome -> AI Shopping Assistant -> Zero-Touch Thank You -> Session Closed.
- Potential verticals include supermarkets, electronics, clothing, jewellery, furniture and malls.

## Payments — parked for later
Future concept only: optional PODX Secure Payment / Buyer Protection using compliant regulated payment infrastructure. Do not design PODX to unofficially hold customer funds in its own account.

## Immediate development order
1. Fix buyer/seller reverse-role mapping in Lead Conversion V1.
2. Live test: Buyer Interest -> Seller Confirm -> Buyer Order Continue/Direct Talk.
3. Add buyer saved delivery address + seller standard pickup/business address architecture.
4. Add Qualified Lead/Order card to seller.
5. Build AI Product FAQ / Seller Assistant V1.
6. Build Local Dispatch Engine V1 after core commerce conversion is stable.
7. Build Smart Grocery RFQ / Local Quote Engine after core order and seller flows are stable.
8. Later: Zero-Touch Face Welcome + In-Store AI Salesman/Visual Shopping Assistant.
9. Payments remain parked until explicitly resumed.
