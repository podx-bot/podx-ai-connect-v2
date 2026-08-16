import threading

import pytest

from app.database.database import Database
from app.repositories.inbound_message_repository import (
    DuplicateInboundMessageError,
    InboundMessageRepository,
)


def _repo(tmp_path):
    database = Database(str(tmp_path / "podx.db"))
    database.create_tables()
    return database, InboundMessageRepository(database)


def test_claim_is_atomic_and_retry_safe(tmp_path):
    database, repo = _repo(tmp_path)
    try:
        assert repo.claim("wamid.1", "919999999999", "hello") is True
        assert repo.claim("wamid.1", "919999999999", "hello") is False
        assert repo.exists("wamid.1") is True
    finally:
        database.close()


def test_save_rejects_duplicate_instead_of_silently_allowing_processing(tmp_path):
    database, repo = _repo(tmp_path)
    try:
        repo.save("wamid.2", "919999999999", "hello")
        with pytest.raises(DuplicateInboundMessageError):
            repo.save("wamid.2", "919999999999", "hello")
    finally:
        database.close()


def test_concurrent_claim_has_exactly_one_winner(tmp_path):
    database, repo = _repo(tmp_path)
    results = []
    lock = threading.Lock()

    def worker():
        value = repo.claim("wamid.concurrent", "919999999999", "hello")
        with lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert results.count(True) == 1
        assert results.count(False) == 7
    finally:
        database.close()
