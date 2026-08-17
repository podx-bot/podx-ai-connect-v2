from app.services.universal_aware_conversation_service import UniversalAwareConversationService


class _Deals:
    class _Repo:
        def get(self, request_id, seller):
            raise AssertionError("old deal must not be touched for a new subject")

    repository = _Repo()


class _ResponseCommands:
    deals = _Deals()

    @staticmethod
    def _looks_like_deal_change(message):
        return True

    @staticmethod
    def _same_deal_context(request, message):
        return False


class _Base:
    pass


def test_accepted_old_deal_does_not_swallow_new_product_subject():
    service = UniversalAwareConversationService(
        response_commands=_ResponseCommands(),
        base_conversation=_Base(),
    )
    result = service._recover_accepted_deal(
        sender_mobile="buyer",
        message="55 inch Samsung smart TV ఉంది ₹42000, new, delivery available",
        interest={"requester_status": "ACCEPTED", "responder_user_id": "seller"},
        request={"id": 77, "domain": "PRODUCT", "subject": "Gajakesari Punugu"},
    )
    assert result is None
