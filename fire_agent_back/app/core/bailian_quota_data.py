"""
百炼账号免费额度数据（静态内置快照，2026-10-02 从控制台同步）

每条: {model, category, quota, expire, status}
  - model:    模型 Code
  - category: text(语言) / vision(视觉) / multimodal(全模态) / embedding(向量) / audio(语音)
  - quota:    免费额度剩余量（剩X/共Y）
  - expire:   过期时间（2099/01/01 = 每月1日额度重置 · 长期有效）
  - status:   状态（已开启）

控制台账号额度为登录态数据、无公开 API，按用户要求改为静态内置；
额度变动时直接更新本文件即可。
统计: 语言 12 / 视觉 5 / 全模态 3 / 向量 3 / 语音 67，共 90 条。
"""

_T = "text"
_V = "vision"
_MM = "multimodal"
_E = "embedding"
_A = "audio"


def _rows(category, items):
    return [{"model": m, "category": category, "quota": q, "expire": e, "status": "已开启"}
            for m, q, e in items]


_M = "剩1,000,000/共1,000,000"

# ===== 语言模型（12 个） =====
_TEXT_ROWS = _rows(_T, [
    ("qwen3.8-27b",                 _M, "2026/11/18"),
    ("qwen3.7-flash-2026-07-15",    _M, "2026/10/23"),
    ("qwen3.8-flash",               "剩928,170/共1,000,000",  "2026/11/25"),
    ("kimi-k3",                     _M, "2026/11/18"),
    ("deepseek-v4-flash-0731",      _M, "2026/10/31"),
    ("qwen3.8-max-0902",            _M, "2026/12/01"),
    ("deepseek-v4.1-flash",         "剩881,500/共1,000,000",  "2026/12/13"),
    ("glm-5.3",                     _M, "2026/11/23"),
    ("deepseek-v4-pro-0813",        _M, "2026/11/13"),
    ("qwen3.8-2.4t-a95b",           _M, "2026/11/12"),
    ("qwen3.8-max",                 "剩992,720/共1,000,000",  "2026/11/01"),
    ("qwen3.7-flash",               "剩195,080/共1,000,000",  "2026/10/23"),
])

# ===== 视觉模型（5 个） =====
_VISION_ROWS = _rows(_V, [
    ("qwen-image-3.0",      "剩5/共10",    "2026/11/03"),
    ("wan3.0-video",        "剩30/共30",   "2026/11/05"),
    ("qwen-image-3.0-pro",  "剩10/共10",   "2026/11/03"),
    ("qwen-mt-image-2.0",   "剩100/共100", "2026/11/27"),
    ("wan3.0-video-prime",  "剩30/共30",   "2026/11/21"),
])

# ===== 全模态模型（3 个） =====
_MULTIMODAL_ROWS = _rows(_MM, [
    ("qwen-mt-uni",                 _M, "2026/12/15"),
    ("qwen3.8-omni-flash",          "剩985,620/共1,000,000", "2026/12/17"),
    ("qwen3.8-omni-flash-realtime", _M, "2026/12/21"),
])

# ===== 向量模型（3 个） =====
_EMBEDDING_ROWS = _rows(_E, [
    ("qwen3.7-text-embedding-flash", _M, "2026/11/30"),
    ("qwen3.7-text-rerank",          _M, "2026/11/30"),
    ("qwen3.7-text-embedding",       _M, "2026/10/13"),
])

# ===== 语音模型（67 个） =====
_SAMBERT = ("剩30,000/共30,000", "2099/01/01")
_PARAFORMER = ("剩36,000/共36,000", "2099/01/01")
_COSYVOICE = ("剩10,000/共10,000", "2099/01/01")

