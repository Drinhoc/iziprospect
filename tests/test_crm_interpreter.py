from app.services.crm_interpreter import extract_phone, interpret_crm_message, parse_followup_from_text


def test_extract_phone_and_new_lead_interpretation():
    phone = extract_phone("Clinca sorrisa, 19 99898-9888 odonto")
    assert phone == "+5519998989888"
    interp = interpret_crm_message("Clinca sorrisa, 19 99898-9888 odonto", has_name=True, has_phone=True)
    assert interp.action_type == "novo_lead"


def test_followup_interpretation():
    followup = parse_followup_from_text("retornar amanhã")
    assert followup is not None
    interp = interpret_crm_message("retornar amanhã", has_name=False, has_phone=False)
    assert interp.action_type == "registrar_followup"
