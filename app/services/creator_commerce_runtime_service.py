"""WhatsApp runtime for seller-authorized creator product promotions."""
from __future__ import annotations

import re


class CreatorCommerceRuntimeService:
    def __init__(self, repository, product_catalog, user_repository=None) -> None:
        self.repo = repository
        self.products = product_catalog
        self.users = user_repository

    def process(self, sender_user_id: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()
        if not lowered.startswith(("creator ", "promo ")):
            return None
        sender = str(sender_user_id)
        if self.users is not None:
            user = self.users.find_by_whatsapp_mobile(sender) or {}
            if int(user.get("registration_complete") or 0) != 1:
                return "ముందుగా PODX registration complete చేయండి."

        if lowered == "creator on":
            if self.users is not None and hasattr(self.users, "add_capability"):
                self.users.add_capability(sender, "CREATOR", source="CREATOR_COMMERCE")
            return "✅ Creator mode ON. Sellers మీకు product promotion campaigns assign చేయగలరు."

        create = re.fullmatch(r"(?i)PROMO CREATE\s+(\d+)\s*\|\s*([^|]+?)(?:\s*\|\s*(NONE|PERCENT|FIXED)(?:\s+([0-9]+(?:\.[0-9]+)?))?)?", clean)
        if create:
            product_id = int(create.group(1)); creator = create.group(2).strip()
            ctype = (create.group(3) or "NONE").upper(); cvalue = float(create.group(4)) if create.group(4) else None
            product = self.products.get(product_id)
            if not product or not int(product.get("active") or 0):
                return "Product దొరకలేదు లేదా inactiveగా ఉంది."
            if str(product.get("seller_user_id")) != sender:
                return "ఈ productకి seller owner మాత్రమే promotion campaign create చేయగలరు."
            if self.users is not None:
                creator_user = self.users.find_by_whatsapp_mobile(creator) or {}
                if not creator_user:
                    return "Creator PODX userగా దొరకలేదు."
            if ctype in {"PERCENT", "FIXED"} and (cvalue is None or cvalue < 0):
                return "Commission value సరైన numberగా ఇవ్వండి."
            campaign = self.repo.create_campaign(sender, creator, product_id, ctype, cvalue)
            commission = self._commission_label(campaign)
            return f"✅ Promotion campaign #{campaign['id']} created.\nProduct: {product.get('subject')}\nCreator: {creator}\nCode: {campaign['promo_code']}\nCommission: {commission}"

        use = re.fullmatch(r"(?i)PROMO USE\s+([A-Z0-9-]+)", clean)
        if use:
            campaign = self.repo.get_campaign_by_code(use.group(1))
            if not campaign:
                return "Promo code valid కాదు లేదా inactiveగా ఉంది."
            if str(campaign.get("creator_user_id")) == sender or str(campaign.get("seller_user_id")) == sender:
                return "Seller/creator తమ campaignకి buyer leadగా register కాలేరు."
            product = self.products.get(int(campaign["product_id"])) or {}
            self.repo.add_lead(int(campaign["id"]), sender)
            price = product.get("price")
            price_text = f" • ₹{float(price):g}" if price is not None else ""
            return f"✅ Creator referral applied.\nProduct: {product.get('subject') or 'Product'}{price_text}\nSeller confirmation/order flowలో ఈ attribution preserve అవుతుంది."

        if lowered == "promo my":
            rows = self.repo.campaigns_for_creator(sender)
            if not rows:
                return "మీకు active creator campaigns లేవు."
            lines = ["🎥 Your active promotion campaigns:"]
            for row in rows[:10]:
                product = self.products.get(int(row["product_id"])) or {}
                lines.append(f"• #{row['id']} {product.get('subject') or 'Product'} • {row['promo_code']} • {self._commission_label(row)}")
            return "\n".join(lines)

        stats = re.fullmatch(r"(?i)PROMO STATS\s+(\d+)", clean)
        if stats:
            campaign = self.repo.get_campaign(int(stats.group(1)))
            if not campaign:
                return "Campaign దొరకలేదు."
            if sender not in {str(campaign.get("seller_user_id")), str(campaign.get("creator_user_id"))}:
                return "ఈ campaign stats చూడటానికి permission లేదు."
            data = self.repo.campaign_stats(int(campaign["id"]))
            return f"📊 Campaign #{campaign['id']}\nLeads: {data['leads']}\nConversions: {data['conversions']}\nSales: ₹{data['sales']:g}\nCreator commission: ₹{data['commission']:g}"

        convert = re.fullmatch(r"(?i)PROMO CONVERT\s+(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)(?:\s*\|\s*₹?([0-9]+(?:\.[0-9]+)?))?", clean)
        if convert:
            campaign_id = int(convert.group(1)); buyer = convert.group(2).strip(); order_ref = convert.group(3).strip(); sale_amount = float(convert.group(4)) if convert.group(4) else None
            campaign = self.repo.get_campaign(campaign_id)
            if not campaign:
                return "Campaign దొరకలేదు."
            if str(campaign.get("seller_user_id")) != sender:
                return "Seller owner మాత్రమే conversion confirm చేయగలరు."
            conversion = self.repo.record_conversion(campaign_id, buyer, sender, order_ref, sale_amount)
            if not conversion:
                return "Conversion save కాలేదు."
            return f"✅ Conversion recorded for campaign #{campaign_id}.\nSale: ₹{float(conversion.get('sale_amount') or 0):g}\nCreator commission: ₹{float(conversion.get('commission_amount') or 0):g}"

        return (
            "Creator commerce commands:\n"
            "• CREATOR ON\n"
            "• PROMO CREATE <PRODUCT_ID> | <CREATOR_MOBILE> | PERCENT 10\n"
            "• PROMO USE <CODE>\n"
            "• PROMO MY\n"
            "• PROMO STATS <CAMPAIGN_ID>\n"
            "• PROMO CONVERT <CAMPAIGN_ID> | <BUYER> | <ORDER_REF> | <SALE_AMOUNT>"
        )

    @staticmethod
    def _commission_label(campaign) -> str:
        ctype = str(campaign.get("commission_type") or "NONE").upper()
        value = float(campaign.get("commission_value") or 0)
        if ctype == "PERCENT":
            return f"{value:g}%"
        if ctype == "FIXED":
            return f"₹{value:g} per conversion"
        return "not set"
