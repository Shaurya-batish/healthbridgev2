from app.graph import build_system_prompt, run_extraction
from app.schemas import ExtractedFacts


def test_system_prompt_lists_every_fact_field_and_forbids_severity():
    prompt = build_system_prompt()
    for field_name in ExtractedFacts.model_fields:
        assert field_name in prompt
    assert "severity" in prompt.lower()  # mentioned only as something to forbid
    assert "never you" in prompt.lower() or "not you" in prompt.lower() or "do not" in prompt.lower()


def test_run_extraction_strips_hallucinated_severity_field():
    def fake_ollama_call(prompt, system):
        return {
            "fever_present": True,
            "fever_duration_days": 3,
            "severity": "RED",  # model disobeyed instructions -- must be dropped
            "urgency": "high",
        }

    facts = run_extraction("child has had fever for 3 days", age_months=24, ollama_call=fake_ollama_call)
    assert "severity" not in facts
    assert "urgency" not in facts
    assert facts["fever_present"] is True
    assert facts["fever_duration_days"] == 3
    assert facts["age_months"] == 24


def test_run_extraction_drops_unknown_and_invalid_fields():
    def fake_ollama_call(prompt, system):
        return {
            "palmar_pallor": "extremely severe somehow",  # not in enum -- must be dropped, not crash
            "not_a_real_field": 123,
            "convulsions": True,
        }

    facts = run_extraction("child had a convulsion", ollama_call=fake_ollama_call)
    assert facts.get("palmar_pallor") is None
    assert "not_a_real_field" not in facts
    assert facts["convulsions"] is True


def test_run_extraction_result_feeds_rule_engine_correctly():
    from app.rules_engine import evaluate

    def fake_ollama_call(prompt, system):
        return {"unable_to_drink_or_feed": True}

    facts = run_extraction("baby refuses to feed", ollama_call=fake_ollama_call)
    decision = evaluate(facts)
    assert decision["severity"] == "RED"
    assert decision["rule_id"] == "GDS-01"
