from req2test import GenerationConfig, LLMSettings, run_workflow
from req2test.metrics import average_step_count, duplicate_title_rate, structural_completeness


def test_quality_metrics_for_demo_result():
    result = run_workflow(
        "# 登录\n1. 用户可以使用正确账号和密码登录。",
        LLMSettings(mode="demo"),
        GenerationConfig(include_positive=True, include_negative=False, max_cases=3),
    )
    assert structural_completeness(result) == 1.0
    assert duplicate_title_rate(result) == 0.0
    assert average_step_count(result) == 3.0
