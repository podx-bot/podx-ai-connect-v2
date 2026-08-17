from app.services.admin_monitoring_runtime_service import AdminMonitoringRuntimeService


class Delegate:
    def __init__(self):
        self.calls = []

    def process(self, sender, message):
        self.calls.append((sender, message))
        return f"delegate:{sender}:{message}"


class Monitoring:
    def snapshot(self):
        return {
            "unresolved": 0,
            "runtime_errors": 0,
            "failed_deliveries": 0,
            "kyc_submitted": 0,
            "kyc_rejected": 0,
            "open_rfqs": 0,
            "open_rides": 0,
            "accepted_ride_bookings": 0,
        }


def test_non_admin_hi_accepts_webhook_sender_mobile_keyword():
    delegate = Delegate()
    runtime = AdminMonitoringRuntimeService(Monitoring(), delegate, admin_mobile="999")

    reply = runtime.process(sender_mobile="919346117227", message="Hi")

    assert reply == "delegate:919346117227:Hi"
    assert delegate.calls == [("919346117227", "Hi")]


def test_legacy_positional_call_still_works():
    delegate = Delegate()
    runtime = AdminMonitoringRuntimeService(Monitoring(), delegate, admin_mobile="999")

    assert runtime.process("111", "hello") == "delegate:111:hello"


def test_admin_command_still_uses_resolved_sender():
    runtime = AdminMonitoringRuntimeService(Monitoring(), Delegate(), admin_mobile="999")

    reply = runtime.process(sender_mobile="999", message="ADMIN STATUS")

    assert "PODX Admin Status" in reply
