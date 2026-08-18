from app.services.domain_complaint_prevention_service import DomainComplaintPreventionService


class Stub:
    def __init__(self, reply):
        self.reply = reply

    def process(self, sender_mobile, message):
        return self.reply


class Result:
    def __init__(self, category):
        self.category = category
        self.side = "SEEKER"
        self.action = "TEST"


class Brain:
    def __init__(self, category):
        self.category = category

    def classify(self, message):
        return Result(self.category)


def run(category, reply):
    return DomainComplaintPreventionService(Stub(reply), Brain(category)).process("u", "x")


def test_job_submission_gets_visible_active_status():
    reply = run("JOBS", "Your application sent successfully")
    assert "Status: ACTIVE" in reply
    assert "targeting widen" in reply


def test_job_reply_with_status_is_not_modified():
    original = "Application sent. Status: waiting for employer response."
    assert run("JOBS", original) == original


def test_commerce_final_confirmation_requires_fulfilment_terms():
    reply = run("COMMERCE", "Order confirmed. Final summary ready.")
    assert "availability" in reply
    assert "delivery/pickup" in reply


def test_commerce_final_with_availability_and_delivery_passes_unchanged():
    original = "Order confirmed. Stock available. Delivery tomorrow."
    assert run("COMMERCE", original) == original


def test_service_booking_requires_scope_price_and_time():
    reply = run("SERVICES", "Booking confirmed")
    assert "scope" in reply
    assert "price basis" in reply
    assert "time" in reply


def test_mobility_fare_change_requires_reconfirm():
    reply = run("MOBILITY", "Updated fare is ₹450")
    assert "Re-confirm" in reply


def test_freelance_hire_requires_deliverables_budget_deadline():
    reply = run("FREELANCE", "Hire confirmed")
    assert "deliverables" in reply
    assert "budget" in reply
    assert "deadline" in reply


def test_rfq_comparison_requires_normalized_basis():
    reply = run("B2B_RFQ", "Here are the supplier quotes")
    assert "same specification / quantity / delivery basis" in reply


def test_support_unresolved_requires_human_escalation():
    reply = run("SUPPORT", "This issue is unresolved")
    assert "human/admin support" in reply
    assert "restart చేయను" in reply


def test_normal_nonfinal_reply_is_never_changed():
    original = "1 year warranty ఉంది"
    assert run("COMMERCE", original) == original
