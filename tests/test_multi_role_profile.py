from app.database.database import Database
from app.repositories.user_repository import UserRepository


def build_repo(tmp_path):
    database = Database(str(tmp_path / "multi_role.db"))
    database.create_tables()
    return database, UserRepository(database)


def register(repository, mobile="9199"):
    repository.create_or_update_registration(
        whatsapp_mobile=mobile,
        entered_mobile="9876543210",
        name="Test User",
        language="Telugu",
        area="Vijayawada",
    )


def test_same_user_can_be_worker_and_employer_without_losing_capabilities(tmp_path):
    database, repository = build_repo(tmp_path)
    try:
        register(repository)
        repository.save_worker_profile(
            whatsapp_mobile="9199",
            category="Delivery",
            experience="1-2 Years",
            availability="Tomorrow",
        )
        repository.save_employer_post(
            whatsapp_mobile="9199",
            service="Delivery",
            requirement="2 delivery workers కావాలి",
        )

        assert repository.list_capabilities("9199") == ["EMPLOYER", "WORKER"]
        user = repository.find_by_whatsapp_mobile("9199")
        assert user["capabilities"] == ["EMPLOYER", "WORKER"]
    finally:
        database.close()


def test_registration_can_seed_multiple_capabilities_and_conversation_can_expand_profile(tmp_path):
    database, repository = build_repo(tmp_path)
    try:
        register(repository)
        repository.add_capabilities(
            "9199",
            ["BUYER", "SELLER", "SERVICE_PROVIDER"],
            source="registration",
        )
        repository.add_capability(
            "9199",
            "SERVICE_CUSTOMER",
            source="conversation",
        )

        assert repository.list_capabilities("9199") == [
            "BUYER",
            "SELLER",
            "SERVICE_CUSTOMER",
            "SERVICE_PROVIDER",
        ]
    finally:
        database.close()
