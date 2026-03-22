import re

from llm import generate_rag_answer, llm_settings
from schemas import AskRequest, AskResponse, Citation, SearchRequest
from search import search_documents


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_NUMERIC_NOISE_RE = re.compile(r"^[\d\s.,;:()\[\]/+\-–—%*xX=<>#°]+$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+|\n+")


def _question_type(question: str) -> str:
    q = question.lower()
    if any(k in question for k in ["多少种", "清单", "列表", "有哪些", "哪几种"]):
        return "list"
    if any(k in question for k in ["容量", "电压", "功率", "压力", "温度", "数量", "参数", "范围", "多大", "几台", "多少台", "额定输出"]):
        return "param"
    if any(k in q for k in ["capacity", "rated output", "quantity", "how many", "kw", "kwe", "generator size"]):
        return "param"
    if "试航" in question or "试验" in question or "测试" in question:
        return "trial"
    if "transformer" in q or "变压器" in question:
        return "list"
    return "general"


def _expand_question_queries(question: str) -> list[str]:
    queries: list[str] = [question.strip()]
    q = question.lower()

    expansions: list[str] = []
    if "试航" in question:
        expansions.extend([
            "sea trial",
            "sea trial test items",
            "sea trial procedure",
            "trial items during sea trial",
        ])
    if "试验" in question or "测试" in question:
        expansions.extend(["test items", "tests", "trial items"])
    if "要求" in question:
        expansions.extend(["requirements", "procedure", "approval"])
    if "焊接" in question or "焊" in question:
        expansions.extend(["welding spec", "WPS"])
    if "coating" in q or "涂层" in question or "油漆" in question:
        expansions.extend(["coating system", "paint specification"])
    if "变压器" in question or "transformer" in q:
        expansions.extend([
            "transformer",
            "transformer capacity",
            "high voltage transformers",
            "low voltage transformers",
        ])
    if any(k in question for k in ["发电机", "应急发电机", "轴带发电机", "双燃料发电机", "辅助发电机"]) or "generator" in q:
        expansions.extend([
            "generator quantity rated output",
            "generator capacity kW",
            "generator particulars",
            "rated output quantity",
            "emergency generator",
            "shaft generator",
            "dual fuel generator",
        ])
    if any(k in question for k in ["几台", "多少台", "多大", "容量", "功率", "额定输出", "数量"]) or any(k in q for k in ["capacity", "rated output", "quantity", "how many", "kw", "kwe"]):
        expansions.extend([
            "quantity rated output",
            "capacity quantity kW",
            "particulars rated output",
            "no. of set rated output",
        ])
    if "流量计" in question or "flow meter" in q:
        expansions.extend(["flow meter", "mass type flow meter", "coriolis", "rotameter"])

    for item in expansions:
        item = item.strip()
        if item and item not in queries:
            queries.append(item)
    return queries[:8]


def _keyword_terms(question: str) -> set[str]:
    keywords: set[str] = set()
    for query in _expand_question_queries(question):
        lowered = query.lower()
        for token in re.findall(r"[a-zA-Z]{3,}|\d+|[\u4e00-\u9fff]{2,}", lowered):
            if token not in {"what", "which", "with", "for", "the", "and", "are", "有哪些", "什么"}:
                keywords.add(token)
    return keywords


def _is_noisy_chunk(text: str) -> bool:
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
    for line in lines:
        compact = line.replace(" ", "")
        if _NUMERIC_NOISE_RE.match(compact):
            numeric_like += 1
        alpha_cjk_chars += sum(1 for ch in line if ch.isalpha() or _CJK_RE.match(ch))
        digit_chars += sum(1 for ch in line if ch.isdigit())

    if numeric_like / max(len(lines), 1) >= 0.6:
        return True
    if alpha_cjk_chars == 0:
        return True
    if digit_chars > alpha_cjk_chars * 1.2:
        return True
    return False


def _extract_relevant_excerpt(text: str, keywords: set[str]) -> str:
    cleaned = text.strip().replace("\r", "")
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    if not parts:
        return cleaned[:240] + ("…" if len(cleaned) > 240 else "")

    scored: list[tuple[int, str]] = []
    for part in parts:
        lowered = part.lower()
        score = 0
        for kw in keywords:
            if kw in lowered or kw in part:
                score += 2
        if any(term in lowered for term in ["trial", "test", "procedure", "approval", "transformer", "capacity", "quantity"]):
            score += 2
        if _is_noisy_chunk(part):
            score -= 3
        scored.append((score, part))

    scored.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
    best = scored[0][1]
    return best[:260] + ("…" if len(best) > 260 else "")


