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
from app.services.universal_aware_conversation_service import UniversalAwareConversationService
from app.services.universal_live_capture_service import UniversalLiveCaptureService
from app.services.universal_matcher import UniversalMatcher
from app.services.universal_notification_service import UniversalNotificationService
from app.services.universal_request_extractor import UniversalRequestExtractor
from app.services.universal_response_command_service import UniversalResponseCommandService
from app.services.universal_targeting_service import UniversalTargetingService
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
        self.base_conversation_service = MarketplaceConversationService(
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
        self.universal_request_extractor = UniversalRequestExtractor(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_voice_model,
        )
        self.universal_matcher = UniversalMatcher(self.universal_demand_repository)
        self.universal_targeting_service = UniversalTargetingService(
            profile_source=self._universal_profiles,
            subject_similarity=UniversalMatcher._subject_similarity,
            distance_km=UniversalMatcher._distance_km,
        )
        self.universal_live_capture_service = UniversalLiveCaptureService(
            extractor=self.universal_request_extractor,
            demand_repository=self.universal_demand_repository,
            matcher=self.universal_matcher,
            targeting_service=self.universal_targeting_service,
            notification_service=self.universal_notification_service,
            notification_repository=self.universal_notification_repository,
            user_repository=self.user_repository,
            session_registry=self.session_registry,
        )
        self.conversation_service = UniversalAwareConversationService(
            response_commands=self.universal_response_command_service,
            live_capture=self.universal_live_capture_service,
            base_conversation=self.base_conversation_service,
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

    def _universal_profiles(self):
        """Combine registered users, seller listings and service profiles for targeting."""
        profiles = []
        user_rows = self.database.fetchall("SELECT * FROM users WHERE registration_complete = 1")
        users = {str(row["whatsapp_mobile"]): dict(row) for row in user_rows}

        for mobile, user in users.items():
            capabilities = self.user_repository.list_capabilities(mobile)
            role = str(user.get("role") or "").upper()
            if not role and capabilities:
                role = "BOTH" if len(capabilities) > 1 else str(capabilities[0]).upper()
            profiles.append(
                {
                    "user_id": mobile,
                    "role": role,
                    "category": user.get("job_category"),
                    "skill": user.get("job_category"),
                    "latitude": user.get("latitude"),
                    "longitude": user.get("longitude"),
                }
            )

        seller_rows = self.database.fetchall(
            "SELECT seller_mobile, product_name FROM seller_listings WHERE status = 'ACTIVE'"
        )
        seller_products = {}
        for row in seller_rows:
            mobile = str(row["seller_mobile"])
            seller_products.setdefault(mobile, []).append(row["product_name"])
        for mobile, products in seller_products.items():
            user = users.get(mobile, {})
            profiles.append(
                {
                    "user_id": mobile,
                    "role": "SELLER",
                    "products": products,
                    "category": " ".join(str(x) for x in products[:5]),
                    "latitude": user.get("latitude"),
                    "longitude": user.get("longitude"),
                }
            )

        provider_rows = self.database.fetchall(
            "SELECT provider_mobile, service_name FROM service_provider_profiles WHERE status = 'ACTIVE'"
        )
        for row in provider_rows:
            mobile = str(row["provider_mobile"])
            user = users.get(mobile, {})
            profiles.append(
                {
                    "user_id": mobile,
                    "role": "SERVICE_PROVIDER",
                    "service": row["service_name"],
                    "category": row["service_name"],
                    "latitude": user.get("latitude"),
                    "longitude": user.get("longitude"),
                }
            )
        return profiles

    def close(self) -> None:
        self.database.close()
