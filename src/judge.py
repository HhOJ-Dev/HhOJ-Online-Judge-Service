<?php
/**
 * 评测触发器入口
 *
 * 评测机 API Key 全部从 judge_runners 表读取（多评测机支持）。
 * triggerJudge 内部按 priority 选评测机，失败自动 fallback。
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/functions.php';

function judge_response(int $code, array $payload): void
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE);
    exit;
}

if (empty(collectJudgeApiKeys())) {
    judge_response(500, ['error' => '系统错误: 未配置任何评测机的 API Key，请在后台 /admin 添加。']);
}

$providedKey = extractJudgeApiKeyFromRequest();
if (!verifyJudgeApiKey($providedKey)) {
    judge_response(403, ['error' => 'Forbidden: Invalid API Key']);
}

// 可选 runner_id 指定评测机
$runnerId = null;
if (isset($_GET['runner_id'])) {
    $rid = (int)$_GET['runner_id'];
    if ($rid > 0) {
        $runnerId = $rid;
    }
}

$r = triggerJudge($runnerId);
if ($r['success']) {
    $extra = ['runner_id' => $r['runner_id'], 'runner_name' => $r['runner_name']];
    if ($r['reason'] === 'throttled') {
        judge_response(200, array_merge(['success' => true, 'message' => '评测任务已触发（节流合并）'], $extra));
    }
    judge_response(200, array_merge([
        'success' => true,
        'message' => '评测任务已成功触发！',
        'details' => "已触发评测机「{$r['runner_name']}」，请前往 GitHub Actions 页面查看进度。",
    ], $extra));
}

judge_response(502, [
    'success' => false,
    'error'  => $r['message'],
    'reason' => $r['reason'],
]);
