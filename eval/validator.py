#!/usr/bin/env python3
"""
Output validators for iPlotBench tasks.

This module provides validation functions that agents can use to check
the quality of their outputs before submission.

Usage:
    from eval.validator import validate_task1, validate_task2

    # Validate Task 1 (Recreation) output
    result = validate_task1(output_dict)
    if result.valid:
        print("Output is valid!")
    else:
        print(f"Invalid: {result.error}")

    # Validate Task 2 (QA) output
    result = validate_task2(output_dict)
    if result.valid:
        print(f"Answer: {result.answer}")
    else:
        print(f"Invalid: {result.error}")

CLI Usage:
    python -m eval.validator task1 path/to/output.json
    python -m eval.validator task2 path/to/output.json
    python -m eval.validator check-dir path/to/output_dir
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Union


@dataclass
class Task1ValidationResult:
    """Result of Task 1 output validation."""
    valid: bool
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    trace_count: int = 0
    data_fields_found: List[str] = field(default_factory=list)


@dataclass
class Task2ValidationResult:
    """Result of Task 2 output validation."""
    valid: bool
    answer: Optional[int] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def validate_task1(data: Any) -> Task1ValidationResult:
    """
    Validate Task 1 (Recreation) output.

    A valid Task 1 output must be a Plotly figure with:
    - A "data" key containing a non-empty list of traces
    - At least one trace with actual data (x, y, values, or labels)

    Args:
        data: The output data (dict or JSON string)

    Returns:
        Task1ValidationResult with validation status and details
    """
    # Handle JSON string input
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return Task1ValidationResult(valid=False, error=f"Invalid JSON: {e}")

    # Check basic structure
    if data is None:
        return Task1ValidationResult(valid=False, error="Output is None")

    if not isinstance(data, dict):
        return Task1ValidationResult(valid=False, error=f"Expected dict, got {type(data).__name__}")

    if data == {}:
        return Task1ValidationResult(valid=False, error="Output is empty dict {}")

    # Check for "data" key
    if "data" not in data:
        return Task1ValidationResult(valid=False, error="Missing 'data' key")

    traces = data["data"]
    if not isinstance(traces, list):
        return Task1ValidationResult(valid=False, error=f"'data' must be a list, got {type(traces).__name__}")

    if len(traces) == 0:
        return Task1ValidationResult(valid=False, error="'data' list is empty")

    # Check traces for actual data
    warnings = []
    data_fields_found = []
    has_data = False

    for i, trace in enumerate(traces):
        if not isinstance(trace, dict):
            warnings.append(f"Trace {i}: not a dict")
            continue

        if trace == {}:
            warnings.append(f"Trace {i}: empty dict")
            continue

        # Check for data fields
        trace_fields = []
        for field_name in ["x", "y", "values", "labels", "z", "text", "lat", "lon"]:
            field_value = trace.get(field_name)
            if field_value is not None:
                if isinstance(field_value, (list, tuple)) and len(field_value) > 0:
                    has_data = True
                    trace_fields.append(f"{field_name}[{len(field_value)}]")
                elif not isinstance(field_value, (list, tuple)):
                    # Scalar value
                    has_data = True
                    trace_fields.append(field_name)

        if trace_fields:
            data_fields_found.extend(trace_fields)

    if not has_data:
        return Task1ValidationResult(
            valid=False,
            error="No traces contain actual data (x, y, values, labels, etc.)",
            warnings=warnings,
            trace_count=len(traces),
        )

    # Check for layout (optional but useful)
    if "layout" not in data:
        warnings.append("Missing 'layout' key (optional)")

    return Task1ValidationResult(
        valid=True,
        warnings=warnings,
        trace_count=len(traces),
        data_fields_found=data_fields_found,
    )


def validate_task2(data: Any) -> Task2ValidationResult:
    """
    Validate Task 2 (QA) output.

    A valid Task 2 output must be a dict with:
    - An "answer" key containing exactly 0 or 1

    Args:
        data: The output data (dict or JSON string)

    Returns:
        Task2ValidationResult with validation status and details
    """
    # Handle JSON string input
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return Task2ValidationResult(valid=False, error=f"Invalid JSON: {e}")

    # Check basic structure
    if data is None:
        return Task2ValidationResult(valid=False, error="Output is None")

    if not isinstance(data, dict):
        return Task2ValidationResult(valid=False, error=f"Expected dict, got {type(data).__name__}")

    if data == {}:
        return Task2ValidationResult(valid=False, error="Output is empty dict {}")

    # Check for "answer" key
    if "answer" not in data:
        return Task2ValidationResult(valid=False, error="Missing 'answer' key")

    answer = data["answer"]

    # Validate answer value
    warnings = []

    # Handle string answers
    if isinstance(answer, str):
        answer_lower = answer.lower().strip()
        if answer_lower in ("0", "no", "false"):
            warnings.append(f"Answer '{answer}' interpreted as 0")
            return Task2ValidationResult(valid=True, answer=0, warnings=warnings)
        elif answer_lower in ("1", "yes", "true"):
            warnings.append(f"Answer '{answer}' interpreted as 1")
            return Task2ValidationResult(valid=True, answer=1, warnings=warnings)
        else:
            return Task2ValidationResult(
                valid=False,
                error=f"Invalid answer string: '{answer}'. Must be 0/1 or yes/no/true/false"
            )

    # Handle boolean
    if isinstance(answer, bool):
        warnings.append(f"Answer {answer} interpreted as {1 if answer else 0}")
        return Task2ValidationResult(valid=True, answer=1 if answer else 0, warnings=warnings)

    # Handle numeric
    try:
        answer_int = int(answer)
        if answer_int not in (0, 1):
            return Task2ValidationResult(
                valid=False,
                error=f"Invalid answer: {answer_int}. Must be exactly 0 or 1"
            )
        return Task2ValidationResult(valid=True, answer=answer_int)
    except (ValueError, TypeError):
        return Task2ValidationResult(
            valid=False,
            error=f"Cannot convert answer to int: {answer} (type: {type(answer).__name__})"
        )


def validate_task1_file(path: Union[str, Path]) -> Task1ValidationResult:
    """Validate a Task 1 output file."""
    path = Path(path)
    if not path.exists():
        return Task1ValidationResult(valid=False, error=f"File not found: {path}")

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return Task1ValidationResult(valid=False, error=f"Invalid JSON: {e}")

    return validate_task1(data)


def validate_task2_file(path: Union[str, Path]) -> Task2ValidationResult:
    """Validate a Task 2 output file."""
    path = Path(path)
    if not path.exists():
        return Task2ValidationResult(valid=False, error=f"File not found: {path}")

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return Task2ValidationResult(valid=False, error=f"Invalid JSON: {e}")

    return validate_task2(data)


def check_output_directory(output_dir: Union[str, Path], verbose: bool = False) -> Dict[str, Any]:
    """
    Check all outputs in a directory for validity.

    Args:
        output_dir: Path to output directory (e.g., env/output/haiku)
        verbose: Print detailed info for each file

    Returns:
        Dict with summary statistics
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        return {"error": f"Directory not found: {output_dir}"}

    stats = {
        "task1": {"valid": 0, "invalid": 0, "missing": 0, "errors": []},
        "task2": {"valid": 0, "invalid": 0, "missing": 0, "errors": []},
    }

    for fig_dir in sorted(output_dir.iterdir()):
        if not fig_dir.is_dir():
            continue

        figure_id = fig_dir.name

        # Check Task 1 files
        for task1_file in fig_dir.glob("output_*_task1.json"):
            result = validate_task1_file(task1_file)
            if result.valid:
                stats["task1"]["valid"] += 1
            else:
                stats["task1"]["invalid"] += 1
                if verbose or len(stats["task1"]["errors"]) < 10:
                    stats["task1"]["errors"].append(f"{task1_file.name}: {result.error}")

        # Check Task 2 files
        for task2_file in fig_dir.glob("output_*_task2_q*.json"):
            result = validate_task2_file(task2_file)
            if result.valid:
                stats["task2"]["valid"] += 1
            else:
                stats["task2"]["invalid"] += 1
                if verbose or len(stats["task2"]["errors"]) < 10:
                    stats["task2"]["errors"].append(f"{task2_file.name}: {result.error}")

    return stats


