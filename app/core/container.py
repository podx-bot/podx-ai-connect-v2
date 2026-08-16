from app.core.settings import load_settings
from app.database.database import Database
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.catering_catalog_repository import CateringCatalogRepository
from app.repositories.catering_menu_pending_repository import CateringMenuPendingRepository
from app.repositories.delivery_log_repository import DeliveryLogRepository
from app.repositories.demand_repository import DemandRepository
from app.repositories.demand_signal_repository import DemandSignalRepository
from app.repositories.grocery_order_repository import GroceryOrderRepository
from app.repositories.grocery_rfq_repository import GroceryRFQRepository
from app.repositories.inbound_message_repository import InboundMessageRepository
from app.repositories.job_lifecycle_repository import JobLifecycleRepository
from app.repositories.local_dispatch_repository import LocalDispatchRepository
from app.repositories.marketplace_repository import MarketplaceRepository
from app.repositories.product_catalog_repository import ProductCatalogRepository
from app.repositories.rag_knowledge_repository import RagKnowledgeRepository
from app.repositories.ride_repository import RideRepository
from app.repositories.seller_ai_escalation_repository import SellerAIEscalationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.repositories.universal_image_pending_repository import UniversalImagePendingRepository
from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.repositories.user_repository import UserRepository
from app.services.appointment_provider_runtime_service import AppointmentProviderRuntimeService
from app.services.appointment_service import AppointmentService
from app.services.audio_codec_service import AudioCodecService
from app.services.buyer_intelligence_service import BuyerIntelligenceService
from app.services.catering_menu_ai_service import CateringMenuAIService
from app.services.catering_rfq_runtime_service import CateringRFQRuntimeService
from app.services.decision_opportunity_service import DecisionOpportunityService
from app.services.demand_capture_service import DemandCaptureService
from app.services.demand_intelligence_service import DemandIntelligenceService
from app.services.easy_job_command_service import EasyJobCommandService
from app.services.event_master_rfq_service import EventMasterRFQService
from app.services.event_master_runtime_service import EventMasterRuntimeService
from app.services.event_provider_runtime_service import EventProviderRuntimeService
from app.services.grocery_order_runtime_service import GroceryOrderRuntimeService
from app.services.grocery_rfq_runtime_service import GroceryRFQRuntimeService
from app.services.grocery_rfq_service import GroceryRFQService
from app.services.intent_router_service import IntentRouterService
from app.services.job_consent_lifecycle_service import JobConsentLifecycleService
from app.services.job_matching_service import JobMatchingService
from app.services.local_dispatch_runtime_service import LocalDispatchRuntimeService
from app.services.marketplace_conversation_service import MarketplaceConversationService
from app.services.product_ai_desk_service import ProductAIDeskService
from app.services.product_buyer_runtime_service import ProductBuyerRuntimeService
from app.services.rag_service import RagService
from app.services.ride_route_runtime_service import RideRouteRuntimeService
from app.services.ride_route_service import RideRouteService
from app.services.ride_runtime_service import RideRuntimeService
from app.services.sarvam_tts_voice_assistant_service import SarvamTTSVoiceAssistantService
from app.services.seller_ai_escalation_service import SellerAIEscalationService
from app.services.session_registry import SessionRegistry
from app.services.universal_aware_conversation_service import UniversalAwareConversationService
from app.services.universal_image_service import UniversalImageService
from app.services.universal_live_capture_service import UniversalLiveCaptureService
from app.services.universal_matcher import UniversalMatcher
from app.services.universal_notification_service import UniversalNotificationService
from app.services.universal_request_extractor import UniversalRequestExtractor
from app.services.universal_response_command_service import UniversalResponseCommandService
from app.services.universal_rfq_service import UniversalRFQService
from app.services.universal_targeting_service import UniversalTargetingService
from app.whatsapp.whatsapp_service import WhatsAppService


