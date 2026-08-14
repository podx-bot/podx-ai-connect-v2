"""Universal conversational adapter with matched-product FAQ context."""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

class UniversalAwareConversationService:
    GREETING_WORDS={"hi","hello","hey","హాయ్","హలో","नमस्ते","हाय"}
    PRODUCT_QUESTION_WORDS=("?","ధర","price","ఎంత","available","availability","stock","size","weight","quantity","delivery","warranty","return","expiry","feature","features","original","color","colour","variant","దొరుకుతుందా","ఉందా","ఎలా","ఏమిటి","doubt","details")
    def __init__(self,response_commands,base_conversation,live_capture=None,image_service=None)->None:
        self.response_commands=response_commands; self.live_capture=live_capture; self.image_service=image_service; self.base_conversation=base_conversation
    def process(self,sender_mobile:str,message:str)->str:
        clean=str(message or "").strip(); normalized=clean.casefold()
        if normalized in self.GREETING_WORDS:
            welcome=self._registered_welcome_back(sender_mobile)
            if welcome is not None:return welcome
        response=self.response_commands.process_text(sender_mobile=sender_mobile,message=clean)
        if response is not None:return response
        faq=self._matched_product_faq(sender_mobile,clean)
        if faq is not None:return faq
        if self.image_service is not None:
            image_reply=self.image_service.process_text(sender_mobile=sender_mobile,message=clean)
            if image_reply is not None:return image_reply
        if self.live_capture is not None:
            capture=self.live_capture.process_text(sender_mobile=sender_mobile,message=clean)
            if capture is not None:return capture
        return self.base_conversation.process(sender_mobile=sender_mobile,message=clean)
    def _matched_product_faq(self,sender_mobile:str,message:str)->str|None:
        lowered=message.casefold()
        if not any(word in lowered for word in self.PRODUCT_QUESTION_WORDS):return None
        repo=getattr(self.response_commands,"notification_repository",None); demands=getattr(self.response_commands,"demands",None)
        if repo is None or demands is None or not hasattr(repo,"latest_interest_for_buyer"):return None
        interest=repo.latest_interest_for_buyer(sender_mobile)
        if not interest:return None
        request=demands.get(int(interest["request_id"]))
        if not request or str(request.get("domain") or "").upper()!="PRODUCT":return None
        subject=str(request.get("subject") or "Product"); side=str(request.get("side") or "").upper(); seller_status=str(interest.get("requester_status") or "PENDING").upper()
        if "ధర" in lowered or "price" in lowered or "ఎంత" in lowered:
            if side=="OFFER" and request.get("price") is not None:return f"💰 {subject} seller listed price ₹{self._money(request.get('price'))}."
            return f"💰 {subject} seller final price ఇంకా confirm కాలేదు. Price తెలియకుండా PODX order continue చేయదు."
        if any(w in lowered for w in ("available","availability","stock","దొరుకుతుందా","ఉందా")):
            if seller_status=="ACCEPTED":return f"✅ Seller {subject} available అని confirm చేశారు."
            if seller_status=="REJECTED":return f"ఈ seller దగ్గర {subject} ప్రస్తుతం available లేదు."
            return f"⏳ {subject} availability seller confirmation కోసం wait చేస్తున్నాను."
        if any(w in lowered for w in ("quantity","weight","size")):
            if request.get("quantity") is not None:return f"📦 ప్రస్తుతం requestలో quantity: {request.get('quantity')} {request.get('unit') or ''}.".strip()
            return f"📦 {subject} exact size/quantity seller-confirmed dataలో ఇంకా లేదు."
        if "delivery" in lowered:
            return "🚚 Seller confirm తర్వాత Order Continue ఎంచుకుంటే delivery address తీసుకుని order process చేస్తాను."
        if any(w in lowered for w in ("warranty","return","expiry","feature","features","original","color","colour","variant","details","ఎలా","ఏమిటి","doubt")):
            return f"🤖 {subject} గురించి ఈ detail seller-confirmed product profileలో ఇంకా లేదు. నేను ఊహించి చెప్పను; seller-confirmed సమాచారం వచ్చిన తర్వాతనే చెప్తాను."
        return None
    @staticmethod
    def _money(value)->str:
        try:
            n=float(value); return f"{n:,.0f}" if n.is_integer() else f"{n:,.2f}"
        except (TypeError,ValueError):return str(value)
    def _registered_welcome_back(self,sender_mobile:str)->str|None:
        users=getattr(self.base_conversation,"user_repository",None); sessions=getattr(self.base_conversation,"session_registry",None)
        if users is None:return None
        user=users.find_by_whatsapp_mobile(sender_mobile)
        if not user or user.get("registration_complete")!=1:return None
        if sessions is not None:
            session=sessions.get(sender_mobile)
            try:
                from app.models.session import ConversationStep
                session.step=ConversationStep.MAIN_MENU; session.data.clear(); sessions.save(sender_mobile)
            except Exception:pass
        name=str(user.get("name") or "").strip(); language=str(user.get("language") or "English").strip().casefold(); hour=datetime.now(ZoneInfo("Asia/Kolkata")).hour
        period="morning" if hour<12 else ("afternoon" if hour<17 else "evening")
        if language=="telugu":
            wish={"morning":"శుభోదయం","afternoon":"శుభ మధ్యాహ్నం","evening":"శుభ సాయంత్రం"}[period]; person=f", {name} గారు" if name else ""
            return f"👋 {wish}{person}! PODXకి మళ్లీ స్వాగతం.\n\nఈరోజు మీకు ఎలా సహాయం చేయగలను? మీకు కావాల్సింది మీ మాటల్లో 🎙️ voiceగా లేదా ⌨️ textగా చెప్పండి."
        if language=="hindi":
            wish={"morning":"सुप्रभात","afternoon":"शुभ दोपहर","evening":"शुभ संध्या"}[period]; person=f", {name} जी" if name else ""
            return f"👋 {wish}{person}! PODX में आपका फिर से स्वागत है।\n\nआज मैं आपकी कैसे मदद कर सकता हूँ? जो चाहिए उसे अपनी भाषा में 🎙️ voice या ⌨️ text में बताइए।"
        wish={"morning":"Good morning","afternoon":"Good afternoon","evening":"Good evening"}[period]; person=f", {name}" if name else ""
        return f"👋 {wish}{person}! Welcome back to PODX.\n\nHow may I help you today? Tell me what you need in your own words by 🎙️ voice or ⌨️ text."
