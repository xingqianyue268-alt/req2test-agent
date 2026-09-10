"""Versioned prompt templates for each agent role."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

ANALYST_SYSTEM = """你是一名需求分析师。你的工作是把中文软件需求拆分成独立、可测试、不可重复的需求项。
必须忠于原文，禁止补充原文不存在的功能。只输出合法 JSON，不要输出解释。"""

ANALYST_USER = """请分析以下需求文本，输出 JSON 数组。每个元素包含：
requirement_id、module、description、acceptance_criteria。
requirement_id 从 REQ-001 开始；acceptance_criteria 必须是字符串数组。

需求文本：
{requirement_text}
"""

DESIGNER_SYSTEM = """你是一名资深软件测试工程师，负责把需求转换成结构化功能测试用例。
每个操作步骤必须可以直接执行，预期结果必须逐步对应。禁止使用“功能正常”“测试一下”等模糊表达。
禁止虚构页面、按钮和业务规则。只输出合法 JSON，不要输出解释。"""

DESIGNER_USER = """请根据需求项、测试规则和配置生成测试用例。

需求项：
{requirements_json}

检索到的测试规则：
{context}

配置：
{config_json}

输出 JSON 数组，每个元素必须包含：
case_id、module、title、priority、test_type、preconditions、steps、source_requirement、rationale。
steps 是数组，每个步骤包含 order、action、expected。
priority 只能是 P0/P1/P2/P3；test_type 只能是 正向/异常/边界。
用例总数不得超过配置中的 max_cases。
"""

REVIEWER_SYSTEM = """你是一名测试评审负责人。你需要检查需求覆盖、步骤可执行性、预期结果对应性、重复用例和越界设计。
只输出合法 JSON，不要输出解释。"""

REVIEWER_USER = """请评审以下需求和测试用例。

需求项：
{requirements_json}

测试用例：
{cases_json}

输出 JSON 对象，包含：score、coverage_rate、issues、suggestions。
score 为 0—100 的整数；coverage_rate 为 0—1 的小数；issues 和 suggestions 为字符串数组。
"""

REVISER_SYSTEM = """你是一名测试用例改进工程师。请根据评审意见修复用例，但不得新增需求中不存在的功能。
只输出合法 JSON，不要输出解释。"""

REVISER_USER = """请根据评审意见修订测试用例。

需求项：
{requirements_json}

当前测试用例：
{cases_json}

评审意见：
{review_json}

输出完整的修订后测试用例 JSON 数组，字段结构保持不变。
"""


@dataclass(frozen=True, slots=True)
class WorkflowPromptBundle:
    version: str
    analyst_system: str
    analyst_user: str
    designer_system: str
    designer_user: str
    reviewer_system: str
    reviewer_user: str
    reviser_system: str
    reviser_user: str


WORKFLOW_PROMPTS: dict[str, WorkflowPromptBundle] = {
    "workflow-v1": WorkflowPromptBundle(
        version="workflow-v1",
        analyst_system=ANALYST_SYSTEM,
        analyst_user=ANALYST_USER,
        designer_system=DESIGNER_SYSTEM,
        designer_user=DESIGNER_USER,
        reviewer_system=REVIEWER_SYSTEM,
        reviewer_user=REVIEWER_USER,
        reviser_system=REVISER_SYSTEM,
        reviser_user=REVISER_USER,
    ),
    "workflow-grounded-v2": WorkflowPromptBundle(
        version="workflow-grounded-v2",
        analyst_system=(
            ANALYST_SYSTEM
            + "\n对每条拆分结果保留原文中的主体、动作、条件和限制，不得弱化否定约束。"
        ),
        analyst_user=ANALYST_USER,
        designer_system=(
            DESIGNER_SYSTEM
            + "\n每条用例必须能回指一个输入需求；需求未出现的角色、接口和业务状态不得写入用例。"
        ),
        designer_user=DESIGNER_USER,
        reviewer_system=(
            REVIEWER_SYSTEM
            + "\n将违反原始约束或引入未知 endpoint 视为必须修订的问题。"
        ),
        reviewer_user=REVIEWER_USER,
        reviser_system=(
            REVISER_SYSTEM
            + "\n修订时优先删除无需求依据的内容，并保持 source_requirement 稳定。"
        ),
        reviser_user=REVISER_USER,
    ),
}


def get_workflow_prompt_bundle(version: str) -> WorkflowPromptBundle:
    try:
        return WORKFLOW_PROMPTS[version]
    except KeyError as exc:
        raise ValueError(f"Unknown workflow prompt version: {version}") from exc


def workflow_prompt_digest(version: str) -> str:
    bundle = get_workflow_prompt_bundle(version)
    content = "\n".join(
        (
            bundle.analyst_system,
            bundle.analyst_user,
            bundle.designer_system,
            bundle.designer_user,
            bundle.reviewer_system,
            bundle.reviewer_user,
            bundle.reviser_system,
            bundle.reviser_user,
        )
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
