"""调 DeepSeek：全项目唯一发起对外网络请求的文件。

只把「提示词 + 搜到的那几条记录」发出去，整库永远不出本机。
"""

import httpx

from .. import config


class LLMError(Exception):
    """带 HTTP 状态码的模型调用错误，接口层直接翻译成响应。"""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


def available() -> bool:
    return bool(config.DEEPSEEK_API_KEY.strip())


def chat(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 600,
) -> str:
    """发一次对话请求，返回纯文本。出错一律抛 LLMError（人话）。"""
    if not available():
        raise LLMError("还没配置 DEEPSEEK_API_KEY，把 Key 填进 .env 再重启", 503)

    url = config.LLM_BASE.rstrip("/") + "/chat/completions"
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {config.DEEPSEEK_API_KEY.strip()}"}

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=60)
    except httpx.TimeoutException:
        raise LLMError("模型接口 60 秒没响应，稍后再试", 504)
    except httpx.HTTPError as exc:
        raise LLMError(f"连不上模型接口：{exc.__class__.__name__}", 502)

    if resp.status_code == 401:
        raise LLMError("API Key 不对，检查 .env 里的 DEEPSEEK_API_KEY", 502)
    if resp.status_code == 402:
        raise LLMError("DeepSeek 账户余额不足，去 platform.deepseek.com 充值", 502)
    if resp.status_code == 429:
        raise LLMError("请求太频繁，等几秒再问", 502)
    if resp.status_code >= 400:
        raise LLMError(f"模型接口返回 {resp.status_code}：{resp.text[:120]}", 502)

    try:
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError):
        raise LLMError("模型返回的格式看不懂，可能是接口地址填错了", 502)
