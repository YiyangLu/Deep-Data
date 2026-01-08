"""
Runner for iPlotBench evaluation.

Runs agents on prepared environments and saves outputs.

Pipeline:
1. Task 1: Recreation query → parse figure JSON
2. Task 2: One query per question → parse 0/1 answer

All queries in same session (agent remembers context).

Paths (inside Docker):
- /data/test/{figure_id}/input.png - Input images
- /data/query/{figure_id}/questions.json - Questions (no answers)
- /data/output/{model}/{figure_id}/ - Agent outputs
- /agent/ - Agent code (this project)
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from src.core.agent import Agent
from src.plotly.mcp_tools import create_plotly_mcp_server

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from .agent_config import CONFIGS, BaseConfig
from .prompts import get_task1_prompt, get_task2_prompt
from .parser import parse_figure, parse_answer
from .validator import validate_task1, validate_task2

# Paths - configurable for Docker vs local
DATA_ROOT = Path("/data")  # Docker mount point
TEST_ROOT = DATA_ROOT / "test"
QUERY_ROOT = DATA_ROOT / "query"
OUTPUT_ROOT = DATA_ROOT / "output"


async def run_task(
    figure_id: str,
    config: type[BaseConfig],
    questions: list[dict],
    model: str | None = None,
    display: bool = False,
) -> dict:
    """
    Run evaluation: Task 1 (recreation) + Task 2 (QA questions).

    All queries in same session so agent remembers context.

    Args:
        figure_id: Figure ID (e.g., "dot_line_16000")
        config: Agent config class (Vision, VisionLint, etc.)
        questions: List of question dicts with "question_string" key
        model: Model to use (opus, sonnet, haiku)
        display: Show agent output

    Returns:
        {"figure": {...}, "answers": [...], "task1_valid": bool, "task2_valid": bool}
    """
    test_dir = TEST_ROOT / figure_id
    input_png = test_dir / "input.png"

    logger.info(f"[task] {figure_id} | config={config.NAME} | model={model} | {len(questions)} questions")

    if not input_png.exists():
        logger.error(f"[task] {figure_id} | input.png not found: {input_png}")
        return {"figure": {}, "answers": [], "task1_valid": False, "task2_valid": False}

    # Create MCP server with only allowed tools
    mcp_server, cleanup = create_plotly_mcp_server(
        enable_headless=True,
        allowed_tools=config.TOOLS
    )

    try:
        agent = Agent(
            agent_id=f"eval_{config.NAME}",
            agent_type="eval",
            cwd=test_dir,
            allowed_tools=config.TOOLS,
            disallowed_tools=config.DISALLOWED_TOOLS,
            mcp_servers={"plotly": mcp_server},
            enable_storage=True,
            model=model,
            # No output_format - parse from text response
        )

        await agent.start()

        # === Task 1: Recreation ===
        task1_prompt = get_task1_prompt(hint=config.HINT)
        await agent.query(task1_prompt, display=display)
        response1 = agent.message_handler.get_last_response()

        # Parse figure from response
        figure = parse_figure(response1 or "")
        task1_result = validate_task1(figure)

        if task1_result.valid:
            logger.info(f"[task] {figure_id} | Task1 VALID: {task1_result.trace_count} traces")
        else:
            logger.warning(f"[task] {figure_id} | Task1 INVALID: {task1_result.error}")

        # === Task 2: QA questions (same session) ===
        answers = []
        valid_answers = 0

        for i, q in enumerate(questions):
            question_str = q["question_string"]
            task2_prompt = get_task2_prompt(question_str)

            await agent.query(task2_prompt, display=display)
            response = agent.message_handler.get_last_response()
            answer = parse_answer(response or "")

            if answer is not None:
                answers.append(answer)
                task2_check = validate_task2({"answer": answer})
                if task2_check.valid:
                    valid_answers += 1
            else:
                answers.append(None)  # Could not parse

        logger.info(f"[task] {figure_id} | Task2: {valid_answers}/{len(questions)} valid answers")

        await agent.stop()

        # All answers must be valid (not None and 0 or 1)
        task2_valid = valid_answers == len(questions)

        return {
            "figure": figure,
            "answers": answers,
            "task1_valid": task1_result.valid,
            "task2_valid": task2_valid,
        }

    finally:
        if cleanup:
            cleanup()


def get_questions(figure_id: str) -> list[dict]:
    """Load questions for a figure from query/."""
    questions_path = QUERY_ROOT / figure_id / "questions.json"
    if not questions_path.exists():
        return []
    return json.loads(questions_path.read_text())


async def run_env(
    figure_id: str,
    config_name: str,
    model: str | None = None,
    display: bool = False,
) -> dict:
    """
    Run evaluation on a single figure.

    Args:
        figure_id: Figure ID (e.g., "dot_line_16000")
        config_name: Config name ("vision", "vision_lint", etc.)
        model: Model to use (opus, sonnet, haiku)
        display: Show agent output

    Returns:
        Result dict with output file paths and validation status
    """
    config = CONFIGS[config_name]
    model_name = model or "haiku"  # Default model

    logger.info(f"[run_env] {figure_id} | config={config_name} | model={model_name}")

    # Load questions
    questions = get_questions(figure_id)
    if not questions:
        logger.error(f"[run_env] {figure_id} | No questions found")
        raise ValueError(f"No questions found for {figure_id}")

    # Run task
    output = await run_task(figure_id, config, questions, model, display)

    # Create output directory: output/{model}/{figure_id}/
    output_dir = OUTPUT_ROOT / model_name / figure_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_files = []

    # Save recreation output (figure)
    figure = output.get("figure", {})
    figure_file = output_dir / f"output_{config_name}_task1.json"
    figure_file.write_text(json.dumps(figure, indent=2))
    output_files.append(str(figure_file))

    task1_valid = output.get("task1_valid", False)
    logger.info(f"[run_env] {figure_id} | Saved figure to {figure_file} ({'VALID' if task1_valid else 'INVALID'})")

    # Save QA outputs (individual answer files)
    answers = output.get("answers", [])
    valid_answers = 0
    for i in range(len(questions)):
        qa_file = output_dir / f"output_{config_name}_task2_q{i}.json"
        if i < len(answers) and answers[i] is not None:
            answer_data = {"answer": answers[i]}
            qa_file.write_text(json.dumps(answer_data, indent=2))
            if validate_task2(answer_data).valid:
                valid_answers += 1
        else:
            # Missing/invalid answer - write empty
            qa_file.write_text("{}")
        output_files.append(str(qa_file))
    logger.info(f"[run_env] {figure_id} | Saved {len(questions)} QA files ({valid_answers}/{len(questions)} valid)")

    task2_valid = valid_answers == len(questions)

    return {
        "figure_id": figure_id,
        "config": config_name,
        "model": model_name,
        "output_files": output_files,
        "task1_valid": task1_valid,
        "task2_valid": task2_valid,
    }


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run iPlotBench evaluation")
    parser.add_argument("figure_id", help="Figure ID (e.g., dot_line_16000)")
    parser.add_argument("--config", default="vision", choices=list(CONFIGS.keys()))
    parser.add_argument("--model", default="haiku", choices=["opus", "sonnet", "haiku"],
                        help="Model to use (default: haiku)")
    parser.add_argument("--display", action="store_true", help="Show agent output")
    parser.add_argument("--data-root", type=Path, default=Path("/data"),
                        help="Data root (default: /data for Docker)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Override paths if specified
    if args.data_root != Path("/data"):
        DATA_ROOT = args.data_root
        TEST_ROOT = DATA_ROOT / "test"
        QUERY_ROOT = DATA_ROOT / "query"
        OUTPUT_ROOT = DATA_ROOT / "output"

    logger.info(f"Starting evaluation: {args.figure_id} | {args.config} | model={args.model}")
    logger.info(f"Data root: {DATA_ROOT}")

    result = asyncio.run(run_env(
        args.figure_id,
        args.config,
        args.model,
        args.display,
    ))

    logger.info(f"Done! Outputs saved: {len(result.get('output_files', []))} files")
    logger.info(f"Task1 valid: {result.get('task1_valid')}, Task2 valid: {result.get('task2_valid')}")
