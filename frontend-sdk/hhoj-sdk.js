/**
 * HhOJ Frontend SDK
 *
 * Usage in frontend:
 * import { HhOJClient } from './hhoj-sdk.js';
 *
 * const client = new HhOJClient('http://your-backend-url:3000');
 * const result = await client.judge('cpp', code, testcases);
 *
 * // 使用 WebSocket 实时推送（推荐，延迟更低）
 * const result = await client.judgeWithWebSocket('cpp', code, testcases, {}, (status) => {
 *   console.log('实时状态:', status);
 * });
 */

class HhOJClient {
  constructor(baseUrl, options = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    // WebSocket URL: http(s):// -> ws(s)://
    this.wsBaseUrl = this.baseUrl.replace(/^http/, 'ws');
    this.options = {
      pollInterval: options.pollInterval || 1000,
      maxPollAttempts: options.maxPollAttempts || 300,
      timeout: options.timeout || 300000, // 5 minutes default
      useWebSocket: options.useWebSocket !== false, // 默认使用 WebSocket
    };
  }

  /**
   * Submit code for judging
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
   * 使用 WebSocket 实时接收评测结果（推荐）
   * 评测完成后服务端主动推送，无需轮询
   */
  async judgeWithWebSocket(language, code, testcases, config = {}, onProgress = null) {
    // 先提交代码
    const { judgeId } = await this.submit(language, code, testcases, config);

    return new Promise((resolve, reject) => {
      const wsUrl = `${this.wsBaseUrl}/ws?judgeId=${judgeId}`;
      let ws;

      try {
        ws = new WebSocket(wsUrl);
      } catch (e) {
        // WebSocket 不可用，回退到轮询
        return this._judgeWithPolling(judgeId, onProgress).then(resolve, reject);
      }

      const timeout = setTimeout(() => {
        ws.close();
        reject(new Error('Judge timeout'));
      }, this.options.timeout);

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === 'connected') {
            // 连接成功
            if (onProgress) onProgress({ status: 'connected' });
            return;
          }

          if (msg.type === 'judge_update') {
            const data = msg.data;

            if (onProgress) onProgress(data);

            if (data.status === 'completed') {
              clearTimeout(timeout);
              ws.close();
              // 获取完整结果
              this.getResult(judgeId).then(resolve, reject);
            } else if (data.status === 'error') {
              clearTimeout(timeout);
              ws.close();
              reject(new Error(data.error || 'Judge failed'));
            }
          }
        } catch (e) {
          // 忽略解析错误
        }
      };

      ws.onerror = () => {
        clearTimeout(timeout);
        // WebSocket 出错，回退到轮询
        this._judgeWithPolling(judgeId, onProgress).then(resolve, reject);
      };

      ws.onclose = (event) => {
        clearTimeout(timeout);
        if (event.code !== 1000 && !event.wasClean) {
          // 非正常关闭，回退到轮询
          this._judgeWithPolling(judgeId, onProgress).then(resolve, reject);
        }
      };
    });
  }

  /**
   * 轮询方式获取结果（fallback）
   */
  async _judgeWithPolling(judgeId, onProgress = null) {
    const startTime = Date.now();
    let attempts = 0;

    while (attempts < this.options.maxPollAttempts) {
      if (Date.now() - startTime > this.options.timeout) {
        throw new Error('Judge timeout');
      }

      const status = await this.getStatus(judgeId);

      if (onProgress) {
        onProgress(status);
      }

      if (status.status === 'completed') {
        return await this.getResult(judgeId);
      }

      if (status.status === 'error') {
        throw new Error(status.error || 'Judge failed');
      }

      await new Promise(resolve => setTimeout(resolve, this.options.pollInterval));
      attempts++;
    }

    throw new Error('Max poll attempts reached');
  }

  /**
   * Submit and wait for result (自动选择 WebSocket 或轮询)
   */
  async judge(language, code, testcases, config = {}, onProgress = null) {
    if (this.options.useWebSocket && typeof WebSocket !== 'undefined') {
      return this.judgeWithWebSocket(language, code, testcases, config, onProgress);
    }
    // 回退到轮询
    const { judgeId } = await this.submit(language, code, testcases, config);
    return this._judgeWithPolling(judgeId, onProgress);
  }

  /**
   * Get list of all judge requests
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
