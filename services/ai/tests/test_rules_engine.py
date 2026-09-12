import pytest

from app.rules_engine import evaluate


def _facts(**overrides):
    return dict(overrides)


@pytest.mark.parametrize(
    "facts, expected_rule_id, expected_severity",
    [
        (_facts(unable_to_drink_or_feed=True), "GDS-01", "RED"),
        (_facts(vomits_everything=True), "GDS-02", "RED"),
        (_facts(convulsions=True), "GDS-03", "RED"),
        (_facts(lethargic_or_unconscious=True), "GDS-04", "RED"),
        (_facts(chest_indrawing=True), "RESP-01", "RED"),
        (_facts(stridor_when_calm=True), "RESP-02", "RED"),
        (_facts(sunken_eyes=True, skin_pinch_very_slow=True), "DIAR-01", "RED"),
        (_facts(fever_present=True, stiff_neck=True), "FEV-01", "RED"),
        (_facts(tender_swelling_behind_ear=True), "EAR-01", "RED"),
        (_facts(visible_severe_wasting=True), "NUT-01", "RED"),
        (_facts(edema_both_feet=True), "NUT-02", "RED"),
        (_facts(palmar_pallor="severe"), "NUT-03", "RED"),
        (_facts(blood_in_stool=True), "DIAR-03", "YELLOW"),
        (_facts(diarrhea_duration_days=14), "DIAR-04", "YELLOW"),
        (_facts(fever_present=True, fever_duration_days=7), "FEV-02", "RED_OR_YELLOW"),
        (_facts(fever_present=True), "FEV-03", "YELLOW"),
        (_facts(ear_pain=True), "EAR-02", "YELLOW"),
        (_facts(ear_discharge=True), "EAR-02", "YELLOW"),
        (_facts(palmar_pallor="some"), "NUT-04", "YELLOW"),
        (_facts(), "DEFAULT-01", "GREEN"),
    ],
)
def test_single_rule_matches(facts, expected_rule_id, expected_severity):
    result = evaluate(facts)
    if expected_severity == "RED_OR_YELLOW":
        # FEV-02 (YELLOW) and FEV-03 (YELLOW) both match fever_present -- both
        # yellow, so either id is an acceptable "highest severity" pick since
        # they tie; assert on severity only for this one case.
        assert result["severity"] == "YELLOW"
        assert set(result["matched_rules"]) >= {"FEV-02", "FEV-03"}
        return
    assert result["rule_id"] == expected_rule_id
    assert result["severity"] == expected_severity


def test_diarrhea_atleast_two_of_four_triggers_yellow():
    # exactly 2 of 4 -> should trigger DIAR-02
    facts = _facts(restless_or_irritable=True, sunken_eyes=True)
    result = evaluate(facts)
    assert result["rule_id"] == "DIAR-02"
    assert result["severity"] == "YELLOW"


def test_diarrhea_only_one_of_four_does_not_trigger():
    facts = _facts(restless_or_irritable=True)
    result = evaluate(facts)
    assert "DIAR-02" not in result["matched_rules"]
    assert result["rule_id"] == "DEFAULT-01"
    assert result["severity"] == "GREEN"


@pytest.mark.parametrize(
    "age_months, rr, should_trigger",
    [
        (1, 59, False),
        (1, 60, True),
        (5, 49, False),
        (5, 50, True),
        (24, 39, False),
        (24, 40, True),
        (72, 45, False),  # out of 0-59 month range -> never triggers
    ],
)
def test_fast_breathing_age_bands(age_months, rr, should_trigger):
    facts = _facts(age_months=age_months, respiratory_rate_per_min=rr)
    result = evaluate(facts)
    if should_trigger:
        assert "RESP-03" in result["matched_rules"]
        assert result["severity"] == "YELLOW"
    else:
        assert "RESP-03" not in result["matched_rules"]


def test_missing_fields_never_auto_fire():
    # No facts at all -- every rule keys off a missing field and must be false.
    result = evaluate({})
    assert result["matched_rules"] == []
    assert result["severity"] == "GREEN"
    assert result["rule_id"] == "DEFAULT-01"


def test_highest_severity_wins_across_categories():
    # A RED general danger sign plus an unrelated YELLOW fever fact: RED must win.
    facts = _facts(unable_to_drink_or_feed=True, fever_present=True)
    result = evaluate(facts)
    assert result["severity"] == "RED"
    assert result["rule_id"] == "GDS-01"
    assert "FEV-03" in result["matched_rules"]
    assert "GDS-01" in result["matched_rules"]


def test_numeric_comparison_against_wrong_type_is_false_not_error():
    facts = _facts(diarrhea_duration_days="a lot")  # malformed input, should not raise
    result = evaluate(facts)
    assert "DIAR-04" not in result["matched_rules"]


def test_rule_version_matches_loaded_table_version():
    from app.rules_engine import load_rules

    table = load_rules()
    result = evaluate({})
    assert result["rule_version"] == table["version"]
