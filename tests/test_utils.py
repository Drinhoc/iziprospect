from app.main import _normalize_group_id, extract_name_before_phone, is_authorized_crm_group, is_message_too_vague
from app.services.normalizer import normalize_evolution_payload
from app.services.sheets_service import canonicalize_name, norm_phone, normalize_text


def test_normalize_text_and_phone():
    assert normalize_text(" Clínica Sorriso!! ") == "clinica sorriso"
    assert canonicalize_name("Clínica Bella Estética") == "bella"
    assert norm_phone("(11) 99999-8888") == "+5511999998888"   # DDD 11 + 9 dígitos
    assert norm_phone(11999998888) == "+5511999998888"         # mesmo número como int


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


def test_vague_message_and_name_fallback_helpers():
    assert is_message_too_vague("ok") is True
    assert is_message_too_vague("teste") is True
    assert is_message_too_vague("Clinca sorrisa, 19 998998988 odonto") is False
    assert extract_name_before_phone("Clinca sorrisa, 19 998998988 odonto") == "Clinca sorrisa"


def test_normalize_evolution_payload_audio_mimetype():
    # Fallback: sem mediaUrl do Evolution, usa URL criptografada do CDN
    payload = {
        "data": {
            "key": {"id": "AUDIO1", "remoteJid": "5511999999999@g.us"},
            "message": {"audioMessage": {"url": "https://mmg.whatsapp.net/foo_n.enc", "mimetype": "audio/ogg; codecs=opus"}},
        }
    }
    event = normalize_evolution_payload(payload)
    assert event.msg_type == "audio"
    assert event.media_url.endswith(".enc")
    assert event.media_mimetype == "audio/ogg; codecs=opus"


def test_normalize_evolution_payload_audio_prefers_media_url():
    # Prioridade: mediaUrl do Evolution (descriptografado) sobre audioMessage.url (.enc)
    payload = {
        "data": {
            "key": {"id": "AUDIO2", "remoteJid": "5511999999999@g.us"},
            "mediaUrl": "https://evolution-server/media/audio123.ogg",
            "message": {"audioMessage": {"url": "https://mmg.whatsapp.net/foo_n.enc", "mimetype": "audio/ogg; codecs=opus"}},
        }
    }
    event = normalize_evolution_payload(payload)
    assert event.msg_type == "audio"
    assert event.media_url == "https://evolution-server/media/audio123.ogg"
    assert not event.media_url.endswith(".enc")


def test_normalize_evolution_payload_audio_base64():
    # "Webhook Based64" do Evolution: áudio entregue como base64 no payload
    payload = {
        "data": {
            "key": {"id": "AUDIO3", "remoteJid": "5511999999999@g.us"},
            "base64": "T2dnUwACAAAAAAAAAA==",
            "message": {"audioMessage": {"url": "https://mmg.whatsapp.net/foo_n.enc", "mimetype": "audio/ogg; codecs=opus"}},
        }
    }
    event = normalize_evolution_payload(payload)
    assert event.msg_type == "audio"
    assert event.media_base64 == "T2dnUwACAAAAAAAAAA=="
    # Sem mediaUrl no payload, cai no fallback .enc (mas base64 será usado na transcrição)
    assert event.media_url is not None and event.media_url.endswith(".enc")


def test_is_authorized_crm_group_not_group():
    ok, reason = is_authorized_crm_group("5511999999999@s.whatsapp.net", False)
    assert ok is False
    assert reason == "not_group"


def test_normalize_group_id_formats():
    assert _normalize_group_id("120363425165290144@g.us") == "120363425165290144@g.us"
    assert _normalize_group_id("120363425165290144") == "120363425165290144@g.us"
    assert _normalize_group_id("[120363425165290144@g.us](mailto:120363425165290144@g.us)") == "120363425165290144@g.us"