class AppContainer:
    def __init__(self) -> None:
        self.settings=load_settings(); self.database=Database(self.settings.database_path); self.database.create_tables()
        self.user_repository=UserRepository(self.database); self.inbound_message_repository=InboundMessageRepository(self.database); self.delivery_log_repository=DeliveryLogRepository(self.database); self.session_repository=SessionRepository(self.database); self.job_lifecycle_repository=JobLifecycleRepository(self.database); self.appointment_repository=AppointmentRepository(self.database); self.demand_repository=DemandRepository(self.database); self.marketplace_repository=MarketplaceRepository(self.database); self.demand_capture_service=DemandCaptureService(self.demand_repository)
        self.universal_demand_repository=UniversalDemandRepository(self.settings.database_path); self.universal_notification_repository=UniversalNotificationRepository(self.settings.database_path); self.universal_image_pending_repository=UniversalImagePendingRepository(self.settings.database_path); self.universal_rfq_repository=UniversalRFQRepository(self.settings.database_path); self.catering_catalog_repository=CateringCatalogRepository(self.settings.database_path); self.catering_menu_pending_repository=CateringMenuPendingRepository(self.settings.database_path); self.grocery_rfq_repository=GroceryRFQRepository(self.settings.database_path); self.grocery_order_repository=GroceryOrderRepository(self.settings.database_path); self.local_dispatch_repository=LocalDispatchRepository(self.settings.database_path); self.product_catalog_repository=ProductCatalogRepository(self.settings.database_path); self.rag_knowledge_repository=RagKnowledgeRepository(self.settings.database_path); self.ride_repository=RideRepository(self.settings.database_path); self.seller_ai_escalation_repository=SellerAIEscalationRepository(self.settings.database_path); self.demand_signal_repository=DemandSignalRepository(self.settings.database_path)
        self.session_registry=SessionRegistry(repository=self.session_repository); self.intent_router_service=IntentRouterService(api_key=self.settings.gemini_api_key,model=self.settings.gemini_voice_model); self.appointment_service=AppointmentService(repository=self.appointment_repository,session_registry=self.session_registry); self.base_conversation_service=MarketplaceConversationService(user_repository=self.user_repository,session_registry=self.session_registry,intent_router=self.intent_router_service,marketplace_repository=self.marketplace_repository,appointment_service=self.appointment_service,demand_capture_service=self.demand_capture_service)
        self.whatsapp_service=WhatsAppService(access_token=self.settings.whatsapp_access_token,phone_number_id=self.settings.whatsapp_phone_number_id,api_version=self.settings.whatsapp_api_version); self.appointment_provider_runtime_service=AppointmentProviderRuntimeService(self.appointment_repository,self.marketplace_repository,self.whatsapp_service,self.user_repository); self.appointment_service.set_provider_runtime(self.appointment_provider_runtime_service); self.ride_base_runtime_service=RideRuntimeService(self.ride_repository,self.whatsapp_service,self.user_repository); self.ride_route_service=RideRouteService(self.ride_repository,self.user_repository); self.ride_runtime_service=RideRouteRuntimeService(self.ride_base_runtime_service,self.ride_route_service); self.universal_notification_service=UniversalNotificationService(notification_repository=self.universal_notification_repository,whatsapp_service=self.whatsapp_service,contact_resolver=self._resolve_universal_contact); self.universal_response_command_service=UniversalResponseCommandService(demand_repository=self.universal_demand_repository,notification_service=self.universal_notification_service,notification_repository=self.universal_notification_repository); self.universal_request_extractor=UniversalRequestExtractor(api_key=self.settings.gemini_api_key,model=self.settings.gemini_voice_model); self.universal_matcher=UniversalMatcher(self.universal_demand_repository); self.universal_targeting_service=UniversalTargetingService(profile_source=self._universal_profiles,subject_similarity=UniversalMatcher._subject_similarity,distance_km=UniversalMatcher._distance_km); self.demand_intelligence_service=DemandIntelligenceService(self.universal_demand_repository,self.universal_targeting_service,self.demand_signal_repository,self.whatsapp_service,self._resolve_universal_contact); self.universal_live_capture_service=UniversalLiveCaptureService(extractor=self.universal_request_extractor,demand_repository=self.universal_demand_repository,matcher=self.universal_matcher,targeting_service=self.universal_targeting_service,notification_service=self.universal_notification_service,notification_repository=self.universal_notification_repository,user_repository=self.user_repository,session_registry=self.session_registry,demand_intelligence=self.demand_intelligence_service)
        self.universal_image_service=UniversalImageService(api_key=self.settings.gemini_api_key,model=self.settings.gemini_voice_model,pending_repository=self.universal_image_pending_repository,live_capture_service=self.universal_live_capture_service,openai_api_key=self.settings.openai_api_key,openai_model=self.settings.openai_vision_model,min_confidence=self.settings.image_ai_min_confidence); self.rag_service=RagService(self.rag_knowledge_repository); self.product_ai_desk_service=ProductAIDeskService(self.product_catalog_repository); self.buyer_intelligence_service=BuyerIntelligenceService(); self.decision_opportunity_service=DecisionOpportunityService(); self.seller_ai_escalation_service=SellerAIEscalationService(self.seller_ai_escalation_repository,self.product_ai_desk_service,self.whatsapp_service,self._resolve_universal_contact); self.product_buyer_runtime_service=ProductBuyerRuntimeService(notification_repository=self.universal_notification_repository,demand_repository=self.universal_demand_repository,catalog_repository=self.product_catalog_repository,product_desk=self.product_ai_desk_service,rag_service=self.rag_service,buyer_intelligence=self.buyer_intelligence_service,decision_service=self.decision_opportunity_service,seller_escalation=self.seller_ai_escalation_service,user_repository=self.user_repository)
        self.universal_rfq_service=UniversalRFQService(self.universal_rfq_repository); self.event_master_rfq_service=EventMasterRFQService(self.universal_rfq_repository); self.event_provider_runtime_service=EventProviderRuntimeService(self.universal_rfq_repository,self.universal_rfq_service,self.marketplace_repository,self.catering_catalog_repository,self.whatsapp_service,self._resolve_universal_contact); self.event_master_runtime_service=EventMasterRuntimeService(self.event_master_rfq_service,user_repository=self.user_repository,provider_runtime=self.event_provider_runtime_service,session_registry=self.session_registry); self.catering_menu_ai_service=CateringMenuAIService(api_key=self.settings.gemini_api_key,catalog_repository=self.catering_catalog_repository,pending_repository=self.catering_menu_pending_repository); self.catering_rfq_runtime_service=CateringRFQRuntimeService(self.catering_catalog_repository,self.universal_rfq_repository,self.universal_rfq_service,self.whatsapp_service,self._resolve_universal_contact,user_repository=self.user_repository)
        self.grocery_rfq_service=GroceryRFQService(self.grocery_rfq_repository); self.grocery_rfq_runtime_service=GroceryRFQRuntimeService(self.grocery_rfq_repository,self.grocery_rfq_service,self.whatsapp_service,self._resolve_universal_contact,user_repository=self.user_repository); self.local_dispatch_runtime_service=LocalDispatchRuntimeService(self.local_dispatch_repository,self.user_repository,self.whatsapp_service,self._resolve_universal_contact); self.grocery_order_runtime_service=GroceryOrderRuntimeService(self.grocery_rfq_repository,self.grocery_order_repository,self.local_dispatch_repository,self._resolve_universal_contact,user_repository=self.user_repository,dispatch_runtime=self.local_dispatch_runtime_service)
        self.conversation_service=UniversalAwareConversationService(response_commands=self.universal_response_command_service,live_capture=self.universal_live_capture_service,image_service=self.universal_image_service,base_conversation=self.base_conversation_service,product_runtime=self.product_buyer_runtime_service,seller_escalation=self.seller_ai_escalation_service,grocery_runtime=self.grocery_rfq_runtime_service,grocery_order_runtime=self.grocery_order_runtime_service,catering_runtime=self.catering_rfq_runtime_service,catering_menu_ai=self.catering_menu_ai_service,event_runtime=self.event_master_runtime_service,event_provider_runtime=self.event_provider_runtime_service,ride_runtime=self.ride_runtime_service)
        self.audio_codec_service=AudioCodecService()
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
        self.job_matching_service=JobMatchingService(user_repository=self.user_repository,whatsapp_service=self.whatsapp_service); self.job_lifecycle_service=JobConsentLifecycleService(repository=self.job_lifecycle_repository,whatsapp_service=self.whatsapp_service); self.easy_job_command_service=EasyJobCommandService(repository=self.job_lifecycle_repository,lifecycle_service=self.job_lifecycle_service)

    def _resolve_universal_contact(self,user_id:str):
        user=self.user_repository.find_by_whatsapp_mobile(str(user_id)) or {}
        if not user:return {"mobile":str(user_id),"phone":str(user_id),"name":"PODX User"}
        whatsapp_mobile=str(user.get("whatsapp_mobile") or user_id); entered_mobile=str(user.get("entered_mobile") or whatsapp_mobile); return {**user,"mobile":whatsapp_mobile,"phone":entered_mobile,"whatsapp_mobile":whatsapp_mobile,"name":user.get("name") or "PODX User"}

    def _universal_profiles(self):
        profiles=[]; user_rows=self.database.fetchall("SELECT * FROM users WHERE registration_complete = 1"); users={str(row["whatsapp_mobile"]):dict(row) for row in user_rows}
        capabilities_by_mobile={}
        for mobile in users:capabilities_by_mobile[mobile]=self.user_repository.list_capabilities(mobile)
        for mobile,user in users.items():
            capabilities=capabilities_by_mobile[mobile]; role=str(user.get("role") or "").upper(); role=role or ("BOTH" if len(capabilities)>1 else (str(capabilities[0]).upper() if capabilities else "")); profiles.append({"user_id":mobile,"role":role,"category":user.get("job_category"),"skill":user.get("job_category"),"latitude":user.get("latitude"),"longitude":user.get("longitude")})
        seller_rows=self.database.fetchall("SELECT seller_mobile, product_name FROM seller_listings WHERE status = 'ACTIVE'"); seller_products={}
        for row in seller_rows:seller_products.setdefault(str(row["seller_mobile"]),[]).append(row["product_name"])
        for mobile,products in seller_products.items():
            user=users.get(mobile,{}); profiles.append({"user_id":mobile,"role":"SELLER","products":products,"category":" ".join(str(x) for x in products[:5]),"latitude":user.get("latitude"),"longitude":user.get("longitude")})
        provider_rows=self.database.fetchall("SELECT provider_mobile, service_name FROM service_provider_profiles WHERE status = 'ACTIVE'")
        for row in provider_rows:
            mobile=str(row["provider_mobile"]); user=users.get(mobile,{}); profiles.append({"user_id":mobile,"role":"SERVICE_PROVIDER","service":row["service_name"],"category":row["service_name"],"latitude":user.get("latitude"),"longitude":user.get("longitude")})
        return profiles

    def close(self)->None:self.database.close()
