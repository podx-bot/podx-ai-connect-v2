from app.whatsapp.payload_parser import extract_document_messages


def test_extracts_whatsapp_document_for_menu_pdf():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.doc1",
                                    "from": "919999999999",
                                    "type": "document",
                                    "document": {
                                        "id": "media-doc-1",
                                        "mime_type": "application/pdf",
                                        "caption": "CMENU",
                                        "filename": "catering-menu.pdf",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    messages = extract_document_messages(payload)
    assert len(messages) == 1
    message = messages[0]
    assert message.sender_mobile == "919999999999"
    assert message.media_id == "media-doc-1"
    assert message.mime_type == "application/pdf"
    assert message.caption == "CMENU"
    assert message.filename == "catering-menu.pdf"
