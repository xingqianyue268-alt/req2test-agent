from req2test import GenerationConfig, LLMSettings, run_workflow


def test_demo_workflow_generates_traceable_cases():
    text = """# 用户管理\n1. 管理员可以新增用户并保存。\n2. 管理员可以根据用户名查询用户。"""
    result = run_workflow(
        text,
        LLMSettings(mode="demo"),
        GenerationConfig(include_positive=True, include_negative=False, max_cases=4),
    )
    assert len(result.requirements) == 2
    assert len(result.test_cases) == 2
    assert result.review.coverage_rate == 1.0
    assert all(case.source_requirement.startswith("REQ-") for case in result.test_cases)
