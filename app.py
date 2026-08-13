"""Legacy Streamlit demo retained as a compatibility entrypoint.

The maintained product UI is served by the FastAPI application in
``req2test.api``. This module remains runnable for users of the original
single-process demonstration workflow.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
from dotenv import load_dotenv

from req2test.config import GenerationConfig, LLMSettings
from req2test.document_loader import load_document_bytes
from req2test.exporters import to_csv_bytes, to_json_text, to_markdown
from req2test.graph import run_workflow

load_dotenv()

st.set_page_config(page_title="Req2Test Agent", page_icon="🧪", layout="wide")
st.title("Req2Test Agent")
st.caption("面向中文需求文档的多智能体测试设计平台")

with st.sidebar:
    st.header("运行配置")
    mode_label = st.radio("生成模式", ["演示模式", "OpenAI 兼容接口"], index=0)
    mode = "demo" if mode_label == "演示模式" else "openai_compatible"

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if mode == "openai_compatible":
        model = st.text_input("模型名称", value=model)
        base_url = st.text_input("Base URL", value=base_url)
        api_key = st.text_input("API Key", value=api_key, type="password")
        st.caption("本地 Ollama 可使用 http://localhost:11434/v1，并将 API Key 填为 ollama。")

    st.divider()
    st.subheader("测试类型")
    include_positive = st.checkbox("正向用例", value=True)
    include_negative = st.checkbox("异常用例", value=True)
    include_edge = st.checkbox("边界用例", value=False)
    max_cases = st.slider("最多生成用例数", min_value=1, max_value=30, value=12)
    min_review_score = st.slider("最低评审分数", min_value=60, max_value=100, value=85)

sample_path = Path(__file__).parent / "samples" / "food_traceability_requirements.md"
sample_text = sample_path.read_text(encoding="utf-8") if sample_path.exists() else ""

uploaded = st.file_uploader("上传需求文档", type=["txt", "md", "docx", "pdf"])
initial_text = sample_text
if uploaded is not None:
    try:
        suffix = Path(uploaded.name).suffix
        initial_text = load_document_bytes(uploaded.getvalue(), suffix)
        st.success(f"已读取：{uploaded.name}")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))

requirement_text = st.text_area(
    "需求内容",
    value=initial_text,
    height=330,
    help="可直接粘贴需求清单、操作手册或产品需求说明。",
)

if st.button("生成并评审测试用例", type="primary", use_container_width=True):
    try:
        llm_settings = LLMSettings(
            mode=mode,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        generation_config = GenerationConfig(
            include_positive=include_positive,
            include_negative=include_negative,
            include_edge=include_edge,
            max_cases=max_cases,
            min_review_score=min_review_score,
        )
        with st.spinner("智能体正在分析需求、生成用例并执行评审……"):
            result = run_workflow(requirement_text, llm_settings, generation_config)
        st.session_state["result"] = result
    except Exception as exc:  # noqa: BLE001
        st.error(f"运行失败：{exc}")

result = st.session_state.get("result")
if result:
    st.divider()
    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("需求项", len(result.requirements))
    metric2.metric("测试用例", len(result.test_cases))
    metric3.metric("评审得分", result.review.score)
    metric4.metric("需求覆盖率", f"{result.review.coverage_rate:.0%}")

    if result.errors:
        with st.expander("运行提示"):
            for error in result.errors:
                st.warning(error)

    tab_cases, tab_requirements, tab_review, tab_context = st.tabs(
        ["测试用例", "需求拆分", "评审报告", "检索依据"]
    )

    with tab_cases:
        for case in result.test_cases:
            with st.expander(f"{case.case_id}｜{case.title}｜{case.test_type}", expanded=False):
                st.write(
                    {
                        "模块": case.module,
                        "优先级": case.priority,
                        "来源需求": case.source_requirement,
                        "前置条件": case.preconditions,
                    }
                )
                st.table(
                    [
                        {"序号": step.order, "输入/操作描述": step.action, "预期结果": step.expected}
                        for step in case.steps
                    ]
                )

    with tab_requirements:
        st.table(
            [
                {
                    "需求编号": item.requirement_id,
                    "模块": item.module,
                    "需求描述": item.description,
                    "验收标准": "；".join(item.acceptance_criteria),
                }
                for item in result.requirements
            ]
        )

    with tab_review:
        st.progress(result.review.score / 100)
        st.write("问题：", result.review.issues or ["未发现结构性问题"])
        st.write("建议：", result.review.suggestions)

    with tab_context:
        for index, context in enumerate(result.retrieved_context, start=1):
            st.markdown(f"### 规则片段 {index}\n{context}")

    st.subheader("导出")
    col1, col2, col3 = st.columns(3)
    col1.download_button(
        "下载 Markdown",
        to_markdown(result),
        file_name="req2test_cases.md",
        mime="text/markdown",
        use_container_width=True,
    )
    col2.download_button(
        "下载 CSV",
        to_csv_bytes(result),
        file_name="req2test_cases.csv",
        mime="text/csv",
        use_container_width=True,
    )
    col3.download_button(
        "下载 JSON",
        to_json_text(result),
        file_name="req2test_result.json",
        mime="application/json",
        use_container_width=True,
    )
