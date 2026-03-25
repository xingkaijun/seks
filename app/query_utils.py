import re
from typing import Iterable, Tuple


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_NUMERIC_NOISE_RE = re.compile(r"^[\d\s.,;:()\[\]/+\-–—%*xX=<>#°]+$")
_IDENTIFIER_RE = re.compile(r"[A-Za-z]+(?:[-_/][A-Za-z0-9]+)+|[A-Za-z]{2,}\d+(?:[-_][A-Za-z0-9]+)*")
_TABLE_OF_CONTENTS_RE = re.compile(r"\.{8,}|table of contents|contents", re.IGNORECASE)


def question_type(question: str) -> str:
    q = question.lower()
    if any(k in question for k in ["多少种", "清单", "列表", "有哪些", "哪几种"]):
        return "list"
    if any(k in question for k in ["容量", "电压", "功率", "压力", "温度", "数量", "参数", "范围", "多大", "几台", "多少台", "额定输出"]):
        return "param"
    if any(k in q for k in ["capacity", "rated output", "quantity", "how many", "kw", "kwe", "generator size"]):
        return "param"
    return "general"


def expand_question_queries(question: str) -> list[str]:
    # 移除特定工程领域的硬编码扩展词，仅保留原问题，系统已具备通用关键词提取和向量检索能力
    queries: list[str] = [question.strip()]
    return queries


def keyword_terms(question: str) -> set[str]:
    keywords: set[str] = set()
    for query in expand_question_queries(question):
        lowered = query.lower()
        for token in re.findall(r"[a-zA-Z]{3,}|\d+|[\u4e00-\u9fff]{2,}", lowered):
            if token not in {"what", "which", "with", "for", "the", "and", "are", "有哪些", "什么"}:
                keywords.add(token)
        for token in _IDENTIFIER_RE.findall(query):
            keywords.add(token.lower())
    return keywords


def exactish_terms(question: str) -> set[str]:
    terms: set[str] = set()
    stripped = question.strip()
    if stripped:
        for token in _IDENTIFIER_RE.findall(stripped):
            terms.add(token.lower())
        if re.search(r"\d", stripped) and re.search(r"[A-Za-z\u4e00-\u9fff]", stripped):
            terms.add(stripped.lower())
    return terms


def is_noisy_chunk(text: str) -> bool:
    raw = text.strip()
    if not raw:
        return True
    if len(raw) < 30:
        return True

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return True

    numeric_like = 0
    alpha_cjk_chars = 0
    digit_chars = 0
    short_symbolic_lines = 0
    for line in lines:
        compact = line.replace(" ", "")
        if _NUMERIC_NOISE_RE.match(compact):
            numeric_like += 1
        if len(compact) <= 16 and _NUMERIC_NOISE_RE.match(compact):
            short_symbolic_lines += 1
        alpha_cjk_chars += sum(1 for ch in line if ch.isalpha() or _CJK_RE.match(ch))
        digit_chars += sum(1 for ch in line if ch.isdigit())

    raw_lower = raw.lower()
    if _TABLE_OF_CONTENTS_RE.search(raw_lower):
        return True
    if short_symbolic_lines / max(len(lines), 1) >= 0.5:
        return True
    if numeric_like / max(len(lines), 1) >= 0.6:
        return True
    if alpha_cjk_chars == 0:
        return True
    if digit_chars > alpha_cjk_chars * 1.2:
        return True
    return False


def apply_light_rerank(
    question: str,
    hits: Iterable,
    *,
    return_debug: bool = False,
) -> Tuple[list, list[dict]] | list:
    keywords = keyword_terms(question)
    exact_terms = exactish_terms(question)
    qtype = question_type(question)
    ranked: list[tuple[float, object, float]] = []
    debug_map: dict[int, dict] = {}

    for hit in hits:
        text = getattr(hit, "chunk_text", "") or ""
        book = getattr(hit, "book", "") or ""
        chapter = getattr(hit, "chapter", "") or ""
        lowered = text.lower()
        book_lower = book.lower()
        chapter_lower = chapter.lower()
        base_score = float(getattr(hit, "score", 0.0) or 0.0)
        score = base_score

        noisy = is_noisy_chunk(text)
        if noisy and qtype not in {"param", "list"}:
            score -= 2.2
        elif noisy:
            score -= 0.8

        keyword_hits = 0
        for kw in keywords:
            if kw in lowered or kw in book_lower or kw in chapter_lower:
                keyword_hits += 1
                score += 0.38

        exact_hits = 0
        for term in exact_terms:
            if term in lowered or term in book_lower or term in chapter_lower:
                exact_hits += 1
                score += 2.2

        if exact_hits:
            score += 0.5 * exact_hits
        elif keyword_hits == 0:
            score -= 0.7

        if len(re.findall(r"\d", text)) > max(12, len(re.findall(r"[A-Za-z\u4e00-\u9fff]", text))):
            score -= 0.8
        if _TABLE_OF_CONTENTS_RE.search(lowered):
            score -= 1.3

        if qtype == "param" and any(term in lowered for term in ["contents", "table of contents", "................................................................"]):
            score -= 1.0

        try:
            hit.score = score
        except Exception:
            pass

        if return_debug:
            debug_map[id(hit)] = {
                "chunk_id": getattr(hit, "chunk_id", None),
                "base_score": base_score,
                "final_score": score,
                "delta": score - base_score,
                "exact_hits": exact_hits,
                "keyword_hits": keyword_hits,
                "noisy": noisy,
            }

        ranked.append((score, hit, base_score))

    ranked.sort(key=lambda x: (x[0], getattr(x[1], "chunk_id", 0)), reverse=True)
    sorted_hits = [hit for _, hit, _ in ranked]

    if return_debug:
        sorted_debug = [
            debug_map.get(
                id(hit),
                {
                    "chunk_id": getattr(hit, "chunk_id", None),
                    "base_score": 0.0,
                    "final_score": float(getattr(hit, "score", 0.0) or 0.0),
                    "delta": 0.0,
                },
            )
            for hit in sorted_hits
        ]
        return sorted_hits, sorted_debug
    return sorted_hits
