from app.services.customer_facing_response_policy import CustomerFacingResponsePolicy


class Delegate:
    def __init__(self, reply):
        self.reply = reply

    def process(self, sender_mobile, message):
        return self.reply


class Ledger:
    def load_state(self, user_id):
        return {
            "active_entity": "chicken",
            "known_fields": {"quantity": 10, "unit": "kg"},
        }


def test_internal_product_profile_language_never_reaches_customer():
    raw = (
        "🤖 chicken గురించి ఈ detail seller-confirmed product profileలో ఇంకా లేదు. "
        "Final confirm ముందు availability + delivery/pickup terms confirm చేయాలి."
    )
    policy = CustomerFacingResponsePolicy(Delegate(raw), Ledger())

    reply = policy.process("buyer-1", "బోన్లెస్ కావాలి")

    assert "seller-confirmed" not in reply.casefold()
    assert "final confirm" not in reply.casefold()
    assert "10 kg chicken" in reply
    assert "కొత్త వివరాన్ని" in reply


def test_normal_customer_reply_is_preserved_exactly():
    raw = "✅ Match దొరికింది!"
    policy = CustomerFacingResponsePolicy(Delegate(raw), Ledger())

    assert policy.process("buyer-1", "10 kg chicken కావాలి") == raw


def test_internal_non_update_reply_becomes_safe_natural_telugu():
    raw = "pending_action is waiting; conversation os runtime state_json missing"
    policy = CustomerFacingResponsePolicy(Delegate(raw), Ledger())

    reply = policy.process("buyer-1", "ధర ఎంత?")

    assert "pending_action" not in reply
    assert "runtime" not in reply
    assert "ఊహించి" in reply