def _rank_hits(question: str, hits):
    keywords = _keyword_terms(question)
    qtype = _question_type(question)
    ranked = []
    for hit in hits:
        text = hit.chunk_text or ""
        lowered = text.lower()
        score = float(hit.score or 0.0)
        if _is_noisy_chunk(text) and qtype not in {"param", "list"}:
            score -= 1.5
        for kw in keywords:
            if kw in lowered or kw in text:
                score += 0.35
        if qtype == "trial" and any(term in lowered for term in ["sea trial", "trial", "test", "procedure", "approved", "approval"]):
            score += 0.7
        if qtype in {"list", "param"} and any(term in lowered for term in ["transformer", "capacity", "quantity", "application", "voltage"]):
            score += 0.7
        if qtype == "param" and any(term in lowered for term in ["rated output", "quantity", "no. of set", "capacity", "kw", "kwe", "particulars"]):
            score += 1.2
        if qtype == "param" and any(term in lowered for term in ["contents", "table of contents", "................................................................"]):
            score -= 1.0
        if qtype == "param" and "generator" in lowered:
            score += 0.6
        ranked.append((score, hit))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [hit for _, hit in ranked]


def _dedupe_hits(hits):
    seen: set[int] = set()
    out = []
    for hit in hits:
        if hit.chunk_id in seen:
            continue
        seen.add(hit.chunk_id)
        out.append(hit)
    return out


def _extract_trial_items(hits) -> list[str]:
    patterns = [
        ("progressive speed trial", "渐进航速试验"),
        ("shaft generator test", "轴带发电机试验"),
        ("shaft locking device", "轴锁定装置试验"),
        ("unmanned engine room test", "无人机舱运行试验"),
        ("vibration measurement", "振动测量"),
        ("over speed running", "超速运行试验"),
        ("crash stop astern test", "倒车紧急停车试验"),
        ("endurance trial", "耐久试验"),
        ("speed trial", "航速试验"),
        ("sea trial procedure", "试航程序审批/确认"),
    ]

    found: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        lowered = hit.chunk_text.lower()
        for needle, label in patterns:
            if needle in lowered and label not in seen:
                seen.add(label)
                found.append(label)
    return found


def _infer_evidence_label(hit) -> str:
    text = hit.chunk_text or ""
    lowered = text.lower()

    if "8.1.4" in text and "high voltage transformers" in lowered:
        return "8.1.4 Transformer / High voltage transformers"
    if "low voltage transformers" in lowered:
        return "8.1.4 Transformer / Low voltage transformers"
    if any(k in lowered for k in ["220v normal", "220v em", "220v fwd", "galley/laundry"]):
        return "8.1.4 Transformer / Low voltage transformers"
    if any(k in lowered for k in ["440v general service", "440v cargo service", "reliquefaction"]):
        return "8.1.4 Transformer / High voltage transformers"
    if "8.1.4" in text:
        return "8.1.4 Transformer"
    if "transformer" in lowered:
        return "Transformer 相关章节"
    return f"《{hit.book}》相关片段"


def _extract_transformer_table(hits) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for hit in hits:
        text = hit.chunk_text
        lowered = text.lower()
        if "transformer" not in lowered and "capacity" not in lowered and "voltage" not in lowered:
            continue

        compact = re.sub(r"\s+", " ", text)
        evidence_label = _infer_evidence_label(hit)

        hv = re.search(
            r"Application\s+440V General Service\s+440V Cargo Service\s+Reliquefaction\s+Quantity\s+Two \(2\)\s+Two \(2\)\s+One\s+\(1-wk, 1-sb\)\s+\(1-wk, 1-sb\)\s+Capacity\s+([\d,]+\s*kVA)\s+([\d,]+\s*kVA)",
            compact,
            re.IGNORECASE,
        )
        if hv:
            candidates = [
                ("440V General Service Transformer", "2", hv.group(1)),
                ("440V Cargo Service Transformer", "2", hv.group(2)),
                ("Reliquefaction Transformer", "1", "待继续从相邻原文补全"),
            ]
            for app, qty, cap in candidates:
                key = (app, qty, cap)
                if key not in seen:
                    seen.add(key)
                    rows.append({"name": app, "quantity": qty, "capacity": cap, "evidence_label": evidence_label})

        lv = re.search(
            r"Application\s+220V Normal\s+220V Em[’']?cy\s+220V Fwd\s+220V\s+Lighting\s+Lighting\s+Lighting\s+Galley/Laundry\s+Isolation\s+Quantity\s+Two \(2\)\s+Two \(2\)\s+One \(1\)\s+One \(1\)\s+\(1-wk, 1-sb\)\s+\(1-wk, 1-sb\)\s+Capacity\s+([\d,]+\s*kVA)\s+([\d,]+\s*kVA)\s+([\d,]+\s*kVA)\s+([\d,]+\s*kVA)",
            compact,
            re.IGNORECASE,
        )
        if lv:
            candidates = [
                ("220V Normal Lighting Transformer", "2", lv.group(1)),
                ("220V Emergency Lighting Transformer", "2", lv.group(2)),
                ("220V Forward Lighting Transformer", "1", lv.group(3)),
                ("220V Galley/Laundry Isolation Transformer", "1", lv.group(4)),
            ]
            for app, qty, cap in candidates:
                key = (app, qty, cap)
                if key not in seen:
                    seen.add(key)
                    rows.append({"name": app, "quantity": qty, "capacity": cap, "evidence_label": evidence_label})

    return rows


