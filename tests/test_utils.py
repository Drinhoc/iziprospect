from app.services.normalizer import normalize_evolution_payload
from app.services.sheets_service import canonicalize_name, norm_phone, normalize_text


def test_normalize_text_and_phone():
    assert normalize_text(" Clínica Sorriso!! ") == "clinica sorriso"
    assert canonicalize_name("Clínica Bella Estética") == "bella"
    assert norm_phone("(11) 99999-8888") == "+55119999998888"


def test_normalize_evolution_payload_text():
    payload = {
        "data": {
            "key": {"id": "ABCD", "remoteJid": "5511999999999@g.us", "participant": "5511999999999@s.whatsapp.net"},
            "messageTimestamp": 1730803200,
            "chatId": "5511999999999@g.us",
            "message": {"extendedTextMessage": {"text": "oi"}},
        }
    }
    event = normalize_evolution_payload(payload)
    assert event.msg_id == "ABCD"
    assert event.msg_type == "text"
    assert event.raw_text == "oi"
    assert event.is_group is True
