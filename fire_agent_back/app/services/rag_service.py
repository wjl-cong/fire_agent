"""
RAG 知识库服务 — 文档上传、切分、向量化、检索增强问答

Agent 风格：RagAgent 通过本服务完成「向量召回 + 关键词召回」混合检索，
并输出检索过程元数据（命中片段、向量分、关键词分、来源文档），供前端展示。
"""
import os
import re
import json
import uuid
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import get_llm, get_embedding, llm_available
from app.models.kb_document import KbDocument, KbChunk

# 中文停用词（检索时过滤，避免"的/了/什么"这类词拉低命中）
_STOP_WORDS = set(
    "的 了 是 在 和 与 及 或 中 有 用 把 被 让 给 对 从 向 为 就 都 也 还 又 很 更 最 "
    "吗 呢 啊 吧 呀 哦 喔 嗯 啥 哪 什么 怎么 怎样 如何 为什么 哪些 哪个 是否 可以 "
    "请 帮 我 你 他 她 它 们 这 那 该 此 其 以及 一个 一种 一些 进行 应该 需要 必须 "
    "提供 了解 查询 回答 说明 相关".split()
)
# 疑问/句式通用词：仅出现在此类词中的 n-gram 无检索价值
_QUESTION_WORDS = set(
    "应该 采取 什么 措施 如何 怎样 怎么 为什么 是否 可以 需要 必须 进行 提供 说明 回答 "
    "请 帮 我 一个 一种 一些 哪些 哪个 情况 时候 原因 方面 处理 应对 办法 方式 步骤".split()
)

# 中文数字 → 阿拉伯数字
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _num2cn(n: int) -> str:
    """阿拉伯数字转中文数字（仅 1-10，用于"4级"→"四级"归一化）"""
    mapping = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
               6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    return mapping.get(n, str(n))


def _extract_keywords(text: str) -> list[str]:
    """提取中文检索关键词：
    1. 英文/数字整体保留
    2. "4级" → "四级" 归一化（提升数字等级命中率）
    3. 2 字词为主（最可靠），3 字词补充
    4. 过滤停用词与疑问句式词
    """
    # 数字等级归一化：4级 → 四级
    text = re.sub(r"([0-9]+)级", lambda m: _num2cn(int(m.group(1))) + "级", text)
    text = re.sub(r"([一二三四五六七八九十])级", lambda m: m.group(1) + "级", text)

    words = set()
    for m in re.finditer(r"[A-Za-z0-9]+", text):
        words.add(m.group(0).lower())

    for seg in re.split(r"[^\u4e00-\u9fa5]+", text):
        seg = seg.strip()
        if len(seg) < 2:
            continue
        # 2 字词（主）+ 3 字词（辅）+ 完整短语
        for n in (2, 3):
            for i in range(len(seg) - n + 1):
                w = seg[i:i + n]
                if w not in _STOP_WORDS and not any(q in w for q in _QUESTION_WORDS):
                    words.add(w)
        if len(seg) <= 4 and seg not in _STOP_WORDS and not any(q in seg for q in _QUESTION_WORDS):
            words.add(seg)

    return [w for w in words if len(w) >= 2]


