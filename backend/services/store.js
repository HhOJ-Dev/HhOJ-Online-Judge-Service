/**
 * In-memory store for judge requests and results
 * In production, replace with Redis/MongoDB
 */

const judgeStore = new Map();
const wsManager = require('./wsManager');

class StoreService {
  /**
   * Save a judge request
   * @param {string} judgeId - The judge ID
   * @param {Object} data - The judge data
   */
  save(judgeId, data) {
    judgeStore.set(judgeId, {
      ...data,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });
  }

  /**
   * Get a judge request
   * @param {string} judgeId - The judge ID
   * @returns {Object|null} - The judge data
   */
  get(judgeId) {
    return judgeStore.get(judgeId) || null;
  }

  /**
   * Update a judge request
   * @param {string} judgeId - The judge ID
   * @param {Object} updates - The updates to apply
   */
  update(judgeId, updates) {
    const existing = judgeStore.get(judgeId);
    if (existing) {
      const updated = {
        ...existing,
        ...updates,
        updatedAt: new Date().toISOString()
      };
      judgeStore.set(judgeId, updated);

      // 通过 WebSocket 实时推送状态更新
      wsManager.notify(judgeId, {
        status: updated.status,
        conclusion: updated.conclusion,
        result: updated.result,
        updatedAt: updated.updatedAt
      });
    }
  }

  /**
   * Delete a judge request
   * @param {string} judgeId - The judge ID
   */
  delete(judgeId) {
    judgeStore.delete(judgeId);
  }

  /**
   * List all judge requests
   * @returns {Array} - All judge requests
   */
  list() {
    return Array.from(judgeStore.entries()).map(([id, data]) => ({
      judgeId: id,
      ...data
    }));
  }

  /**
   * List pending judge requests (for GitHub Actions to fetch)
   * @param {number} limit - Maximum number of submissions to return
   * @returns {Array} - Pending judge requests with full data
   */
  listPending(limit = 10) {
    const pending = [];
    for (const [id, data] of judgeStore.entries()) {
      if (data.status === 'pending' || data.status === 'queued') {
        pending.push({
          judgeId: id,
          ...data
        });
        if (pending.length >= limit) {
          break;
        }
      }
    }
    return pending;
  }

  /**
   * Clean up old entries (older than maxAge ms)
   * @param {number} maxAge - Maximum age in milliseconds
   */
  cleanup(maxAge = 3600000) { // Default 1 hour
    const now = Date.now();
    for (const [id, data] of judgeStore.entries()) {
      const age = now - new Date(data.createdAt).getTime();
      if (age > maxAge) {
        judgeStore.delete(id);
      }
    }
  }
}

module.exports = new StoreService();