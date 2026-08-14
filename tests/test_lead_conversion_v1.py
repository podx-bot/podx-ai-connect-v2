from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.services.universal_notification_service import UniversalNotificationService
from app.services.universal_response_command_service import UniversalResponseCommandService

class FakeDemandRepository:
    def __init__(self,request):self.request=dict(request)
    def get(self,request_id):return dict(self.request) if int(request_id)==int(self.request["id"]) else None
class FakeWhatsApp:
    def __init__(self):self.sent=[]
    def send_text_message(self,recipient_mobile,message):self.sent.append({"type":"text","to":str(recipient_mobile),"body":str(message),"buttons":None});return {"success":True,"provider_message_id":f"m{len(self.sent)}"}
    def send_reply_buttons(self,recipient_mobile,body,buttons):self.sent.append({"type":"buttons","to":str(recipient_mobile),"body":str(body),"buttons":list(buttons)});return {"success":True,"provider_message_id":f"m{len(self.sent)}"}
    def send_image_by_id(self,recipient_mobile,media_id,caption=""):self.sent.append({"type":"image","to":str(recipient_mobile),"media_id":media_id,"body":caption,"buttons":None});return {"success":True,"provider_message_id":f"m{len(self.sent)}"}

def _build(request,tmp_path):
    buyer,seller="919900000002","919900000001";contacts={seller:{"mobile":seller,"name":"Seller"},buyer:{"mobile":buyer,"name":"Buyer"}}
    repo=UniversalNotificationRepository(str(tmp_path/f"lead-{request['id']}.db"));wa=FakeWhatsApp();notifications=UniversalNotificationService(repo,wa,lambda uid:contacts.get(str(uid)));commands=UniversalResponseCommandService(FakeDemandRepository(request),notifications,repo);return buyer,seller,repo,wa,notifications,commands

def test_offer_conversion_has_image_price_and_new_order_card(tmp_path):
    buyer,seller,repo,wa,n,c=_build({"id":52,"user_id":"919900000001","side":"OFFER","status":"ACTIVE","subject":"Gajakesari Punugu","price":99,"quantity":1,"unit":"pack","media_ref":"media-product-1"},tmp_path);r=c.demands.request
    assert n.dispatch_plan(r,{"waves":[{"wave":1,"targets":[{"user_id":buyer,"distance_km":1.2,"score":.95}]}]})["sent"]==1
    assert any(x["type"]=="image" and x["to"]==buyer for x in wa.sent);assert "₹99" in wa.sent[-1]["body"]
    c.process_text(buyer,f"BUY_INTERESTED 52 {seller}");assert any(x["type"]=="image" and x["to"]==seller for x in wa.sent)
    c.process_text(seller,f"SELLER_CONFIRM 52 {buyer}");assert "₹99" in wa.sent[-1]["body"]
    assert "delivery address" in c.process_text(buyer,f"ORDER_CONTINUE 52 {seller}").lower()
    assert "New Order Request" in (c.process_text(buyer,"12 Main Road, Vuyyuru, Krishna District 521165") or "") or any("New Order Request" in x["body"] for x in wa.sent)
    seller_cards=[x for x in wa.sent if x["to"]==seller and "New Order Request" in x["body"]];assert len(seller_cards)==1;assert "Price: ₹99" in seller_cards[0]["body"]

def test_offer_without_price_is_blocked_before_address(tmp_path):
    buyer,seller,repo,wa,n,c=_build({"id":53,"user_id":"919900000001","side":"OFFER","status":"ACTIVE","subject":"Product","media_ref":"m2"},tmp_path);r=c.demands.request
    repo.record_interest(53,buyer,seller);repo.set_seller_decision(53,seller,True)
    reply=c.process_text(buyer,f"ORDER_CONTINUE 53 {seller}");assert "price" in reply.lower();assert repo.get_interest(53,seller)["qualification_status"]=="READY_FOR_BUYER"

def test_need_price_is_labelled_budget_not_seller_price(tmp_path):
    buyer,seller,repo,wa,n,c=_build({"id":54,"user_id":"919900000002","side":"NEED","status":"ACTIVE","subject":"Rice","price":1000,"quantity":1,"unit":"bag","media_ref":"m3"},tmp_path);r=c.demands.request
    n.dispatch_plan(r,{"waves":[{"wave":1,"targets":[{"user_id":seller,"distance_km":2,"score":.9}]}]});assert "మీ budget: ₹1,000" in wa.sent[-1]["body"];assert "Price: ₹1,000" not in wa.sent[-1]["body"]
