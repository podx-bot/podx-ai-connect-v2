"""WhatsApp runtime for PODX business receivables/payables ledger."""
from __future__ import annotations

import re


class BusinessLedgerRuntimeService:
    def __init__(self, repository, user_repository=None) -> None:
        self.ledger = repository
        self.users = user_repository

    def process(self, sender_user_id: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())
        if not clean.casefold().startswith("ledger "):
            return None
        if self.users is not None:
            user = self.users.find_by_whatsapp_mobile(str(sender_user_id)) or {}
            if int(user.get("registration_complete") or 0) != 1:
                return "ముందుగా PODX registration complete చేయండి."

        body = clean[7:].strip()
        add = re.fullmatch(
            r"(?i)(CREDIT|RECEIVABLE|DEBIT|PAYABLE|RECEIVED|PAID|PAY)\s+(.+?)\s*\|\s*₹?([0-9]+(?:\.[0-9]{1,2})?)(?:\s*\|\s*(.*))?",
            body,
        )
        if add:
            verb, party, amount, note = add.group(1).upper(), add.group(2).strip(), float(add.group(3)), add.group(4)
            mapping = {
                "CREDIT": "RECEIVABLE", "RECEIVABLE": "RECEIVABLE",
                "DEBIT": "PAYABLE", "PAYABLE": "PAYABLE",
                "RECEIVED": "RECEIVED", "PAID": "PAID", "PAY": "PAID",
            }
            kind = mapping[verb]
            entry_id = self.ledger.add_entry(sender_user_id, party, kind, amount, note)
            balance = self.ledger.balance(sender_user_id, party)
            return self._entry_reply(entry_id, party, kind, amount, balance)

        bal = re.fullmatch(r"(?i)(?:BALANCE|BAL)\s*(?:\|\s*)?(.+)?", body)
        if bal:
            party = (bal.group(1) or "").strip()
            if party:
                return self._balance_reply(party, self.ledger.balance(sender_user_id, party))
            parties = self.ledger.parties(sender_user_id, 10)
            if not parties:
                return "Ledgerలో ఇంకా entries లేవు."
            lines = ["📒 Ledger balances:"]
            lines.extend(self._party_line(row["counterparty"], float(row["balance"])) for row in parties)
            return "\n".join(lines)

        stmt = re.fullmatch(r"(?i)(?:STATEMENT|HISTORY)\s*(?:\|\s*)?(.+)?", body)
        if stmt:
            party = (stmt.group(1) or "").strip() or None
            rows = self.ledger.statement(sender_user_id, party, 10)
            if not rows:
                return "Ledger statementలో entries లేవు."
            title = f"📒 {party} statement:" if party else "📒 Recent ledger entries:"
            lines = [title]
            for row in reversed(rows):
                note = f" • {row.get('note')}" if row.get("note") else ""
                lines.append(f"#{row['id']} {row['entry_type']} ₹{float(row['amount']):g} • {row['counterparty']}{note}")
            if party:
                lines.append(self._balance_reply(party, self.ledger.balance(sender_user_id, party)))
            return "\n".join(lines)

        return (
            "Ledger commands:\n"
            "• LEDGER CREDIT <NAME> | <AMOUNT> | <NOTE optional>\n"
            "• LEDGER DEBIT <NAME> | <AMOUNT> | <NOTE optional>\n"
            "• LEDGER RECEIVED <NAME> | <AMOUNT>\n"
            "• LEDGER PAID <NAME> | <AMOUNT>\n"
            "• LEDGER BALANCE <NAME optional>\n"
            "• LEDGER STATEMENT <NAME optional>"
        )

    @staticmethod
    def _entry_reply(entry_id: int, party: str, kind: str, amount: float, balance: float) -> str:
        return f"✅ Ledger entry #{entry_id} saved: {kind} ₹{amount:g} • {party}\n{BusinessLedgerRuntimeService._balance_reply(party, balance)}"

    @staticmethod
    def _balance_reply(party: str, balance: float) -> str:
        if balance > 0:
            return f"💰 {party} నుంచి మీకు రావాల్సింది ₹{balance:g}."
        if balance < 0:
            return f"💸 మీరు {party}కి ఇవ్వాల్సింది ₹{abs(balance):g}."
        return f"✅ {party} balance settled (₹0)."

    @staticmethod
    def _party_line(party: str, balance: float) -> str:
        if balance > 0:
            return f"• {party}: receive ₹{balance:g}"
        if balance < 0:
            return f"• {party}: pay ₹{abs(balance):g}"
        return f"• {party}: settled"