_AUDIO_ROWS = _rows(_A, [
    # — 限期额度 —
    ("qwen-audio-3.0-tts-plus",                "剩10,000/共10,000", "2026/10/12"),
    ("qwen-audio-3.0-tts-flash",               "剩10,000/共10,000", "2026/10/12"),
    ("qwen-audio-3.0-asr-flash-streaming",     "剩36,000/共36,000", "2026/10/27"),
    ("qwen-audio-3.0-asr-flash",               "剩36,000/共36,000", "2026/10/27"),
    ("qwen-audio-3.0-asr-flash-filetrans",     "剩36,000/共36,000", "2026/10/27"),
    ("qwen3-asr-flash",                        "剩35,980/共36,000", "2026/11/24"),
    ("qwen3.8-livetranslate-flash-realtime",   _M, "2026/12/16"),
    ("qwen-audio-3.1-asr-flash-streaming",     _M, "2026/12/21"),
    ("qwen-audio-3.1-asr-flash-filetrans",     _M, "2026/12/21"),
    ("qwen-audio-3.1-tts-next",                _M, "2026/12/21"),
    ("qwen-audio-3.1-asr-flash-message",       _M, "2026/12/21"),
    ("qwen-audio-3.1-asr-flash",               _M, "2026/12/21"),
    ("qwen-audio-3.1-tts-flash",               _M, "2026/12/21"),
    # — 每月1日额度重置 · 长期有效 —
    ("sambert-zhide-v1",                    *_SAMBERT),
    ("paraformer-v2",                       *_PARAFORMER),
    ("paraformer-v1",                       *_PARAFORMER),
    ("sambert-zhida-v1",                    *_SAMBERT),
    ("sambert-zhishu-v1",                   *_SAMBERT),
    ("sambert-zhiyue-v1",                   *_SAMBERT),
    ("sambert-eva-v1",                      *_SAMBERT),
    ("paraformer-realtime-8k-v2",           *_PARAFORMER),
    ("paraformer-realtime-8k-v1",           *_PARAFORMER),
    ("sambert-beth-v1",                     *_SAMBERT),
    ("sambert-zhiye-v1",                    *_SAMBERT),
    ("sambert-zhiya-v1",                    *_SAMBERT),
    ("sambert-indah-v1",                    *_SAMBERT),
    ("sambert-cindy-v1",                    *_SAMBERT),
    ("paraformer-realtime-v2",              *_PARAFORMER),
    ("sambert-zhiying-v1",                  *_SAMBERT),
    ("paraformer-realtime-v1",              *_PARAFORMER),
    ("sambert-zhistella-v1",                *_SAMBERT),
    ("sambert-perla-v1",                    *_SAMBERT),
    ("sambert-zhihao-v1",                   *_SAMBERT),
    ("sambert-zhilun-v1",                   *_SAMBERT),
    ("sambert-zhichu-v1",                   *_SAMBERT),
    ("sambert-zhimao-v1",                   *_SAMBERT),
    ("sambert-zhigui-v1",                   *_SAMBERT),
    ("sambert-zhinan-v1",                   *_SAMBERT),
    ("sambert-zhixiao-v1",                  *_SAMBERT),
    ("sambert-zhimo-v1",                    *_SAMBERT),
    ("sambert-zhiming-v1",                  *_SAMBERT),
    ("sambert-brian-v1",                    *_SAMBERT),
    ("sambert-betty-v1",                    *_SAMBERT),
    ("sambert-donna-v1",                    *_SAMBERT),
    ("sambert-hanna-v1",                    *_SAMBERT),
    ("paraformer-8k-v1",                    *_PARAFORMER),
    ("sambert-zhiru-v1",                    *_SAMBERT),
    ("paraformer-8k-v2",                    *_PARAFORMER),
    ("sambert-zhiqi-v1",                    *_SAMBERT),
    ("cosyvoice-v1",                        *_COSYVOICE),
    ("sambert-zhiting-v1",                  *_SAMBERT),
    ("sambert-zhiyuan-v1",                  *_SAMBERT),
    ("sambert-zhixiang-v1",                 *_SAMBERT),
    ("paraformer-mtl-v1",                   *_PARAFORMER),
    ("sambert-zhifei-v1",                   *_SAMBERT),
    ("sambert-zhijia-v1",                   *_SAMBERT),
    ("sambert-clara-v1",                    *_SAMBERT),
    ("sambert-waan-v1",                     *_SAMBERT),
    ("sambert-camila-v1",                   *_SAMBERT),
    ("sambert-zhiwei-v1",                   *_SAMBERT),
    ("sambert-zhijing-v1",                  *_SAMBERT),
    ("sambert-cally-v1",                    *_SAMBERT),
    ("sambert-zhimiao-emo-v1",              *_SAMBERT),
    ("sambert-zhishuo-v1",                  *_SAMBERT),
    ("cosyvoice-clone-v1",                  *_COSYVOICE),
    ("sambert-zhiqian-v1",                  *_SAMBERT),
    ("sambert-zhina-v1",                    *_SAMBERT),
])

BAILIAN_ACCOUNT_QUOTA: list[dict] = [
    *_TEXT_ROWS,
    *_VISION_ROWS,
    *_MULTIMODAL_ROWS,
    *_EMBEDDING_ROWS,
    *_AUDIO_ROWS,
]

QUOTA_CATEGORY_LABELS = {
    "text": "语言模型",
    "vision": "视觉模型",
    "multimodal": "全模态模型",
    "embedding": "向量模型",
    "audio": "语音模型",
}


def get_bailian_account_quota() -> dict:
    """返回账号免费额度快照及分类统计"""
    counts = {k: 0 for k in QUOTA_CATEGORY_LABELS}
    for r in BAILIAN_ACCOUNT_QUOTA:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return {
        "snapshot_date": "2026-10-02",
        "total": len(BAILIAN_ACCOUNT_QUOTA),
        "counts": counts,
        "category_labels": QUOTA_CATEGORY_LABELS,
        "rows": BAILIAN_ACCOUNT_QUOTA,
    }
