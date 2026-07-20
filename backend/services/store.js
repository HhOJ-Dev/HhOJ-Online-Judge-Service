/**
 * In-memory store for judge requests and results
 * In production, replace with Redis/MongoDB
 */

const judgeStore = new Map();

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
      judgeStore.set(judgeId, {
        ...existing,
        ...updates,
        updatedAt: new Date().toISOString()
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