def _parse_embedding(raw) -> np.ndarray | None:
    """解析数据库中存储的向量（JSON 字符串）"""
    if not raw:
        return None
    try:
        if isinstance(raw, (list, tuple)):
            arr = np.asarray(raw, dtype=float)
        else:
            arr = np.asarray(json.loads(raw), dtype=float)
        if arr.ndim != 1 or arr.size == 0:
            return None
        return arr
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """余弦相似度"""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class RagService:
    """RAG 知识库服务"""

    def __init__(self, db: Session):
        self.db = db
        self.llm = get_llm()
        self.embed = get_embedding()

    # ──────────────────────────────────────
    # 文档管理
    # ──────────────────────────────────────

    def upload_document(self, file_bytes: bytes, filename: str, category: str = "other", user_id: int = None) -> dict:
        """上传文档，保存文件并入库（user_id 记录归属用户，实现数据隔离）"""
        # 确保上传目录存在
        upload_dir = Path(settings.KB_UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # 保存文件
        file_id = str(uuid.uuid4())[:8]
        ext = Path(filename).suffix
        save_path = upload_dir / f"{file_id}{ext}"
        with open(save_path, "wb") as f:
            f.write(file_bytes)

        # 提取文本（返回 (文本, 错误信息)，文本为 None 表示失败）
        content, extract_err = self._extract_text(save_path, ext)

        # 创建文档记录
        doc = KbDocument(
            user_id=user_id,
            title=filename,
            category=category,
            source_path=str(save_path),
            file_type=ext.lstrip("."),
            status="processing",
        )
        self.db.add(doc)
        self.db.flush()

        # 切分并向量化
        if content and content.strip():
            chunks = self._chunk_text(content, doc.id)
            for chunk in chunks:
                self.db.add(chunk)
            doc.status = "ready"
            doc.summary = content[:200] + "..." if len(content) > 200 else content
            chunk_count = len(chunks)
        else:
            doc.status = "failed"
            doc.summary = extract_err or "文本提取失败：该文件可能是扫描件（无文字层）或格式不受支持，请改用可复制的 PDF/TXT/MD 文档。"
            chunk_count = 0

        self.db.commit()
        return {"id": doc.id, "title": doc.title, "status": doc.status,
                "chunks": chunk_count, "error": None if doc.status == "ready" else doc.summary}

    def list_documents(self, user_id: int = None, is_admin: bool = False) -> list[dict]:
        """文档列表（普通用户仅自己的，管理员可见全部）"""
        q = self.db.query(KbDocument)
        if not is_admin:
            q = q.filter(KbDocument.user_id == user_id)
        docs = q.order_by(KbDocument.created_at.desc()).all()
        return [
            {"id": d.id, "title": d.title, "category": d.category, "status": d.status, "summary": d.summary,
             "created_at": str(d.created_at) if d.created_at else ""}
            for d in docs
        ]

    def delete_document(self, doc_id: int, user_id: int = None, is_admin: bool = False) -> bool:
        """删除文档（仅本人或管理员）"""
        doc = self.db.query(KbDocument).get(doc_id)
        if not doc:
            return False
        if not is_admin and doc.user_id != user_id:
            return False
        # 删除文件
        if doc.source_path and os.path.exists(doc.source_path):
            os.remove(doc.source_path)
        # 删除关联分片
        self.db.query(KbChunk).filter(KbChunk.document_id == doc_id).delete()
        self.db.delete(doc)
        self.db.commit()
        return True

    # ──────────────────────────────────────
    # 检索与问答
    # ──────────────────────────────────────

    def retrieve(self, query: str, top_k: int = None, user_id: int = None, is_admin: bool = False) -> dict:
        """混合检索：向量召回 + 关键词召回，返回带检索过程元数据的结果

        用户隔离：普通用户只检索自己的文档分片，管理员检索全部。

        Returns:
            {
              "items": [ {id, document_id, document_title, content, score, vector_score, keyword_score, ...} ],
              "total_chunks": 知识库分片总数,
              "matched_chunks": 命中分片数,
              "method": "hybrid" | "vector" | "keyword" | "none",
              "keywords": [命中的关键词],
              "vector_enabled": 是否有向量可用,
            }
        """
        k = top_k or settings.KB_TOP_K
        # 可见文档（普通用户仅自己的，管理员全部）
        doc_q = self.db.query(KbDocument)
        if not is_admin:
            doc_q = doc_q.filter(KbDocument.user_id == user_id)
        total_docs = doc_q.count()
        failed_docs = doc_q.filter(KbDocument.status == "failed").count()
        failed_doc_titles = [d.title for d in doc_q.filter(KbDocument.status == "failed").all()]

        q = self.db.query(KbChunk)
        if not is_admin:
            q = q.join(KbDocument, KbChunk.document_id == KbDocument.id)\
                 .filter(KbDocument.user_id == user_id)
        chunks = q.filter(KbChunk.content.isnot(None)).all()

        if not chunks:
            return {
                "items": [], "total_chunks": 0, "matched_chunks": 0,
                "method": "none", "keywords": [], "vector_enabled": False,
                "total_docs": total_docs, "failed_docs": failed_docs,
                "failed_doc_titles": failed_doc_titles,
            }

        # 1) 中文分词
        query_words = _extract_keywords(query)
        kw2 = [w for w in query_words if len(w) == 2]
        kw3 = [w for w in query_words if len(w) >= 3]

        # 2) 问题向量（用于余弦检索）
        query_vec = None
        vector_enabled = False
        if self.embed:
            try:
                qv = self.embed.embed_query(query)
                query_vec = np.asarray(qv, dtype=float)
                vector_enabled = True
            except Exception:
                query_vec = None

        # 3) 逐分片打分
        results = []
        for c in chunks:
            content_lower = c.content.lower()
            # —— 关键词分：2 字词命中权重更高 ——
            hits2 = sum(1 for w in kw2 if w in content_lower)
            hits3 = sum(1 for w in kw3 if w in content_lower)
            kw_total = max(len(kw2) * 2 + len(kw3), 1)
            keyword_score = (hits2 * 2 + hits3) / kw_total

            # —— 向量分（余弦相似度） ——
            vec_score = 0.0
            if query_vec is not None:
                emb = _parse_embedding(c.embedding)
                if emb is not None:
                    vec_score = _cosine(query_vec, emb)

            # 任一命中即进入候选池
            if (hits2 + hits3) > 0 or vec_score > 0.05:
                results.append({
                    "id": c.id,
                    "document_id": c.document_id,
                    "document_title": self._doc_title(c.document_id),
                    "content": c.content,
                    "keyword_score": round(keyword_score, 3),
                    "vector_score": round(vec_score, 3),
                    "score": round(max(keyword_score, vec_score), 3),
                })

        # 4) 混合排序：向量分与关键词分加权融合（取 max，向量优先）
        results.sort(key=lambda x: max(x["vector_score"], x["keyword_score"]), reverse=True)
        top = results[:k]

        # 5) 严格匹配无结果 → 字符 bigram 包含度兜底
        #    解决「文档已上传但换个说法问不到」：只要查询与分片存在有意义的共同字组，
        #    就返回最相关分片并保留来源引用，避免误报"未检索到"。
        if not top and chunks:
            q_bi = [query[i:i + 2] for i in range(len(query) - 1)]
            # 仅保留中文/字母数字 bigram，且过滤停用词与纯符号
            q_bi = [
                b for b in q_bi
                if re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", b)
                and b.lower() not in _STOP_WORDS
                and b not in _STOP_WORDS
            ]
            if q_bi:
                scored = []
                for c in chunks:
                    cl = c.content.lower()
                    hits = sum(1 for b in q_bi if b.lower() in cl)
                    if hits:
                        scored.append({
                            "id": c.id,
                            "document_id": c.document_id,
                            "document_title": self._doc_title(c.document_id),
                            "content": c.content,
                            "keyword_score": round(hits / len(q_bi), 3),
                            "vector_score": 0.0,
                            "score": round(hits / len(q_bi), 3),
                            "overlap_hits": hits,
                        })
                scored.sort(key=lambda x: -x["score"])
                if scored and scored[0]["score"] >= 0.12:
                    top = scored[:k]
                    results = scored

        # 6) 汇总方法标识
        if results and vector_enabled:
            method = "hybrid"
        elif results:
            method = "keyword"
        else:
            method = "none"

        return {
            "items": top,
            "total_chunks": len(chunks),
            "matched_chunks": len(results),
            "method": method,
            "keywords": query_words,
            "vector_enabled": vector_enabled,
            "total_docs": total_docs,
            "failed_docs": failed_docs,
            "failed_doc_titles": failed_doc_titles,
        }

    def answer(self, query: str, context: dict = None) -> dict:
        """基于检索结果生成回答（带 RagAgent 检索过程元数据）

        context 为 retrieve() 的返回值；若未传入则内部执行检索。
        """
        if context is None:
            context = self.retrieve(query)

        refs = context.get("items", [])
        retri_meta = {
            "total_chunks": context.get("total_chunks", 0),
            "matched_chunks": context.get("matched_chunks", 0),
            "method": context.get("method", "none"),
            "keywords": context.get("keywords", []),
            "vector_enabled": context.get("vector_enabled", False),
            "total_docs": context.get("total_docs", 0),
            "failed_docs": context.get("failed_docs", 0),
            "failed_doc_titles": context.get("failed_doc_titles", []),
        }

        # 未命中任何片段 → 明确告知原因，不让 LLM 凭空发挥
        if not refs:
            failed_titles = retri_meta.get("failed_doc_titles") or []
            failed_hint = ""
            if failed_titles:
                names = "、".join(failed_titles[:5])
                failed_hint = (f"\n\n注意：知识库中有 {len(failed_titles)} 个文档提取失败"
                               f"（{names}），可能是扫描件/图片型 PDF 或无文字层，"
                               "请删除后重新上传可复制的 PDF、TXT 或 Markdown 文档。")
            if retri_meta["total_chunks"] == 0:
                if retri_meta["failed_docs"] > 0:
                    hint = (f"当前可见知识库中有 {retri_meta['failed_docs']} 个文档文本提取失败，"
                            "没有可检索的文字内容。" + failed_hint)
                elif retri_meta["total_docs"] == 0:
                    hint = "当前知识库中还没有可检索的文档。请先在上方「文档管理」上传相关文档。"
                else:
                    hint = "当前可见知识库暂无可检索的分片（文档可能正在处理中）。" + failed_hint
            else:
                hint = ("RagAgent 在知识库中未检索到与问题相关的内容。\n\n"
                        "建议：\n1. 换一种更具体的表述再提问；\n"
                        "2. 确认问题关键词与已上传文档内容相关。" + failed_hint)

            return {
                "answer": hint,
                "references": [],
                "llm_used": False,
                "retrieval": retri_meta,
            }

        # LLM 不可用 → 直接返回检索到的片段
        if not llm_available():
            return {
                "answer": "LLM 未配置，RagAgent 仅返回检索到的相关片段（未生成 AI 回答）。",
                "references": refs,
                "llm_used": False,
                "retrieval": retri_meta,
            }

        # 构建 Prompt：注入完整片段内容 + 来源文档
        context_text = "\n\n".join(
            [f"[来源 {i + 1}（文档：{r.get('document_title', '未知')}）]: {r['content']}" for i, r in enumerate(refs)]
        )
        prompt = f"""你是一个森林火险知识助手（RagAgent）。请严格根据下面的参考文档回答用户问题。

要求：
1. 回答必须基于参考文档中的内容，不得编造文档中不存在的信息；
2. 在回答中引用对应的来源编号，例如「根据[来源1]…」；
3. 如果参考文档无法覆盖问题，请明确说明"知识库文档中未找到该信息"；
4. 用简洁、专业的中文回答。

参考文档：
{context_text}

用户问题：{query}

回答："""

        llm = get_llm(temperature=0.1)
        try:
            response = llm.invoke(prompt)
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            answer = f"RagAgent 调用 LLM 失败，已返回原始检索片段。\n\n检索到 {len(refs)} 个相关片段，详见下方引用来源。（{e}）"

        return {
            "answer": answer,
            "references": refs,
            "llm_used": True,
            "retrieval": retri_meta,
        }

    # ──────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────

    def _doc_title(self, doc_id: int) -> str:
        """根据分片 document_id 查文档标题（带缓存）"""
        if not hasattr(self, "_title_cache"):
            self._title_cache = {}
        if doc_id not in self._title_cache:
            doc = self.db.query(KbDocument).filter(KbDocument.id == doc_id).first()
            self._title_cache[doc_id] = doc.title if doc else "未知文档"
        return self._title_cache[doc_id]

    def _extract_text(self, file_path: Path, ext: str) -> tuple:
        """提取文档文本，返回 (文本, 错误信息)；文本为 None 表示提取失败

        失败时返回具体原因，供前端展示（区分扫描件/无文字层/格式问题等）。
        """
        ext = ext.lower()
        try:
            if ext == ".txt":
                return file_path.read_text(encoding="utf-8"), None
            elif ext == ".md":
                from markdown import markdown
                import re
                html = markdown(file_path.read_text(encoding="utf-8"))
                return re.sub(r"<[^>]+>", "", html), None
            elif ext == ".pdf":
                return self._extract_pdf(file_path), None
            else:
                return file_path.read_text(encoding="utf-8", errors="ignore"), None
        except Exception as e:
            return None, f"文本提取失败：{e}"

    @staticmethod
    def _normalize_pdf_text(raw) -> str:
        """把各 PDF 库返回的文本统一成 str（兼容 bytes 返回）"""
        if raw is None:
            return ""
        if isinstance(raw, bytes):
            for enc in ("utf-8", "gbk", "gb18030"):
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, ValueError):
                    continue
            return ""
        return str(raw)

    @staticmethod
    def _is_garbled_cn(text: str) -> bool:
        """检测 GB/T 国家标准 PDF 的乱码文字层

        这类 PDF（国家标准全文公开系统）使用自定义字体编码，提取出的文本
        会出现大量生僻字形（犐犆犛犌犅犜…，位于 U+7280-U+72FF 牛部字）以及
        高密度标点符号（!"#$%&'()*…）替代中文字符，导致关键词/向量检索全部失效。
        返回 True 表示判定为乱码文本。
        """
        if not text or len(text.strip()) < 20:
            return True
        total = len(text)
        rare = sum(1 for ch in text if "\u7280" <= ch <= "\u72ff")
        punct = sum(1 for ch in text if ch in "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        if rare / total > 0.03:
            return True
        if punct / total > 0.35 and cjk / total < 0.35:
            return True
        if rare / total > 0.01 and cjk / total < 0.2:
            return True
        return False

    @staticmethod
    def _ocr_pdf(file_path: Path, max_pages: int = 60) -> str:
        """对 PDF 逐页渲染为图片并用 RapidOCR 识别文字（兜底方案）

        适用于：GB/T 国家标准 PDF（自定义字体编码导致文字层乱码）、扫描件。
        RapidOCR 基于 ONNX 离线推理，无需联网、无需系统级 Tesseract。
        """
        import pymupdf  # PyMuPDF（新 API，替代已弃用的 fitz）
        from rapidocr_onnxruntime import RapidOCR

        ocr = RapidOCR()
        doc = pymupdf.open(str(file_path))
        pages_text = []
        try:
            for i, page in enumerate(doc):
                if i >= max_pages:
                    pages_text.append(f"[提示：文档超过 {max_pages} 页，仅 OCR 前 {max_pages} 页]")
                    break
                # 2x 缩放渲染保证中文小字号可识别
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                result, _ = ocr(img_bytes)
                if result:
                    # 按 OCR 返回的行顺序拼接
                    pages_text.append("\n".join(line[1] for line in result))
        finally:
            doc.close()
        return "\n".join(pages_text)

    @staticmethod
    def _extract_pdf(file_path: Path) -> str:
        """PDF 文本提取：pdfplumber → pypdf → PyMuPDF → RapidOCR 依次尝试

        前三个库提取文字层并做乱码/空文本检测；全部失败时自动降级到
        RapidOCR 图像识别（解决 GB/T 标准 PDF 乱码与扫描件问题）。
        """
        reasons = []
        for extractor in ("pdfplumber", "pypdf", "fitz"):
            text = ""
            try:
                if extractor == "pdfplumber":
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        text = "\n".join(
                            RagService._normalize_pdf_text(page.extract_text()) for page in pdf.pages
                        )
                elif extractor == "pypdf":
                    from pypdf import PdfReader
                    reader = PdfReader(str(file_path))
                    text = "\n".join(
                        RagService._normalize_pdf_text(page.extract_text()) for page in reader.pages
                    )
                else:
                    import pymupdf  # PyMuPDF（新 API，替代已弃用的 fitz）
                    doc = pymupdf.open(str(file_path))
                    text = "\n".join(
                        RagService._normalize_pdf_text(page.get_text()) for page in doc
                    )
                    doc.close()
            except Exception as e:
                reasons.append(f"{extractor}: {e}")
                continue

            if not (text and text.strip()):
                reasons.append(f"{extractor}: 无文字")
                continue
            if len(text.strip()) < 20:
                reasons.append(f"{extractor}: 文字过少（疑似扫描件）")
                continue
            if RagService._is_garbled_cn(text):
                reasons.append(f"{extractor}: 乱码")
                continue
            return text

        # ===== 文字层全部不可用 → OCR 兜底 =====
        try:
            ocr_text = RagService._ocr_pdf(file_path)
        except ImportError:
            ocr_text = ""
        except Exception as e:
            reasons.append(f"ocr: {e}")
            ocr_text = ""

        if ocr_text and len(ocr_text.strip()) >= 20 and not RagService._is_garbled_cn(ocr_text):
            return ocr_text

        joined = "；".join(reasons)
        if "乱码" in joined:
            raise ValueError(
                "该 PDF 为 GB/T 国家标准全文文件（文字层使用自定义字体编码，提取后为乱码），"
                "且 OCR 识别失败或未安装 OCR 组件（pip install rapidocr-onnxruntime）。"
                "请安装 OCR 组件后重新上传，或直接上传 TXT / Markdown 文档。"
            )
        if "扫描件" in joined or "无文字" in joined:
            raise ValueError(
                "该 PDF 提取到极少量文字（疑似扫描件/图片型 PDF，无文字层），"
                "且 OCR 识别失败。请改用带文字层的 PDF，或直接上传 TXT / Markdown 文档。"
            )
        raise ValueError(f"PDF 文本提取失败，无可用文字（{joined}）")

    def _chunk_text(self, text: str, doc_id: int) -> list[KbChunk]:
        """切分文本并生成向量"""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.KB_CHUNK_SIZE,
            chunk_overlap=settings.KB_CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )
        chunks = splitter.split_text(text)

        # 生成向量（如果 LLM 可用）
        embeddings = None
        if self.embed:
            try:
                embeddings = self.embed.embed_documents(chunks)
            except Exception:
                embeddings = None

        result = []
        for i, content in enumerate(chunks):
            embedding_str = None
            if embeddings and i < len(embeddings):
                try:
                    # 统一存 JSON 数组，便于检索时解析为向量
                    embedding_str = json.dumps([float(x) for x in embeddings[i]])
                except (TypeError, ValueError):
                    embedding_str = None
            chunk = KbChunk(
                document_id=doc_id,
                chunk_index=i,
                content=content,
                token_count=len(content),
                embedding=embedding_str,
            )
            result.append(chunk)
        return result