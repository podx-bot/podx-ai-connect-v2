from app.services.easy_job_command_service import EasyJobCommandService


class DB:
    def __init__(self, registration_complete):
        self.registration_complete = registration_complete
        self.queries = []

    def fetchone(self, sql, params=()):
        self.queries.append((sql, params))
        if "FROM users" in sql:
            if self.registration_complete is None:
                return None
            return {"registration_complete": self.registration_complete}
        if "FROM match_notifications" in sql:
            return {"employer_job_id": 99}
        return None


class Repo:
    def __init__(self, registration_complete):
        self.database = DB(registration_complete)
        self.registration_complete = registration_complete
        self.active_calls = 0

    def find_user(self, sender):
        if self.registration_complete is None:
            return None
        return {"whatsapp_mobile": sender, "registration_complete": self.registration_complete}

    def active_assignment_for_worker(self, sender):
        self.active_calls += 1
        return None


class Lifecycle:
    def __init__(self):
        self.calls = []

    def process_text(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "JOB SHORTCUT"


def test_language_choice_one_cannot_accept_old_job_while_onboarding():
    repo = Repo(registration_complete=0)
    lifecycle = Lifecycle()
    service = EasyJobCommandService(repo, lifecycle)

    assert service.process_text("u1", "1") is None
    assert lifecycle.calls == []
    assert repo.active_calls == 0
    assert not any("match_notifications" in sql for sql, _ in repo.database.queries)


def test_spoken_yes_cannot_accept_old_job_before_profile_is_complete():
    repo = Repo(registration_complete=0)
    lifecycle = Lifecycle()
    service = EasyJobCommandService(repo, lifecycle)

    assert service.process_text("u1", "అవును") is None
    assert lifecycle.calls == []


def test_unknown_first_time_user_is_owned_by_onboarding_not_job_shortcuts():
    repo = Repo(registration_complete=None)
    lifecycle = Lifecycle()
    service = EasyJobCommandService(repo, lifecycle)

    assert service.process_text("new-user", "2") is None
    assert lifecycle.calls == []


def test_registered_user_keeps_existing_easy_job_accept_behavior():
    repo = Repo(registration_complete=1)
    lifecycle = Lifecycle()
    service = EasyJobCommandService(repo, lifecycle)

    assert service.process_text("u1", "1") == "JOB SHORTCUT"
    assert lifecycle.calls == [("u1", "ACCEPT 99")]
