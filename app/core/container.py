from app.core.settings import load_settings
from app.database.database import Database
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.delivery_log_repository import DeliveryLogRepository
from app.repositories.demand_repository import DemandRepository
from app.repositories.inbound_message_repository import InboundMessageRepository
from app.repositories.job_lifecycle_repository import JobLifecycleRepository
from app.repositories.marketplace_repository import MarketplaceRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.repositories.user_repository import UserRepository
from app.services.appointment_service import AppointmentService
from app.services.audio_codec_service import AudioCodecService
from app.services.demand_capture_service import DemandCaptureService
from app.services.easy_job_command_service import EasyJobCommandService
from app.services.intent_router_service import IntentRouterService
from app.services.job_lifecycle_service import JobLifecycleService
from app.services.job_matching_service import JobMatchingService
from app.services.marketplace_conversation_service import MarketplaceConversationService
from app.services.sarvam_tts_voice_assistant_service import SarvamTTSVoiceAssistantService
from app.services.session_registry import SessionRegistry
from app.services.universal_notification_service import UniversalNotificationService
from app.services.universal_response_command_service import UniversalResponseCommandService
from app.whatsapp.whatsapp_service import WhatsAppService


class AppContainer:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.database = Database(self.settings.database_path)
        self.database.create_tables()

        self.user_repository = UserRepository(self.database)
        self.inbound_message_repository = InboundMessageRepository(self.database)
        self.delivery_log_repository = DeliveryLogRepository(self.database)
        self.session_repository = SessionRepository(self.database)
        self.job_lifecycle_repository = JobLifecycleRepository(self.database)
        self.appointment_repository = AppointmentRepository(self.database)
        self.demand_repository = DemandRepository(self.database)
        self.marketplace_repository = MarketplaceRepository(self.database)
        self.demand_capture_service = DemandCaptureService(self.demand_repository)

        self.universal_demand_repository = UniversalDemandRepository(self.settings.database_path)
        self.universal_notification_repository = UniversalNotificationRepository(self.settings.database_path)

        self.session_registry = SessionRegistry(repository=self.session_repository)
        self.intent_router_service = IntentRouterService(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_voice_model,
        )
        self.appointment_service = AppointmentService(
            repository=self.appointment_repository,
            session_registry=self.session_registry,
        )
        self.conversation_service = MarketplaceConversationService(
            user_repository=self.user_repository,
            session_registry=self.session_registry,
            intent_router=self.intent_router_service,
            marketplace_repository=self.marketplace_repository,
            appointment_service=self.appointment_service,
            demand_capture_service=self.demand_capture_service,
        )

        self.whatsapp_service = WhatsAppService(
            access_token=self.settings.whatsapp_access_token,
            phone_number_id=self.settings.whatsapp_phone_number_id,
            api_version=self.settings.whatsapp_api_version,
        )
        self.universal_notification_service = UniversalNotificationService(
            notification_repository=self.universal_notification_repository,
            whatsapp_service=self.whatsapp_service,
            contact_resolver=self._resolve_universal_contact,
        )
        self.universal_response_command_service = UniversalResponseCommandService(
            demand_repository=self.universal_demand_repository,
            notification_service=self.universal_notification_service,
            notification_repository=self.universal_notification_repository,
        )

        self.audio_codec_service = AudioCodecService()
        self.voice_assistant_service = SarvamTTSVoiceAssistantService(
            sarvam_api_key=self.settings.sarvam_api_key,
            sarvam_model=self.settings.sarvam_stt_model,
            sarvam_timeout_seconds=self.settings.sarvam_stt_timeout_seconds,
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_voice_model,
            max_audio_bytes=self.settings.gemini_voice_max_bytes,
            tts_model=self.settings.gemini_tts_model,
            tts_voice=self.settings.gemini_tts_voice,
            voice_reply_max_chars=self.settings.voice_reply_max_chars,
            transcription_attempts=2,
            generate_content_attempts=2,
            audio_codec_service=self.audio_codec_service,
        )
        self.job_matching_service = JobMatchingService(
            user_repository=self.user_repository,
            whatsapp_service=self.whatsapp_service,
        )
        self.job_lifecycle_service = JobLifecycleService(
            repository=self.job_lifecycle_repository,
            whatsapp_service=self.whatsapp_service,
        )
        self.easy_job_command_service = EasyJobCommandService(
            repository=self.job_lifecycle_repository,
            lifecycle_service=self.job_lifecycle_service,
        )

    def _resolve_universal_contact(self, user_id: str):
        user = self.user_repository.find_by_whatsapp_mobile(str(user_id)) or {}
        if not user:
            return {"mobile": str(user_id), "name": "PODX User"}
        return {
            **user,
            "mobile": user.get("entered_mobile") or user.get("whatsapp_mobile") or str(user_id),
            "phone": user.get("entered_mobile") or user.get("whatsapp_mobile") or str(user_id),
            "name": user.get("name") or "PODX User",
        }

    def close(self) -> None:
        self.database.close()
