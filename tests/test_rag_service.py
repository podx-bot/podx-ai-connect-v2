from app.repositories.rag_knowledge_repository import RagKnowledgeRepository
from app.services.rag_service import RagService


def test_rag_retrieves_seller_confirmed_product_knowledge(tmp_path):
    repo=RagKnowledgeRepository(str(tmp_path/'rag.db'))
    service=RagService(repo)
    product={'id':1,'seller_user_id':'seller1','subject':'Mixer Grinder','brand':'ABC','variant':'750W','price':2999,'stock_status':'IN_STOCK','delivery_available':1,'features':['3 jars','2 year warranty']}
    service.ingest_seller_product(product)
    result=service.retrieve_context('750W warranty details',namespaces=['SELLER_PRODUCT'],owner_user_id='seller1',subject='Mixer Grinder')
    assert result['status']=='CONTEXT_FOUND'
    assert result['evidence'][0]['source_type']=='SELLER_CONFIRMED'
    assert '750W' in result['evidence'][0]['content']


def test_live_price_question_requires_fresh_verification(tmp_path):
    repo=RagKnowledgeRepository(str(tmp_path/'rag2.db'))
    service=RagService(repo)
    repo.add('SELLER_PRODUCT','Seller confirmed price ₹999',owner_user_id='s1',subject='Product',source_type='SELLER_CONFIRMED')
    result=service.retrieve_context('price ఎంత?',namespaces=['SELLER_PRODUCT'],owner_user_id='s1',subject='Product')
    assert result['live_verification_required'] is True


def test_rag_does_not_return_unrelated_knowledge(tmp_path):
    repo=RagKnowledgeRepository(str(tmp_path/'rag3.db'))
    service=RagService(repo)
    repo.add('SELLER_FAQ','Warranty is two years',owner_user_id='s1',subject='Mixer',source_type='SELLER_CONFIRMED')
    result=service.retrieve_context('battery capacity',namespaces=['SELLER_FAQ'],owner_user_id='s1',subject='Mixer')
    assert result['status']=='NO_CONTEXT'
