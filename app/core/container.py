from app.core.settings import load_settings
from app.database.database import Database
from app.repositories.delivery_log_repository import (
    DeliveryLogRepository
)
from app.repositories.inbound_message_repository import (
    InboundMessageRepository
)
from app.repositories.job_lifecycle_repository import JobLifecycleRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.conversation_service import ConversationService
from app.services.job_lifecycle_service import JobLifecycleService
from app.services.job_matching_service import JobMatchingService
from app.services.session_registry import SessionRegistry
from app.whatsapp.whatsapp_service import WhatsAppService


class AppContainer:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.database = Database(self.settings.database_path)
        self.database.create_tables()

        self.user_repository = UserRepository(self.database)
        self.inbound_message_repository = (
            InboundMessageRepository(self.database)
        )
        self.delivery_log_repository = (
            DeliveryLogRepository(self.database)
        )
        self.session_repository = SessionRepository(self.database)
        self.job_lifecycle_repository = JobLifecycleRepository(self.database)

        self.session_registry = SessionRegistry(
            repository=self.session_repository
        )
        self.conversation_service = ConversationService(
            user_repository=self.user_repository,
            session_registry=self.session_registry
        )

        self.whatsapp_service = WhatsAppService(
            access_token=self.settings.whatsapp_access_token,
            phone_number_id=(
                self.settings.whatsapp_phone_number_id
            ),
            api_version=self.settings.whatsapp_api_version
        )
        self.job_matching_service = JobMatchingService(
            user_repository=self.user_repository,
            whatsapp_service=self.whatsapp_service
        )
        self.job_lifecycle_service = JobLifecycleService(
            repository=self.job_lifecycle_repository,
            whatsapp_service=self.whatsapp_service
        )

    def close(self) -> None:
        self.database.close()
