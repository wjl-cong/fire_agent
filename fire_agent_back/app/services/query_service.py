"""
智能查询服务 — 自然语言 → 结构化查询 → 结果

使用 LLM 做意图识别（有 API Key 时），无 API Key 时回退到关键词匹配
"""
import re
from datetime import datetime

from app.core.llm import get_llm, llm_available
from app.repositories.fire_repository import FireRepository
from app.schemas.query import QueryParseResult, QueryResult

# 云南 16 个州市
CITIES = [
    "昆明市", "曲靖市", "玉溪市", "保山市", "昭通市", "丽江市",
    "普洱市", "临沧市", "楚雄彝族自治州", "红河哈尼族彝族自治州",
    "文山壮族苗族自治州", "西双版纳傣族自治州", "大理白族自治州",
    "德宏傣族景颇族自治州", "怒江傈僳族自治州", "迪庆藏族自治州",
]
SHORT_CITY_MAP = {
    "昆明": "昆明市", "曲靖": "曲靖市", "玉溪": "玉溪市",
    "保山": "保山市", "昭通": "昭通市", "丽江": "丽江市",
    "普洱": "普洱市", "临沧": "临沧市", "楚雄": "楚雄彝族自治州",
    "红河": "红河哈尼族彝族自治州", "文山": "文山壮族苗族自治州",
    "西双版纳": "西双版纳傣族自治州", "版纳": "西双版纳傣族自治州",
    "大理": "大理白族自治州", "德宏": "德宏傣族景颇族自治州",
    "怒江": "怒江傈僳族自治州", "迪庆": "迪庆藏族自治州",
}
# 16 州市中心经纬度（用于汇总类查询生成地图点位）
CITY_CENTERS = {
    "昆明市": [102.833, 24.879],
    "曲靖市": [103.798, 25.491],
    "玉溪市": [102.545, 24.354],
    "保山市": [99.162, 25.112],
    "昭通市": [103.717, 27.337],
    "丽江市": [100.229, 26.855],
    "普洱市": [100.966, 22.825],
    "临沧市": [100.092, 23.886],
    "楚雄彝族自治州": [101.546, 25.040],
    "红河哈尼族彝族自治州": [103.375, 23.366],
    "文山壮族苗族自治州": [104.244, 23.369],
    "西双版纳傣族自治州": [100.797, 22.009],
    "大理白族自治州": [100.267, 25.606],
    "德宏傣族景颇族自治州": [98.585, 24.436],
    "怒江傈僳族自治州": [98.854, 25.851],
    "迪庆藏族自治州": [99.702, 27.826],
}
SEASON_MAP = {
    "spring": [3, 4, 5], "summer": [6, 7, 8], "autumn": [9, 10, 11], "winter": [12, 1, 2],
    "春季": [3, 4, 5], "夏季": [6, 7, 8], "秋季": [9, 10, 11], "冬季": [12, 1, 2],
    "春": [3, 4, 5], "夏": [6, 7, 8], "秋": [9, 10, 11], "冬": [12, 1, 2],
}
CONFIDENCE_MAP = {"高": "high", "低": "low", "中": "nominal", "high": "high", "low": "low", "nominal": "nominal"}
# 中文数字月份："一月" → 1
CN_MONTH = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


