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
5. After seller Confirm, BUYER — never seller — receives two choices:
   - Order Continue
   - Direct Talk
6. Order Continue: buyer supplies/selects delivery address and order details; PODX sends seller a qualified order/lead summary.
7. Direct Talk: contact details may be exchanged according to consent/privacy rules.

Rules:
- Interest = Buyer action.
- Availability confirmation = Seller action.
- Delivery address = Buyer data.
- Qualified order summary = Seller receives it.
- Internal IDs/commands such as INTERESTED 5 / CONFIRM 5 must remain hidden behind WhatsApp buttons.

## Seller comfort / AI Product Desk
Seller comfort is a primary design requirement because a seller may handle many buyers.
- PODX should answer repetitive product questions on the seller's behalf.
- Build a Smart Product Profile/FAQ from seller-confirmed listing data and safe product information.
- Typical fields: price, quantity/size, features, usage, availability, variants, delivery, warranty/return where applicable.
- If PODX knows the seller-confirmed answer, answer the buyer automatically without disturbing seller.
- If information is unknown, ask seller one short question, return the answer to buyer, and save the confirmed answer for future FAQs.
- Never invent/guess seller-specific price, stock, warranty, return or delivery promises.

## Standard addresses
Seller:
- Standard Business/Pickup Address.
- Shop/business name optional.
- Map location.
- Delivery available/not available.
- Delivery radius.
- Later support multiple branches/addresses.

Buyer:
- Saved Delivery Address collected during first relevant order.
- Home / Work / Other labels.
- Reuse saved address on future orders with Change Address option.

Privacy:
- Do not expose full addresses at initial matching stage.
- Reveal only when required by confirmed order/delivery workflow.

## Local Instant Delivery / Dispatch Engine
Reusable common engine for products, food, parcels and later ride/taxi-like flows.

Buyer delivery choices can include:
- Pickup
- Normal Delivery
- Instant Delivery

Instant Delivery flow:
1. Confirmed order has seller pickup location and buyer drop location.
2. Find/rank nearby registered delivery partners.
3. Send a compact delivery job card with pickup area, drop area, distance and delivery fee where available.
4. Delivery partners get Accept / Decline buttons.
5. First valid Accept atomically locks the delivery task to that partner; all other offers close to prevent duplicate pickup.
6. Share seller pickup location with assigned partner.
7. Share buyer drop details only at the appropriate delivery stage.
8. Track statuses such as ACCEPTED -> PICKED_UP -> ON_THE_WAY -> DELIVERED.
9. Automatically update buyer and seller through WhatsApp.

Common core for future verticals:
Location -> Nearby provider -> Accept -> Atomic task lock -> Controlled location sharing -> Status tracking -> Complete.

## Smart Grocery RFQ / Local Quote Engine
Purpose: digitize the common local grocery/kirana paper-list quotation process and turn it into a buyer-side competitive quotation workflow.

Flow:
1. Buyer sends a handwritten/printed grocery shopping-list photo or text list.
2. PODX converts it into a structured digital list with item, quantity and unit, then asks buyer to confirm/correct the list.
3. After confirmation, PODX targets only relevant nearby registered grocery/kirana sellers and sends the RFQ/list.
4. Each seller gets a simple quotation form/list with a rate field beside each item and an option to mark an item Not Available.
5. PODX automatically calculates each seller's basket total, item coverage and other comparison signals.
6. Do not dump every quotation on the buyer. Rank/filter and normally show Top 3 or Top 5 useful choices.
7. Ranking should not use cheapest price alone. Consider total price, full item availability, seller rating, distance, delivery availability/cost and seller response/reliability.
8. Buyer presentation can highlight:
   - Best Value
   - Lowest Price
   - Compare Top Sellers
9. Buyer selects a seller; only then send that seller the selected-order confirmation/Confirm Order step.
10. Selected order can continue into the existing PODX order/address/delivery flow, including future Normal or Instant Delivery.

Optional Split Basket optimization:
- If no single seller is best for the full list, PODX may calculate a combination across sellers.
- Recommend split ordering only when the real saving remains meaningful after delivery charges and inconvenience are considered.

Seller privacy/competition rules:
- Do not reveal competitor identities or individual competitor quotations to sellers.
- Limited feedback such as 'your quotation can be more competitive' may be used without exposing another seller's private pricing.
- Goal is a fair competitive quote process while protecting seller business data.

Reusable verticals:
The same RFQ engine can later support groceries/kirana, building materials, electricals, hardware, restaurant/raw-material supplies and other list-based local purchasing categories.

## Payments — parked for later
Future concept only; do not implement now:
- Optional PODX Secure Payment / Buyer Protection.
- Buyer/seller may opt into protected transaction.
- Settlement after delivery/acceptance/protection window subject to compliant regulated payment infrastructure.
- Security/protection users can be charged a commission/service fee.
- Do not design PODX to unofficially hold customer funds in its own account.

## Immediate development order
1. Fix buyer/seller reverse-role mapping in Lead Conversion V1.
2. Live test: Buyer Interest -> Seller Confirm -> Buyer Order Continue/Direct Talk.
3. Add buyer saved delivery address + seller standard pickup/business address architecture.
4. Add Qualified Lead/Order card to seller.
5. Build AI Product FAQ / Seller Assistant V1.
6. Build Local Dispatch Engine V1 after core commerce conversion is stable.
7. Build Smart Grocery RFQ / Local Quote Engine after core order and seller flows are stable.
8. Payments remain parked until explicitly resumed.
