from req2test.evaluation.safety import safe_failure_reason


def test_failure_reason_redacts_common_credentials_and_flattens_lines():
    reason = safe_failure_reason(
        "request failed\nauthorization=Bearer-abc token:visible api_key=sk-demo Bearer abc.def"
    )
    assert "Bearer-abc" not in reason
    assert "visible" not in reason
    assert "sk-demo" not in reason
    assert "abc.def" not in reason
    assert "\n" not in reason
