import pytest

from app.repositories.business_ledger_repository import BusinessLedgerRepository
from app.services.business_ledger_runtime_service import BusinessLedgerRuntimeService


class FakeUsers:
    def __init__(self):
        self.rows={"owner":{"whatsapp_mobile":"owner","registration_complete":1},"other":{"whatsapp_mobile":"other","registration_complete":1}}
    def find_by_whatsapp_mobile(self, mobile):
        return self.rows.get(str(mobile))


def test_customer_receivable_and_received_payment_reduce_balance(tmp_path):
    repo=BusinessLedgerRepository(str(tmp_path/'ledger.db')); runtime=BusinessLedgerRuntimeService(repo,FakeUsers())
    assert "saved" in runtime.process("owner","LEDGER CREDIT Sai Family Restaurant | 5000 | chicken supply")
    assert repo.balance("owner","Sai Family Restaurant")==5000
    reply=runtime.process("owner","LEDGER RECEIVED Sai Family Restaurant | 2000")
    assert "₹3000" in reply
    assert repo.balance("owner","Sai Family Restaurant")==3000


def test_supplier_payable_and_paid_settle(tmp_path):
    repo=BusinessLedgerRepository(str(tmp_path/'ledger2.db')); runtime=BusinessLedgerRuntimeService(repo,FakeUsers())
    runtime.process("owner","LEDGER DEBIT Feed Supplier | 1200")
    assert repo.balance("owner","Feed Supplier")==-1200
    reply=runtime.process("owner","LEDGER PAID Feed Supplier | 1200")
    assert "settled" in reply
    assert repo.balance("owner","Feed Supplier")==0


def test_owner_isolation_and_statement(tmp_path):
    repo=BusinessLedgerRepository(str(tmp_path/'ledger3.db'))
    repo.add_entry("owner","A","RECEIVABLE",100,"one")
    repo.add_entry("owner","A","RECEIVED",40,"two")
    repo.add_entry("other","A","RECEIVABLE",999)
    assert repo.balance("owner","A")==60
    assert repo.balance("other","A")==999
    rows=repo.statement("owner","A",10)
    assert [r["entry_type"] for r in rows]==["RECEIVED","RECEIVABLE"]


def test_balance_summary_and_non_ledger_bypass(tmp_path):
    repo=BusinessLedgerRepository(str(tmp_path/'ledger4.db')); runtime=BusinessLedgerRuntimeService(repo,FakeUsers())
    runtime.process("owner","LEDGER CREDIT Customer A | 250")
    runtime.process("owner","LEDGER DEBIT Supplier B | 90")
    reply=runtime.process("owner","LEDGER BALANCE")
    assert "Customer A" in reply and "Supplier B" in reply
    assert runtime.process("owner","I need chicken 2 kg") is None


def test_invalid_amount_rejected_by_repository(tmp_path):
    repo=BusinessLedgerRepository(str(tmp_path/'ledger5.db'))
    with pytest.raises(ValueError):
        repo.add_entry("owner","A","RECEIVABLE",0)