def _structured_summary(question: str, hits) -> str | None:
    qtype = _question_type(question)
    useful_hits = [hit for hit in hits if not _is_noisy_chunk(hit.chunk_text)] or hits[:5]

    if qtype == "trial":
        items = _extract_trial_items(useful_hits)
        if items:
            lines = [f"问题：{question}", "整理结果（结构化抽取）："]
            for idx, item in enumerate(items[:10], start=1):
                lines.append(f"{idx}. {item}")
            lines.append("\n可在下方证据区查看对应原文片段。")
            return "\n".join(lines)

    if "变压器" in question or "transformer" in question.lower():
        rows = _extract_transformer_table(hits)
        if rows:
            lines = [f"问题：{question}", "整理结果（结构化抽取）：", "已识别到的变压器类型 / 数量 / 容量如下："]
            for idx, row in enumerate(rows, start=1):
                lines.append(
                    f"{idx}. {row['name']} —— 数量：{row['quantity']}；容量：{row['capacity']}（证据位置：{row['evidence_label']}）"
                )
            lines.append("\n说明：当前结果来自命中表格的规则抽取；若要补齐未完整显示项，可继续查看下方原文证据。")
            return "\n".join(lines)

    return None


def _fallback_summary(question: str, hits) -> str:
    if not hits:
        return "当前知识库里没有检索到足够证据，暂时不能可靠回答这个问题。"

    keywords = _keyword_terms(question)
    useful_hits = [hit for hit in hits if not _is_noisy_chunk(hit.chunk_text)]
    if not useful_hits:
        useful_hits = hits[:3]

    lines = [f"问题：{question}", "基于当前命中的资料，先给出可追溯的整理："]
    for idx, hit in enumerate(useful_hits[:5], start=1):
        excerpt = _extract_relevant_excerpt(hit.chunk_text, keywords)
        loc = []
        if hit.chapter:
            loc.append(hit.chapter)
        if hit.page_start is not None or hit.page_end is not None:
            loc.append(f"页码 {hit.page_start}-{hit.page_end}")
        loc_text = f"（{'，'.join(loc)}）" if loc else ""
        lines.append(f"证据 {idx}. 《{hit.book}》{loc_text}：{excerpt}")

    lines.append("以上内容为基于检索结果的整理；当前仍是 retrieval-only 回答，但已尽量过滤表格噪声并保留可追溯证据。")
    return "\n".join(lines)


def _build_contexts(hits):
    return [
        {
            "chunk_id": hit.chunk_id,
            "book": hit.book,
            "chapter": hit.chapter,
            "page_start": hit.page_start,
            "page_end": hit.page_end,
            "chunk_text": hit.chunk_text,
            "score": hit.score,
        }
        for hit in hits
    ]


async def ask_documents(payload: AskRequest) -> AskResponse:
    merged_hits = []
    for query in _expand_question_queries(payload.question):
        result = await search_documents(SearchRequest(query=query, top_k=max(payload.top_k, 8), filters=payload.filters))
        merged_hits.extend(result.hits)

    ranked_hits = _rank_hits(payload.question, _dedupe_hits(merged_hits))
    top_hits = ranked_hits[: payload.top_k]

    citations = [
        Citation(
            chunk_id=hit.chunk_id,
            book=hit.book,
            chapter=hit.chapter,
            page_start=hit.page_start,
            page_end=hit.page_end,
        )
        for hit in top_hits[: min(len(top_hits), 8)]
    ]

    contexts = _build_contexts(top_hits)
    mode = "retrieval_only"
    debug: dict = {
        "retrieved_hits": len(top_hits),
        "queries": _expand_question_queries(payload.question),
        "question_type": _question_type(payload.question),
    }

    llm_overrides = {
        "enabled": payload.llm_enabled,
        "model": payload.llm_model,
        "temperature": payload.llm_temperature,
    }

    answer = ""
    llm_error = None
    settings = llm_settings(llm_overrides)
    if settings["enabled"] and top_hits:
        try:
            answer = await generate_rag_answer(question=payload.question, contexts=contexts, overrides=llm_overrides)
            mode = "llm_rag"
        except Exception as exc:
            llm_error = str(exc)

    if not answer:
        answer = _structured_summary(payload.question, top_hits) or _fallback_summary(payload.question, top_hits)

    debug["mode"] = mode
    if llm_error:
        debug["llm_error"] = llm_error
    if settings["base_url"]:
        debug["llm_base_url"] = settings["base_url"]
    if settings["model"]:
        debug["llm_model"] = settings["model"]

    return AskResponse(
        question=payload.question,
        answer=answer,
        citations=citations,
        sources=top_hits,
        mode=mode,
        debug=debug,
    )
