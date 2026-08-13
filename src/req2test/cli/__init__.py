"""Command-line interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from ..config import GenerationConfig, LLMSettings
from ..document_loader import load_document
from ..exporters import to_csv_bytes, to_json_text, to_markdown
from ..graph import run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从中文需求文档生成结构化测试用例")
    parser.add_argument("input", help="需求文件路径，支持 txt/md/docx/pdf")
    parser.add_argument("--mode", choices=["demo", "openai_compatible"], default="demo")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    parser.add_argument(
        "--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    parser.add_argument("--max-cases", type=int, default=12)
    parser.add_argument("--positive-only", action="store_true")
    parser.add_argument("--include-edge", action="store_true")
    parser.add_argument("--out-dir", default="output")
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    text = load_document(args.input)
    settings = LLMSettings(
        mode=args.mode,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
    )
    config = GenerationConfig(
        include_positive=True,
        include_negative=not args.positive_only,
        include_edge=args.include_edge,
        max_cases=args.max_cases,
    )
    result = run_workflow(text, settings, config)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "test_cases.md").write_text(to_markdown(result), encoding="utf-8")
    (out_dir / "test_cases.csv").write_bytes(to_csv_bytes(result))
    (out_dir / "result.json").write_text(to_json_text(result), encoding="utf-8")
    print(f"生成完成：{len(result.test_cases)} 条用例，评审得分 {result.review.score}")
    print(f"输出目录：{out_dir.resolve()}")
    if result.errors:
        print("运行提示：")
        for error in result.errors:
            print(f"- {error}")
