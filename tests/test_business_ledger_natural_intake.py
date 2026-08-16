from app.repositories.business_ledger_repository import BusinessLedgerRepository
from app.services.business_ledger_runtime_service import BusinessLedgerRuntimeService


class FakeUsers:
    def find_by_whatsapp_mobile(self, mobile):
        return {"whatsapp_mobile":str(mobile),"registration_complete":1}


def test_telugu_natural_receivable_received_and_balance(tmp_path):
    runtime=BusinessLedgerRuntimeService(BusinessLedgerRepository(str(tmp_path/'a.db')),FakeUsers())
    reply=runtime.process('owner','Sai Restaurant నుంచి ₹5000 రావాలి')
    assert reply and '₹5000' in reply
    reply=runtime.process('owner','Sai Restaurant నుంచి ₹2000 వచ్చింది')
    assert '₹3000' in reply
    reply=runtime.process('owner','Sai Restaurant బ్యాలెన్స్ ఎంత?')
    assert '₹3000' in reply


def test_telugu_natural_payable_and_paid(tmp_path):
    runtime=BusinessLedgerRuntimeService(BusinessLedgerRepository(str(tmp_path/'b.db')),FakeUsers())
    reply=runtime.process('owner','Feed Supplierకి ₹1200 ఇవ్వాలి')
    assert '₹1200' in reply and 'ఇవ్వాల్సింది' in reply
    reply=runtime.process('owner','Feed Supplierకి ₹1200 ఇచ్చాను')
    assert 'settled' in reply


def test_english_natural_ledger(tmp_path):
    runtime=BusinessLedgerRuntimeService(BusinessLedgerRepository(str(tmp_path/'c.db')),FakeUsers())
    assert '₹750' in runtime.process('owner','Customer A owes me ₹750')
    assert '₹250' in runtime.process('owner','received ₹500 from Customer A')
    assert '₹900' in runtime.process('owner','I owe Supplier B ₹900')
    assert '₹300' in runtime.process('owner','paid ₹600 to Supplier B')
    assert '₹250' in runtime.process('owner','Customer A balance')


def test_natural_parser_does_not_hijack_normal_commerce(tmp_path):
    runtime=BusinessLedgerRuntimeService(BusinessLedgerRepository(str(tmp_path/'d.db')),FakeUsers())
    assert runtime.process('owner','I need chicken 2 kg for ₹500') is None
    assert runtime.process('owner','bike taxi Benz Circle to Railway Station') is None
    assert runtime.process('owner','500 guests marriage catering కావాలి') is None
