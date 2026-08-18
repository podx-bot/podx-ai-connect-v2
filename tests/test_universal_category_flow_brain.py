from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain


def test_category_matrix_covers_reference_app_behaviours():
    brain = UniversalCategoryFlowBrain()
    cases = {
        "నాకు Vijayawadaలో driver job కావాలి": ("JOBS", "SEEKER", "FIND"),
        "need 3 workers for warehouse": ("JOBS", "PROVIDER", "HIRE"),
        "55 inch TV కావాలి": ("COMMERCE", "SEEKER", "BUY"),
        "నేను rice bags అమ్ముతాను": ("COMMERCE", "PROVIDER", "SELL"),
        "AC repair కావాలి": ("SERVICES", "SEEKER", "BOOK"),
        "నేను electrician service ఇస్తాను": ("SERVICES", "PROVIDER", "OFFER"),
        "logo design చేయించాలి": ("FREELANCE", "SEEKER", "HIRE"),
        "airportకి వెళ్లాలి cab కావాలి": ("MOBILITY", "SEEKER", "BOOK"),
        "రేపు Hyderabad వెళ్తున్నాను carలో 3 seats ఉన్నాయి": ("MOBILITY", "PROVIDER", "OFFER"),
        "biryani order చేయాలి": ("FOOD", "SEEKER", "ORDER"),
        "parcel send చేయాలి": ("DELIVERY", "SEEKER", "BOOK"),
        "doctor appointment కావాలి": ("APPOINTMENT", "SEEKER", "BOOK"),
        "medicine కావాలి": ("HEALTHCARE", "SEEKER", "FIND"),
        "2BHK flat rent కావాలి": ("PROPERTY", "SEEKER", "FIND"),
        "hotel room booking కావాలి": ("TRAVEL", "SEEKER", "BOOK"),
        "100 bags cement quotation కావాలి": ("B2B_RFQ", "SEEKER", "REQUEST_QUOTES"),
        "wedding function planning కావాలి": ("EVENT", "SEEKER", "PLAN"),
    }
    for message, expected in cases.items():
        decision = brain.classify(message)
        assert (decision.category, decision.side, decision.action) == expected, message


def test_provider_intents_beat_generic_seeker_words():
    brain = UniversalCategoryFlowBrain()
    service = brain.classify("నేను plumber service ఇస్తాను customers కావాలి")
    mobility = brain.classify("carలో one seat ఉంది lift ఇస్తాను")
    commerce = brain.classify("TV stock ఉంది అమ్ముతాను")
    assert service.side == "PROVIDER" and service.category == "SERVICES"
    assert mobility.side == "PROVIDER" and mobility.category == "MOBILITY"
    assert commerce.side == "PROVIDER" and commerce.category == "COMMERCE"


def test_specific_domains_beat_generic_kavali_commerce_rule():
    brain = UniversalCategoryFlowBrain()
    assert brain.classify("electrician కావాలి").category == "SERVICES"
    assert brain.classify("job కావాలి").category == "JOBS"
    assert brain.classify("cab కావాలి").category == "MOBILITY"
    assert brain.classify("doctor appointment కావాలి").category == "APPOINTMENT"
    assert brain.classify("flat rent కావాలి").category == "PROPERTY"


def test_unknown_text_falls_back_without_forcing_a_vertical():
    decision = UniversalCategoryFlowBrain().classify("ఇది ఎలా పని చేస్తుంది?")
    assert decision.category == "GENERAL"
    assert decision.action == "UNKNOWN"
    assert decision.confidence < 0.5
