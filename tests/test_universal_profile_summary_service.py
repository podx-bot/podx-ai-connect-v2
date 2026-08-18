from app.services.universal_profile_summary_service import UniversalProfileSummaryService


class Delegate:
    def __init__(self):
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "DOWNSTREAM"


class Users:
    def __init__(self, user=None):
        self.user = user

    def find_by_whatsapp_mobile(self, sender):
        if self.user is None:
            return None
        data = dict(self.user)
        data.setdefault("whatsapp_mobile", sender)
        return data


class Marketplace:
    def list_seller_listings_for_user(self, sender):
        return [
            {"product_name": "Chicken", "price_text": "₹250/kg"},
            {"product_name": "Eggs", "price_text": "₹6"},
        ]

    def list_service_provider_profiles_for_user(self, sender):
        return [{"service_name": "Electrician", "details": "Available today"}]


def test_non_profile_message_passes_through_untouched():
    delegate = Delegate()
    service = UniversalProfileSummaryService(delegate, Users({"registration_complete": 1}))

    assert service.process("u", "job కావాలి") == "DOWNSTREAM"
    assert delegate.calls == [("u", "job కావాలి")]


def test_incomplete_registration_does_not_expose_profile_summary():
    service = UniversalProfileSummaryService(Delegate(), Users(None))

    reply = service.process("u", "నా ప్రొఫైల్")
    assert "complete కాలేదు" in reply


def test_profile_summary_combines_universal_roles_worker_and_marketplace_data():
    users = Users({
        "registration_complete": 1,
        "name": "Manohar",
        "language": "Telugu",
        "area": "Vijayawada",
        "capabilities": ["BUYER", "SELLER", "SERVICE_PROVIDER", "WORKER"],
        "job_category": "Driver",
        "experience": "5+ Years",
        "availability": "Today",
        "latitude": 16.5,
        "longitude": 80.6,
    })
    service = UniversalProfileSummaryService(Delegate(), users, Marketplace())

    reply = service.process("u", "my profile")

    assert "Manohar" in reply
    assert "Vijayawada" in reply
    assert "Buyer" in reply and "Seller" in reply
    assert "Worker / Job Seeker" in reply
    assert "Driver" in reply and "5+ Years" in reply and "Location: Saved" in reply
    assert "Active Seller Listings: 2" in reply
    assert "Chicken" in reply and "Eggs" in reply
    assert "Service Profiles: 1" in reply
    assert "Electrician" in reply


def test_worker_missing_fields_are_visible_as_pending():
    users = Users({
        "registration_complete": 1,
        "name": "User",
        "capabilities": ["WORKER"],
        "job_category": None,
        "experience": None,
        "availability": None,
        "latitude": None,
        "longitude": None,
    })
    service = UniversalProfileSummaryService(Delegate(), users)

    reply = service.process("u", "profile")
    assert "పని: Pending" in reply
    assert "Experience: Pending" in reply
    assert "Availability: Pending" in reply
    assert "Location: Pending" in reply


def test_profile_summary_survives_marketplace_read_failure():
    class BrokenMarketplace:
        def list_seller_listings_for_user(self, sender):
            raise RuntimeError("db unavailable")

        def list_service_provider_profiles_for_user(self, sender):
            raise RuntimeError("db unavailable")

    users = Users({"registration_complete": 1, "name": "User", "capabilities": ["BUYER"]})
    service = UniversalProfileSummaryService(Delegate(), users, BrokenMarketplace())

    reply = service.process("u", "show profile")
    assert "User" in reply
    assert "Buyer" in reply
