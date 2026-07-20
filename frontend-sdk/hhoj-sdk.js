/**
 * HhOJ Frontend SDK
 * 
 * Usage in frontend:
 * import { HhOJClient } from './hhoj-sdk.js';
 * 
 * const client = new HhOJClient('http://your-backend-url:3000');
 * const result = await client.judge('cpp', code, testcases);
 */

class HhOJClient {
  constructor(baseUrl, options = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.options = {
      pollInterval: options.pollInterval || 3000,
      maxPollAttempts: options.maxPollAttempts || 100,
      timeout: options.timeout || 300000, // 5 minutes default
    };
  }

  /**
   * Submit code for judging
   * @param {string} language - Programming language (cpp, c, python, java, go, rust, javascript, csharp)
   * @param {string} code - Source code
   * @param {Array<{input: string, output: string}>} testcases - Test cases
   * @param {Object} config - Optional config (timeLimit, memoryLimit)
   * @returns {Promise<{judgeId: string, runId: string}>}
   */
  async submit(language, code, testcases, config = {}) {
    const response = await fetch(`${this.baseUrl}/api/judge`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        language,
        code,
        testcases,
        config,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to submit code');
    }

    const result = await response.json();
    return result.data;
  }

  /**
   * Get judge status
   * @param {string} judgeId - Judge ID
   * @returns {Promise<Object>}
   */
  async getStatus(judgeId) {
    const response = await fetch(`${this.baseUrl}/api/status/${judgeId}`);
    
    if (!response.ok) {
      throw new Error('Failed to get status');
    }

    const result = await response.json();
    return result.data;
  }

  /**
   * Get judge result
   * @param {string} judgeId - Judge ID
   * @returns {Promise<Object>}
   */
  async getResult(judgeId) {
    const response = await fetch(`${this.baseUrl}/api/result/${judgeId}`);
    
    if (!response.ok) {
      throw new Error('Failed to get result');
    }

    const result = await response.json();
    return result.data;
  }

  /**
   * Submit and wait for result (convenience method)
   * @param {string} language - Programming language
   * @param {string} code - Source code
   * @param {Array} testcases - Test cases
   * @param {Object} config - Optional config
   * @param {Function} onProgress - Progress callback (status updates)
   * @returns {Promise<Object>} - Final result
   */
  async judge(language, code, testcases, config = {}, onProgress = null) {
    // Submit
    const { judgeId } = await this.submit(language, code, testcases, config);
    
    // Poll for result
    const startTime = Date.now();
    let attempts = 0;

    while (attempts < this.options.maxPollAttempts) {
      // Check timeout
      if (Date.now() - startTime > this.options.timeout) {
        throw new Error('Judge timeout');
      }

      // Get status
      const status = await this.getStatus(judgeId);
      
      // Report progress
      if (onProgress) {
        onProgress(status);
      }

      // Check if completed
      if (status.status === 'completed') {
        return await this.getResult(judgeId);
      }

      if (status.status === 'error') {
        throw new Error(status.error || 'Judge failed');
      }

      // Wait before next poll
      await new Promise(resolve => setTimeout(resolve, this.options.pollInterval));
      attempts++;
    }

    throw new Error('Max poll attempts reached');
  }

  /**
   * Get list of all judge requests
   * @returns {Promise<Array>}
   */
  async list() {
    const response = await fetch(`${this.baseUrl}/api/list`);
    
    if (!response.ok) {
      throw new Error('Failed to get list');
    }

    const result = await response.json();
    return result.data;
  }
}

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { HhOJClient };
}

if (typeof window !== 'undefined') {
  window.HhOJClient = HhOJClient;
}

export { HhOJClient };