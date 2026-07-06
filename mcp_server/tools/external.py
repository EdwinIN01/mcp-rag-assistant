"""外部工具：网络搜索、当前时间等，作为 MCP 工具补充。"""
import datetime
import json
import urllib.request


def web_search(query: str, top_k: int = 5) -> str:
    """简易网络搜索（基于 DuckDuckGo HTML），返回摘要 JSON。

    Args:
        query: 搜索关键词
        top_k: 返回结果数量
    """
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # 简易解析：提取结果链接文本
        import re
        results = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)[:top_k]
        clean = [re.sub(r"<[^>]+>", "", r).strip() for r in results]
        return json.dumps(clean, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def current_time() -> str:
    """返回当前时间。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
