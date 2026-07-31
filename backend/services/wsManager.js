/**
 * WebSocket manager for real-time judge status push
 * 使用 ws 库实现，避免轮询延迟
 * 支持消息缓冲：晚连接的客户端可以收到最新状态
 */

const clients = new Map(); // judgeId -> Set<WebSocket>
const lastMessages = new Map(); // judgeId -> last status message (for late subscribers)

class WsManager {
  /**
   * Subscribe a WebSocket connection to a judgeId
   */
  subscribe(judgeId, ws) {
    if (!clients.has(judgeId)) {
      clients.set(judgeId, new Set());
    }
    clients.get(judgeId).add(ws);

    // Replay last known status for late subscribers
    const lastMsg = lastMessages.get(judgeId);
    if (lastMsg && ws.readyState === 1) {
      ws.send(JSON.stringify(lastMsg));
    }

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
   * Also buffers the message for late subscribers
   */
  notify(judgeId, data) {
    const message = {
      type: 'judge_update',
      judgeId,
      data,
      timestamp: new Date().toISOString()
    };

    // Always buffer the latest message for late subscribers
    lastMessages.set(judgeId, message);

    const set = clients.get(judgeId);
    if (!set || set.size === 0) {
      return;
    }

    const payload = JSON.stringify(message);

    for (const ws of set) {
      if (ws.readyState === 1) { // OPEN
        ws.send(payload);
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
