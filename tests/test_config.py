import base64

from app.config import Settings


def test_parse_service_account_payload_accepts_single_quotes_dict_string():
    raw = "{'type': 'service_account', 'project_id': 'x'}"
    parsed = Settings._parse_service_account_payload(raw)
    assert parsed["type"] == "service_account"


def test_parse_service_account_payload_accepts_base64_json():
    raw_json = '{"type":"service_account","project_id":"x"}'
    encoded = base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")
    settings = Settings(
        openai_api_key="",
        google_sheets_id="sheet",
        google_service_account_json="",
        google_service_account_json_base64=encoded,
        evolution_webhook_secret=None,
        evolution_api_url=None,
        evolution_api_key=None,
        crm_target_group_id=None,
        disable_evolution_confirmation=True,
    )
    parsed = settings.service_account_info()
    assert parsed["project_id"] == "x"
