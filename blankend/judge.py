#!/usr/bin/env python3

import os
import sys
import json
import subprocess
import argparse
import tempfile
import signal
import requests
import time

RESULT_AC = 'AC'
RESULT_WA = 'WA'
RESULT_TLE = 'TLE'
RESULT_MLE = 'MLE'
RESULT_RE = 'RE'
RESULT_CE = 'CE'
RESULT_UKE = 'UKE'

def run_command(cmd, timeout=5, memory_limit=None, input_data=None):
    try:
        env = os.environ.copy()
        if memory_limit:
            env['MEM_LIMIT'] = str(memory_limit)
        
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True
        )
        
        start_time = time.time()
        try:
            stdout, stderr = process.communicate(input=input_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return None, None, 'TLE'
        
        elapsed = time.time() - start_time
        
        returncode = process.returncode
        
        if returncode != 0:
            return stdout, stderr, 'RE'
        
        return stdout, stderr, 'OK'
        
    except Exception as e:
        return None, str(e), 'UKE'

def compile_code(language, code):
    with tempfile.TemporaryDirectory() as tmpdir:
        if language == 'cpp':
            src_path = os.path.join(tmpdir, 'main.cpp')
            exe_path = os.path.join(tmpdir, 'main')
            with open(src_path, 'w') as f:
                f.write(code)
            cmd = ['g++', '-O2', '-std=c++17', src_path, '-o', exe_path]
            stdout, stderr, status = run_command(cmd, timeout=30)
            if status != 'OK':
                return None, stderr or stdout, RESULT_CE
            return exe_path, None, RESULT_AC
            
        elif language == 'c':
            src_path = os.path.join(tmpdir, 'main.c')
            exe_path = os.path.join(tmpdir, 'main')
            with open(src_path, 'w') as f:
                f.write(code)
            cmd = ['gcc', '-O2', '-std=c11', src_path, '-o', exe_path]
            stdout, stderr, status = run_command(cmd, timeout=30)
            if status != 'OK':
                return None, stderr or stdout, RESULT_CE
            return exe_path, None, RESULT_AC
            
        elif language == 'python':
            src_path = os.path.join(tmpdir, 'main.py')
            with open(src_path, 'w') as f:
                f.write(code)
            return src_path, None, RESULT_AC
            
        elif language == 'java':
            src_path = os.path.join(tmpdir, 'Main.java')
            with open(src_path, 'w') as f:
                f.write(code)
            cmd = ['javac', src_path]
            stdout, stderr, status = run_command(cmd, timeout=30)
            if status != 'OK':
                return None, stderr or stdout, RESULT_CE
            return tmpdir, None, RESULT_AC
            
        elif language == 'go':
            src_path = os.path.join(tmpdir, 'main.go')
            exe_path = os.path.join(tmpdir, 'main')
            with open(src_path, 'w') as f:
                f.write(code)
            cmd = ['go', 'build', '-o', exe_path, src_path]
            stdout, stderr, status = run_command(cmd, timeout=60)
            if status != 'OK':
                return None, stderr or stdout, RESULT_CE
            return exe_path, None, RESULT_AC
            
        elif language == 'rust':
            src_path = os.path.join(tmpdir, 'src')
            os.makedirs(src_path, exist_ok=True)
            src_file = os.path.join(src_path, 'main.rs')
            with open(src_file, 'w') as f:
                f.write(code)
            with open(os.path.join(tmpdir, 'Cargo.toml'), 'w') as f:
                f.write('[package]\nname = "judge"\nversion = "0.1.0"\nedition = "2021"\n')
            cmd = ['cargo', 'build', '--release', '--target-dir', os.path.join(tmpdir, 'target')]
            stdout, stderr, status = run_command(cmd, timeout=120)
            if status != 'OK':
                return None, stderr or stdout, RESULT_CE
            return os.path.join(tmpdir, 'target', 'release', 'judge'), None, RESULT_AC
            
        elif language == 'javascript':
            src_path = os.path.join(tmpdir, 'main.js')
            with open(src_path, 'w') as f:
                f.write(code)
            return src_path, None, RESULT_AC
            
        elif language == 'csharp':
            src_path = os.path.join(tmpdir, 'main.cs')
            exe_path = os.path.join(tmpdir, 'main.exe')
            with open(src_path, 'w') as f:
                f.write(code)
            cmd = ['csc', '/out:' + exe_path, src_path]
            stdout, stderr, status = run_command(cmd, timeout=30)
            if status != 'OK':
                return None, stderr or stdout, RESULT_CE
            return exe_path, None, RESULT_AC
            
        else:
            return None, f'Unsupported language: {language}', RESULT_UKE

def run_testcase(executable, language, input_data, expected_output, time_limit, memory_limit):
    timeout = time_limit / 1000.0 + 1.0
    
    if language == 'cpp' or language == 'c':
        stdout, stderr, status = run_command([executable], timeout=timeout, input_data=input_data)
    elif language == 'python':
        stdout, stderr, status = run_command(['python3', executable], timeout=timeout, input_data=input_data)
    elif language == 'java':
        stdout, stderr, status = run_command(['java', '-cp', executable, 'Main'], timeout=timeout, input_data=input_data)
    elif language == 'go':
        stdout, stderr, status = run_command([executable], timeout=timeout, input_data=input_data)
    elif language == 'rust':
        stdout, stderr, status = run_command([executable], timeout=timeout, input_data=input_data)
    elif language == 'javascript':
        stdout, stderr, status = run_command(['node', executable], timeout=timeout, input_data=input_data)
    elif language == 'csharp':
        stdout, stderr, status = run_command(['mono', executable], timeout=timeout, input_data=input_data)
    else:
        return RESULT_UKE, None, None
    
    if status == 'TLE':
        return RESULT_TLE, None, None
    if status == 'RE':
        return RESULT_RE, stdout, stderr
    if status == 'UKE':
        return RESULT_UKE, None, stderr
    
    actual_output = stdout.strip()
    expected_stripped = expected_output.strip()
    
    if actual_output == expected_stripped:
        return RESULT_AC, actual_output, None
    else:
        return RESULT_WA, actual_output, None

def judge_submission(submission):
    result = {
        'id': submission['id'],
        'status': 'running',
        'testcases': [],
        'total': len(submission['testcases']),
        'passed': 0
    }
    
    language = submission['language']
    code = submission['code']
    testcases = submission['testcases']
    time_limit = submission.get('time_limit', 2000)
    memory_limit = submission.get('memory_limit', 256)
    
    executable, compile_error, compile_status = compile_code(language, code)
    
    if compile_status != RESULT_AC:
        result['status'] = compile_status
        result['compile_error'] = compile_error
        result['passed'] = 0
        return result
    
    passed = 0
    for i, tc in enumerate(testcases):
        tc_result = run_testcase(
            executable, language, 
            tc['input'], tc['output'], 
            time_limit, memory_limit
        )
        
        test_result = {
            'index': i,
            'status': tc_result[0],
            'input': tc['input'],
            'expected': tc['output'],
            'actual': tc_result[1],
            'error': tc_result[2]
        }
        result['testcases'].append(test_result)
        
        if tc_result[0] == RESULT_AC:
            passed += 1
        
        if tc_result[0] not in (RESULT_AC, RESULT_WA):
            result['status'] = tc_result[0]
            break
    
    if result['status'] == 'running':
        result['status'] = RESULT_AC if passed == len(testcases) else RESULT_WA
    
    result['passed'] = passed
    
    return result

def send_result(host, api_key, judge_id, result):
    url = f"{host}/api/callback"
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': api_key
    }
    data = {
        'judgeId': judge_id,
        'result': result
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to send result: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='HhOJ Judge Script')
    parser.add_argument('--api-key', required=True, help='API key')
    parser.add_argument('--host', required=True, help='Backend host')
    parser.add_argument('--submissions', required=True, help='Path to submissions JSON file')
    
    args = parser.parse_args()
    
    with open(args.submissions, 'r') as f:
        data = json.load(f)
    
    if not data.get('success'):
        print(f"API error: {data.get('message', 'Unknown')}", file=sys.stderr)
        return
    
    submissions = data.get('submissions', [])
    
    results = []
    for submission in submissions:
        print(f"Judging submission {submission['id']}...")
        judge_result = judge_submission(submission)
        results.append(judge_result)
        
        print(f"Result: {judge_result['status']} ({judge_result['passed']}/{judge_result['total']})")
        
        send_result(args.host, args.api_key, submission['id'], judge_result)
    
    with open('../judge_result.json', 'w') as f:
        json.dump(results, f)
    
    with open('../status.txt', 'w') as f:
        f.write('SUCCESS' if results else 'SKIP')
    
    with open('../summary.md', 'w') as f:
        f.write('## HhOJ Judge Result\n\n')
        if results:
            for r in results:
                f.write(f"**Submission**: {r['id']}\n")
                f.write(f"**Status**: {r['status']}\n")
                f.write(f"**Result**: {r['passed']}/{r['total']} test cases passed\n\n")
        else:
            f.write("**Status**: No submissions to judge\n")

if __name__ == '__main__':
    main()