# =============================================================================
# CLI Interface
# =============================================================================

def _print_task1_result(result: Task1ValidationResult, path: str = None):
    """Print Task 1 validation result."""
    prefix = f"{path}: " if path else ""
    if result.valid:
        print(f"{prefix}VALID")
        print(f"  Traces: {result.trace_count}")
        print(f"  Data fields: {', '.join(result.data_fields_found[:10])}")
        if result.warnings:
            print(f"  Warnings: {result.warnings}")
    else:
        print(f"{prefix}INVALID - {result.error}")
        if result.warnings:
            print(f"  Warnings: {result.warnings}")


def _print_task2_result(result: Task2ValidationResult, path: str = None):
    """Print Task 2 validation result."""
    prefix = f"{path}: " if path else ""
    if result.valid:
        print(f"{prefix}VALID (answer={result.answer})")
        if result.warnings:
            print(f"  Warnings: {result.warnings}")
    else:
        print(f"{prefix}INVALID - {result.error}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate iPlotBench output files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m eval.validator task1 output.json
    python -m eval.validator task2 answer.json
    python -m eval.validator check-dir env/output/haiku
    python -m eval.validator check-dir env/output/haiku --verbose
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # task1 command
    task1_parser = subparsers.add_parser("task1", help="Validate Task 1 output file")
    task1_parser.add_argument("file", type=Path, help="Path to output JSON file")

    # task2 command
    task2_parser = subparsers.add_parser("task2", help="Validate Task 2 output file")
    task2_parser.add_argument("file", type=Path, help="Path to output JSON file")

    # check-dir command
    check_parser = subparsers.add_parser("check-dir", help="Check all outputs in directory")
    check_parser.add_argument("dir", type=Path, help="Path to output directory")
    check_parser.add_argument("--verbose", "-v", action="store_true", help="Show all errors")

    args = parser.parse_args()

    if args.command == "task1":
        result = validate_task1_file(args.file)
        _print_task1_result(result, str(args.file))
        return 0 if result.valid else 1

    elif args.command == "task2":
        result = validate_task2_file(args.file)
        _print_task2_result(result, str(args.file))
        return 0 if result.valid else 1

    elif args.command == "check-dir":
        stats = check_output_directory(args.dir, args.verbose)
        if "error" in stats:
            print(f"Error: {stats['error']}")
            return 1

        print("=" * 60)
        print("OUTPUT VALIDATION SUMMARY")
        print("=" * 60)

        for task, data in stats.items():
            total = data["valid"] + data["invalid"]
            pct = data["valid"] / total * 100 if total > 0 else 0
            print(f"\n{task.upper()}:")
            print(f"  Valid:   {data['valid']:>6} ({pct:.1f}%)")
            print(f"  Invalid: {data['invalid']:>6}")

            if data["errors"]:
                print(f"  Sample errors:")
                for err in data["errors"][:5]:
                    print(f"    - {err}")
                if len(data["errors"]) > 5:
                    print(f"    ... and {len(data['errors']) - 5} more")

        return 0


if __name__ == "__main__":
    sys.exit(main())
