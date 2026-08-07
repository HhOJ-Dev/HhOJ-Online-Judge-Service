/**
 * HhOJ API Usage Examples
 * 
 * This file demonstrates how to use the HhOJ Backend API
 */

const API_BASE = 'http://localhost:3000/api';

// Example 1: Submit C++ code for judging
async function submitCppCode() {
  const response = await fetch(`${API_BASE}/judge`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      language: 'cpp',
      code: `#include <iostream>
using namespace std;

int main() {
    int a, b;
    cin >> a >> b;
    cout << a + b << endl;
    return 0;
}`,
      testcases: [
        {
          input: '1 2',
          output: '3'
        },
        {
          input: '5 10',
          output: '15'
        },
        {
          input: '-1 1',
          output: '0'
        }
      ],
      config: {
        timeLimit: 2000,
        memoryLimit: 256
      }
    })
  });

  const result = await response.json();
  console.log('Submit result:', result);
  return result.data.judgeId;
}

// Example 2: Submit Python code
async function submitPythonCode() {
  const response = await fetch(`${API_BASE}/judge`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      language: 'python',
      code: `import sys

def main():
    for line in sys.stdin:
        a, b = map(int, line.split())
        print(a + b)

if __name__ == '__main__':
    main()`,
      testcases: [
        {
          input: '1 2',
          output: '3'
        },
        {
          input: '100 200',
          output: '300'
        }
      ]
    })
  });

  const result = await response.json();
  console.log('Python result:', result);
  return result.data.judgeId;
}

// Example 3: Check judge status
async function checkStatus(judgeId) {
  const response = await fetch(`${API_BASE}/status/${judgeId}`);
  const result = await response.json();
  console.log('Status:', result);
  return result.data;
}

// Example 4: Get judge result
async function getResult(judgeId) {
  const response = await fetch(`${API_BASE}/result/${judgeId}`);
  const result = await response.json();
  console.log('Result:', result);
  return result.data;
}

// Example 5: Poll until completion
async function pollUntilComplete(judgeId, maxAttempts = 60, intervalMs = 5000) {
  for (let i = 0; i < maxAttempts; i++) {
    const status = await checkStatus(judgeId);
    
    if (status.status === 'completed') {
      return await getResult(judgeId);
    }
    
    if (status.status === 'error') {
      throw new Error('Judge failed');
    }
    
    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  
  throw new Error('Timeout waiting for judge to complete');
}

// Main execution
async function main() {
  try {
    console.log('=== Submitting C++ code ===');
    const judgeId = await submitCppCode();
    
    console.log('\n=== Checking status ===');
    await checkStatus(judgeId);
    
    console.log('\n=== Waiting for completion ===');
    const result = await pollUntilComplete(judgeId);
    console.log('\n=== Final result ===');
    console.log(JSON.stringify(result, null, 2));
    
  } catch (error) {
    console.error('Error:', error);
  }
}

// Run if executed directly
if (require.main === module) {
  main();
}

module.exports = {
  submitCppCode,
  submitPythonCode,
  checkStatus,
  getResult,
  pollUntilComplete
};