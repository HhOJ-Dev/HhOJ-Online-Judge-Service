#!/usr/bin/env python3
import os
import sys
import json
import re
import glob
from pathlib import Path

from runners import create_runner, get_supported_languages

JUDGE_STATUS = {
    "AC": "Accepted",
    "WA": "Wrong Answer",
    "TLE": "Time Limit Exceeded",
    "MLE": "Memory Limit Exceeded",
    "RE": "Runtime Error",
    "CE": "Compilation Error",
    "UKE": "Unknown Error",
}

DEFAULT_TIME_LIMIT = 2.0
DEFAULT_MEMORY_LIMIT = 262144

def compare_output(user_output: str, expected_output: str) -> bool:
    def normalize(text: str) -> list[str]:
        return [line.rstrip() for line in text.strip().splitlines()]

    user_lines = normalize(user_output)
    expected_lines = normalize(expected_output)

    if len(user_lines) != len(expected_lines):
        return False

    for u, e in zip(user_lines, expected_lines):
        if u.split() != e.split():
            return False

    return True

def find_test_cases() -> list[tuple[int, str, str]]:
    test_cases = []
    input_files = glob.glob("testcase*.in")

    for in_file in input_files:
        match = re.search(r"testcase(\d+)\.in", in_file)
        if not match:
            continue
        num = int(match.group(1))
        out_file = f"testcase{num}.out"
        if os.path.exists(out_file):
            test_cases.append((num, in_file, out_file))

    test_cases.sort(key=lambda x: x[0])
    return test_cases

def judge(
    language: str,
    source_file: str = None,
    time_limit: float = DEFAULT_TIME_LIMIT,
    memory_limit: int = DEFAULT_MEMORY_LIMIT,
) -> dict:
    result = {
        "status": "UKE",
        "total": 0,
        "passed": 0,
        "time": 0.0,
        "memory": 0,
        "error_msg": "",
        "test_cases": [],
        "language": language,
    }

    try:
        runner = create_runner(language, source_file, time_limit, memory_limit)
    except ValueError as e:
        result["status"] = "UKE"
        result["error_msg"] = str(e)
        return result

    compile_ok, compile_err = runner.compile()
    if not compile_ok:
        result["status"] = "CE"
        result["error_msg"] = compile_err
        return result

    test_cases = find_test_cases()
    if not test_cases:
        result["status"] = "UKE"
        result["error_msg"] = "No test cases found"
        return result

    result["total"] = len(test_cases)
    final_status = "AC"
    total_time = 0.0
    max_memory = 0

    for num, in_file, expected_file in test_cases:
        user_out_file = f"ans{num}.out"
        status, run_time, memory, error_msg = runner.run(in_file, user_out_file)

        tc_result = {
            "num": num,
            "status": status,
            "time": run_time,
            "memory": memory,
            "error_msg": error_msg,
        }

        if status == "AC":
            mem_usage, mem_err = runner.measure_memory(in_file)
            if mem_usage > memory_limit:
                status = "MLE"
                tc_result["status"] = "MLE"
                tc_result["error_msg"] = f"Memory Limit Exceeded ({mem_usage}KB)"
            else:
                tc_result["memory"] = mem_usage
                max_memory = max(max_memory, mem_usage)

                try:
                    with open(user_out_file, "r") as f_user, open(expected_file, "r") as f_expected:
                        user_output = f_user.read()
                        expected_output = f_expected.read()
                    if not compare_output(user_output, expected_output):
                        status = "WA"
                        tc_result["status"] = "WA"
                        tc_result["error_msg"] = "Wrong Answer"
                except Exception as e:
                    status = "UKE"
                    tc_result["status"] = "UKE"
                    tc_result["error_msg"] = str(e)

        result["test_cases"].append(tc_result)
        total_time += run_time

        if status != "AC":
            final_status = status
            result["error_msg"] = tc_result["error_msg"]
            break
        else:
            result["passed"] += 1

    result["status"] = final_status
    result["time"] = total_time
    result["memory"] = max_memory

    return result

def write_summary(result: dict, summary_file: str = "summary.md"):
    with open(summary_file, "w") as f:
        f.write("## HhOJ Judge Result\n\n")
        status = result["status"]
        status_text = JUDGE_STATUS.get(status, status)
        f.write(f"**Language**: {result.get('language', 'Unknown')}\n\n")
        f.write(f"**Verdict**: {status_text} ({status})\n\n")

        if status == "CE":
            f.write("**Compilation Error Log:**\n\n")
            f.write("```\n")
            f.write(result.get("error_msg", "")[:2000])
            f.write("\n```\n")
        elif status == "AC":
            f.write("All test cases passed successfully!\n\n")
            f.write(f"**Test Results**: {result['passed']} / {result['total']} passed\n")
            f.write(f"**Total Time**: {result['time']:.3f}s\n")
            f.write(f"**Max Memory**: {result['memory']}KB\n")
        elif status in ("WA", "TLE", "MLE", "RE"):
            f.write(f"**Details**: {result.get('error_msg', '')}\n\n")
            f.write(f"**Test Results**: {result['passed']} / {result['total']} passed\n")
        else:
            f.write(f"**Details**: {result.get('error_msg', 'Unknown error')}\n")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="HhOJ Judge")
    parser.add_argument("--language", required=True, help=f"Programming language. Supported: {get_supported_languages()}")
    parser.add_argument("--source", help="Source file to judge (optional, auto-detected based on language)")
    parser.add_argument("--time-limit", type=float, default=DEFAULT_TIME_LIMIT, help="Time limit in seconds")
    parser.add_argument("--memory-limit", type=int, default=DEFAULT_MEMORY_LIMIT, help="Memory limit in KB")
    parser.add_argument("--output", default="judge_result.json", help="Output JSON file")
    parser.add_argument("--summary", default="summary.md", help="Summary markdown file")
    args = parser.parse_args()

    result = judge(args.language, args.source, args.time_limit, args.memory_limit)

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    write_summary(result, args.summary)

    with open("status.txt", "w") as f:
        f.write(result["status"])

    print(f"Judge result: {result['status']}")
    print(f"Language: {result['language']}")
    print(f"Passed: {result['passed']} / {result['total']}")
    if result["error_msg"]:
        print(f"Error: {result['error_msg']}")

    return 0 if result["status"] == "AC" else 1

if __name__ == "__main__":
    sys.exit(main())