class QueryService:
    def __init__(self, db_session):
        self.repo = FireRepository(db_session)

    # ========== 公共入口 ==========

    def parse(self, query_text: str) -> QueryParseResult:
        """解析自然语言查询（返回结果带 method 字段，标识 LLM 或关键词）"""
        if llm_available():
            result = self._parse_with_llm(query_text)
            if result.method == "keyword":
                return result
            result.method = "llm"
            return result
        return self._parse_with_keyword(query_text)

    def execute(self, parsed: QueryParseResult) -> QueryResult:
        """执行查询"""
        p = parsed.params
        if parsed.intent == "predict":
            return self._exec_predict(p)
        elif parsed.intent == "summary":
            return self._exec_summary(p)
        return self._exec_history(p)

    # ========== LLM 解析 ==========

    def _parse_with_llm(self, query_text: str) -> QueryParseResult:
        """使用 LLM 解析自然语言"""
        llm = get_llm(temperature=0.05)
        prompt = f"""你是一个火险数据查询助手。请解析用户的自然语言查询，输出 JSON 格式结果。

可用查询类型：history（历史火点）、predict（预测火险）、summary（数据汇总）
城市列表：{', '.join(CITIES)}
季节映射：spring=[3,4,5] summer=[6,7,8] autumn=[9,10,11] winter=[12,1,2]
置信度：high / nominal / low

用户查询：{query_text}

请输出 JSON，格式如下：
{{"intent": "history|predict|summary", "city": "城市名或null", "year": 年份或null, "month": 月份或null, "months": [月份列表]或null, "confidence": "置信度或null", "top_k": 数量或null, "sort": "desc或null", "explanation": "解析说明"}}
仅输出 JSON，不要其他文字。"""
        try:
            response = llm.invoke(prompt)
            import json
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip().removeprefix("```json").removesuffix("```").strip()
            data = json.loads(text)
            # 清洗 LLM 返回值：年份/月份/top_k 统一转数字，去掉"年/月"后缀，避免脏值导致查询为空
            for k in ("year", "month", "top_k"):
                if k in data and data[k] is not None:
                    try:
                        data[k] = int(str(data[k]).replace("年", "").replace("月", "").strip())
                    except (ValueError, TypeError):
                        data[k] = None
            if isinstance(data.get("months"), list):
                cleaned_months = []
                for m in data["months"]:
                    try:
                        cleaned_months.append(int(str(m).replace("月", "").strip()))
                    except (ValueError, TypeError):
                        continue
                data["months"] = cleaned_months or None
            return QueryParseResult(
                intent=data.get("intent", "history"),
                params={k: v for k, v in data.items() if k not in ("intent", "explanation") and v is not None},
                explanation=data.get("explanation", "LLM 解析"),
            )
        except Exception:
            return self._parse_with_keyword(query_text)

    # ========== 关键词回退解析 ==========

    def _parse_with_keyword(self, query_text: str) -> QueryParseResult:
        text = query_text.strip()
        params = {}
        now_year = datetime.now().year

        # 意图识别：汇总/统计 → summary；预测/预报/未来/风险 → predict；否则 history
        intent = "summary" if any(kw in text for kw in ["汇总", "统计", "概况", "摘要", "分布", "一览"]) else \
                 "predict" if any(kw in text for kw in ["预测", "预报", "未来", "风险", "预警", "险情"]) else "history"

        # 城市
        for city in CITIES:
            if city in text:
                params["city"] = city
                break
        if "city" not in params:
            for short, full in SHORT_CITY_MAP.items():
                if short in text:
                    params["city"] = full
                    break

        # 年份（显式 4 位年份优先）
        m = re.search(r"(20\d{2})年", text)
        if m:
            params["year"] = int(m.group(1))
        else:
            m = re.search(r"(20\d{2})", text)
            if m:
                params["year"] = int(m.group(1))

        # 相对年份（仅在未显式给出年份时生效）
        if "year" not in params:
            if "去年" in text:
                params["year"] = now_year - 1
            elif "今年" in text:
                params["year"] = now_year

        # 近 N 年（时间范围：近N年 = 今年往前 N 年）
        m = re.search(r"近(\d{1,2})年", text)
        if m:
            n = int(m.group(1))
            params["year_start"] = now_year - n + 1
            params["year_end"] = now_year

        # 月份（阿拉伯数字，如 "1月"；随后处理中文数字，如 "一月"）
        m = re.search(r"(\d{1,2})月", text)
        if m:
            params["month"] = int(m.group(1))
        else:
            m = re.search(r"([一二三四五六七八九十]{1,2})月", text)
            if m and m.group(1) in CN_MONTH:
                params["month"] = CN_MONTH[m.group(1)]

        # 季节
        for season, months in SEASON_MAP.items():
            if season in text:
                params["months"] = months
                break

        # 置信度
        for kw, val in CONFIDENCE_MAP.items():
            if kw in text:
                params["confidence"] = val
                break

        # 排序/排名
        if any(kw in text for kw in ["最多", "最高", "Top", "top"]):
            params["sort"] = "desc"
            params["top_k"] = 5
            m = re.search(r"(\d+)个", text)
            if m:
                params["top_k"] = int(m.group(1))

        exp = self._explain_keyword(intent, params)
        return QueryParseResult(intent=intent, params=params, explanation=exp)

    @staticmethod
    def _explain_keyword(intent: str, params: dict) -> str:
        """把关键词解析结果转成自然语言说明（替代原始调试串，更易读）"""
        intent_name = {"history": "历史火点查询", "predict": "预测火险查询", "summary": "数据汇总统计"}.get(intent, intent)
        parts = [intent_name]
        if params.get("city"):
            parts.append(f"限定城市「{params['city']}」")
        if params.get("year_start") and params.get("year_end"):
            parts.append(f"时间范围 {params['year_start']}—{params['year_end']} 年")
        elif params.get("year"):
            if params.get("month"):
                parts.append(f"时间 {params['year']} 年 {params['month']} 月")
            else:
                parts.append(f"时间 {params['year']} 年")
        if params.get("months"):
            parts.append(f"季节月份 {','.join(str(m) for m in params['months'])} 月")
        if params.get("confidence"):
            conf_label = {"high": "高置信度", "nominal": "中置信度", "low": "低置信度"}.get(params["confidence"], params["confidence"])
            parts.append(conf_label)
        if params.get("sort") == "desc":
            parts.append("按数值降序取 TopN")
        return "，".join(parts) + "。"

    # ========== 地图 GeoJSON 生成 ==========

    @staticmethod
    def _build_geojson(points, name_key="city", value_key="risk_score", color_mode="risk"):
        """把带经纬度的记录转成 GeoJSON FeatureCollection，供前端地图渲染

        points: dict 列表，需含 longitude/latitude
        name_key/value_key: 用于 properties 的字段名，缺省自动取首条记录里存在的键
        color_mode: risk(按风险分档) / value(按数值) / 默认青色
        """
        features = []
        if not points:
            return None
        # 推断要用的取值字段
        first = points[0]
        if not name_key or name_key not in first:
            name_key = next((k for k in ("city", "name", "city_name") if k in first), None)
        if not value_key or value_key not in first:
            value_key = next((k for k in ("risk_score", "frp", "pred_fire_count", "value", "final_fire_index") if k in first), None)
        for i, pt in enumerate(points):
            lng = pt.get("longitude")
            lat = pt.get("latitude")
            if lng is None or lat is None:
                continue
            val = pt.get(value_key) if value_key else None
            features.append({
                "type": "Feature",
                "id": i,
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "name": pt.get(name_key, f"点{i + 1}"),
                    "value": val,
                    "color": QueryService._risk_color(val) if color_mode == "risk" else "#0ea5e9",
                    **{k: v for k, v in pt.items() if k in ("acq_date", "confidence", "risk_score", "frp", "city", "month", "day")},
                },
            })
        if not features:
            return None
        return {"type": "FeatureCollection", "features": features}

    @staticmethod
    def _risk_color(val):
        """按数值映射风险颜色（与前端 riskLevel 一致的分档）"""
        if val is None:
            return "#0ea5e9"
        try:
            v = float(val)
        except (TypeError, ValueError):
            return "#0ea5e9"
        if v >= 0.8:
            return "#ef4444"
        if v >= 0.6:
            return "#fb923c"
        if v >= 0.4:
            return "#facc15"
        if v >= 0.2:
            return "#4ade80"
        return "#22d3ee"

    # ========== 执行查询 ==========

    def _exec_history(self, p: dict) -> QueryResult:
        from app.schemas.dashboard import HistoryFireQuery
        sd, ed = None, None
        if p.get("year_start") and p.get("year_end"):
            sd = f"{p['year_start']}-01-01"
            ed = f"{p['year_end']}-12-31"
        elif p.get("year"):
            if p.get("month"):
                sd = f"{p['year']}-{p['month']:02d}-01"
                ed = f"{p['year']}-{p['month']:02d}-28"
            else:
                sd = f"{p['year']}-01-01"
                ed = f"{p['year']}-12-31"
        q = HistoryFireQuery(start_date=sd, end_date=ed, city=p.get("city"), confidence=p.get("confidence"))
        result = self.repo.query_history_fires(q)
        items = result["items"]
        if p.get("sort") == "desc":
            items.sort(key=lambda x: x.get("frp", 0) or 0, reverse=True)
            if p.get("top_k"):
                items = items[: p["top_k"]]
        city_s = f" {p.get('city', '')}" if p.get("city") else ""
        summary = f"查询到{result['total']}条{city_s}历史火点记录"
        if p.get("year_start") and p.get("year_end"):
            summary += f"（{p['year_start']}—{p['year_end']}年）"
        elif p.get("year"):
            summary += f"（{p['year']}年）"
        if items:
            summary += f"，最高 FRP 为 {max((i.get('frp', 0) or 0) for i in items):.1f} MW"
        dc = {}
        for i in items:
            d = i.get("acq_date", "")
            dc[d] = dc.get(d, 0) + 1
        cd = {"labels": list(dc.keys())[:30], "values": list(dc.values())[:30]}
        # 历史火点若缺经纬度，用州市中心点兜底，保证地图可展示（与预测/汇总一致）
        geo_points = []
        for i in items:
            lng, lat = i.get("longitude"), i.get("latitude")
            if lng is None or lat is None:
                center = CITY_CENTERS.get(i.get("city"))
                if center:
                    lng, lat = center[0], center[1]
            if lng is not None and lat is not None:
                geo_points.append({**i, "longitude": lng, "latitude": lat})
        return QueryResult(summary=summary, table_data=items, chart_data=cd,
                           chart_type="bar" if len(cd["labels"]) > 1 else "pie",
                           geo_data=self._build_geojson(geo_points, name_key="city", value_key="frp", color_mode="value"),
                           total=result["total"])

    def _exec_predict(self, p: dict) -> QueryResult:
        from app.schemas.dashboard import PredictRiskQuery
        year = p.get("year", datetime.now().year)
        month = p.get("month")
        vm = "daily" if month else "monthly"
        all_items = []
        if p.get("months"):
            for m in p["months"]:
                res = self.repo.query_predict_risks(PredictRiskQuery(year=year, month=m, view_mode=vm, city=p.get("city")))
                all_items.extend(res["items"])
        else:
            res = self.repo.query_predict_risks(PredictRiskQuery(year=year, month=month, view_mode=vm, city=p.get("city")))
            all_items = res["items"]
        if p.get("sort") == "desc":
            all_items.sort(key=lambda x: x.get("risk_score", 0) or 0, reverse=True)
            if p.get("top_k"):
                all_items = all_items[: p["top_k"]]
        city_s = f" {p.get('city', '')}" if p.get("city") else ""
        summary = f"查询到{len(all_items)}条{city_s}预测火险数据"
        if all_items:
            summary += f"，最高风险评分 {max((i.get('risk_score', 0) or 0) for i in all_items):.4f}"
        cd = {"labels": [i["city"] for i in all_items], "values": [i.get("risk_score", 0) or 0 for i in all_items]}
        # 预测数据若缺经纬度，用州市中心点兜底，保证地图可展示
        geo_points = []
        for i in all_items:
            lng, lat = i.get("longitude"), i.get("latitude")
            if lng is None or lat is None:
                center = CITY_CENTERS.get(i.get("city"))
                if center:
                    lng, lat = center[0], center[1]
            if lng is not None and lat is not None:
                geo_points.append({**i, "longitude": lng, "latitude": lat})
        return QueryResult(summary=summary, table_data=all_items, chart_data=cd, chart_type="bar",
                           geo_data=self._build_geojson(geo_points, name_key="city", value_key="risk_score", color_mode="risk"),
                           total=len(all_items))

    def _exec_summary(self, p: dict) -> QueryResult:
        res = self.repo.get_summary(None, None)
        summary = f"火点总数: {res['total_fire_points']}，高风险: {res['high_risk_count']}，平均 FRP: {res['avg_frp']}"
        tc = res.get("top_cities", [])
        cd = {"labels": [c["city"] for c in tc], "values": [c["count"] for c in tc]}
        # 汇总类查询也生成地图：用各城市中心点 + 火点数着色
        geo_points = []
        for c in tc:
            center = CITY_CENTERS.get(c.get("city"))
            if center:
                geo_points.append({
                    "city": c.get("city"),
                    "count": c.get("count", 0),
                    "longitude": center[0],
                    "latitude": center[1],
                })
        return QueryResult(summary=summary, table_data=tc, chart_data=cd, chart_type="bar",
                           geo_data=self._build_geojson(geo_points, name_key="city", value_key="count", color_mode="value"),
                           total=res["total_fire_points"])