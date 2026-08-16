from app.repositories.creator_commerce_repository import CreatorCommerceRepository
from app.repositories.product_catalog_repository import ProductCatalogRepository
from app.services.creator_commerce_runtime_service import CreatorCommerceRuntimeService


class FakeUsers:
    def __init__(self):
        self.users={
            'seller': {'whatsapp_mobile':'seller','registration_complete':1,'name':'Seller'},
            'creator': {'whatsapp_mobile':'creator','registration_complete':1,'name':'Creator'},
            'buyer': {'whatsapp_mobile':'buyer','registration_complete':1,'name':'Buyer'},
            'other': {'whatsapp_mobile':'other','registration_complete':1,'name':'Other'},
        }
        self.caps={}
    def find_by_whatsapp_mobile(self,mobile): return self.users.get(str(mobile))
    def add_capability(self,mobile,capability,source=None): self.caps.setdefault(str(mobile),set()).add(str(capability))


def build(tmp_path):
    db=str(tmp_path/'creator.db')
    products=ProductCatalogRepository(db)
    repo=CreatorCommerceRepository(db)
    users=FakeUsers()
    runtime=CreatorCommerceRuntimeService(repo,products,users)
    product_id=products.upsert_product('seller','Mixer Grinder',price=2500,stock_status='IN_STOCK')
    return runtime,repo,products,users,product_id


def test_creator_opt_in(tmp_path):
    runtime,_,_,users,_=build(tmp_path)
    reply=runtime.process('creator','CREATOR ON')
    assert 'Creator mode ON' in reply
    assert 'CREATOR' in users.caps['creator']


def test_seller_creates_campaign_and_buyer_lead_is_attributed(tmp_path):
    runtime,repo,_,_,product_id=build(tmp_path)
    reply=runtime.process('seller',f'PROMO CREATE {product_id} | creator | PERCENT 10')
    assert 'Promotion campaign #1' in reply
    campaign=repo.get_campaign(1)
    assert campaign['seller_user_id']=='seller'
    assert campaign['creator_user_id']=='creator'
    code=campaign['promo_code']
    buyer_reply=runtime.process('buyer',f'PROMO USE {code}')
    assert 'Creator referral applied' in buyer_reply
    assert repo.campaign_stats(1)['leads']==1
    runtime.process('buyer',f'PROMO USE {code}')
    assert repo.campaign_stats(1)['leads']==1


def test_non_owner_cannot_create_or_convert(tmp_path):
    runtime,repo,_,_,product_id=build(tmp_path)
    assert 'seller owner మాత్రమే' in runtime.process('other',f'PROMO CREATE {product_id} | creator')
    runtime.process('seller',f'PROMO CREATE {product_id} | creator | FIXED 50')
    code=repo.get_campaign(1)['promo_code']
    runtime.process('buyer',f'PROMO USE {code}')
    assert 'Seller owner మాత్రమే' in runtime.process('other','PROMO CONVERT 1 | buyer | ORD-1 | 2000')


def test_conversion_calculates_commission_and_stats_permissions(tmp_path):
    runtime,repo,_,_,product_id=build(tmp_path)
    runtime.process('seller',f'PROMO CREATE {product_id} | creator | PERCENT 10')
    code=repo.get_campaign(1)['promo_code']
    runtime.process('buyer',f'PROMO USE {code}')
    reply=runtime.process('seller','PROMO CONVERT 1 | buyer | ORD-1 | 2500')
    assert 'Creator commission: ₹250' in reply
    stats=repo.campaign_stats(1)
    assert stats['conversions']==1
    assert stats['sales']==2500
    assert stats['commission']==250
    creator_stats=runtime.process('creator','PROMO STATS 1')
    assert 'Conversions: 1' in creator_stats
    assert 'permission లేదు' in runtime.process('other','PROMO STATS 1')


def test_creator_and_seller_cannot_self_attribute_as_buyer(tmp_path):
    runtime,repo,_,_,product_id=build(tmp_path)
    runtime.process('seller',f'PROMO CREATE {product_id} | creator')
    code=repo.get_campaign(1)['promo_code']
    assert 'buyer leadగా register కాలేరు' in runtime.process('creator',f'PROMO USE {code}')
    assert 'buyer leadగా register కాలేరు' in runtime.process('seller',f'PROMO USE {code}')


def test_unrelated_message_not_hijacked(tmp_path):
    runtime,_,_,_,_=build(tmp_path)
    assert runtime.process('buyer','I need chicken 2 kg') is None
