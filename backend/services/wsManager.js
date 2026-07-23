/**
 * WebSocket manager for real-time judge status push
 * 使用 ws 库实现，避免轮询延迟
 */

const clients = new Map(); // judgeId -> Set<WebSocket>

class WsManager {
  /**
   * Subscribe a WebSocket connection to a judgeId
   */
  subscribe(judgeId, ws) {
    if (!clients.has(judgeId)) {
      clients.set(judgeId, new Set());
    }
    clients.get(judgeId).add(ws);

    ws.on('close', () => {
      this.unsubscribe(judgeId, ws);
    });
    ws.on('error', () => {
      this.unsubscribe(judgeId, ws);
    });
  }

  /**
   * Unsubscribe a WebSocket connection
   */
  unsubscribe(judgeId, ws) {
    const set = clients.get(judgeId);
    if (set) {
      set.delete(ws);
      if (set.size === 0) {
        clients.delete(judgeId);
      }
    }
  }

  /**
   * Push status update to all subscribers of a judgeId
   */
  notify(judgeId, data) {
    const set = clients.get(judgeId);
    if (!set || set.size === 0) {
      return;
    }

    const message = JSON.stringify({
      type: 'judge_update',
      judgeId,
      data,
      timestamp: new Date().toISOString()
    });

    for (const ws of set) {
      if (ws.readyState === 1) { // OPEN
        ws.send(message);
      }
    }
  }

  /**
   * Get subscriber count for a judgeId
   */
  getSubscriberCount(judgeId) {
    return clients.get(judgeId)?.size || 0;
  }
}

module.exports = new WsManager();
