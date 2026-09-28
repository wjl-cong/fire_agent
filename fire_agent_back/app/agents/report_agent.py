"""
报告 Agent — 生成分析报告（LLM 调用统一走 llm_invoker：重试/熔断/降级）
"""
from app.core.config import settings
from app.core.llm import llm_available
from app.core.llm_invoker import invoke_llm


class ReportAgent:
    """报告 Agent：将数据与分析结果转为可读报告"""

    def __init__(self, llm_client=None):
        self.llm = llm_client  # 保留注入能力；实际调用统一走 invoke_llm

    async def generate_report(self, data: dict, analysis: dict = None, knowledge: list[str] = None) -> str:
        """生成 Markdown 格式报告（头部系统注入生成时间，末尾统一追加系统署名）"""
        from datetime import datetime
        head = f"> 报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        if llm_available():
            return head + await self._generate_with_llm(data, analysis, knowledge) + settings.REPORT_FOOTER
        return head + self._generate_template(data, analysis, knowledge) + settings.REPORT_FOOTER

    async def generate_summary(self, data: dict) -> str:
        """生成简短摘要"""
        total = data.get("total", 0)
        city = "全部"
        if data.get("items") and len(data["items"]) > 0:
            item = data["items"][0]
            city = item.get("city", "全部")
        return f"共查询到 {total} 条火点记录（{city}），最高风险等级待分析。"

    async def _generate_with_llm(self, data: dict, analysis: dict, knowledge: list[str]) -> str:
        """使用 LLM 生成报告"""
        data_summary = f"数据总量: {data.get('total', 0)}"
        analysis_summary = analysis.get("summary", "未分析") if analysis else "未分析"
        knowledge_text = "\n".join(knowledge) if knowledge else "未检索"

        prompt = f"""你是一个森林火险分析报告专家。请根据以下信息生成专业的分析报告。

## 数据摘要
{data_summary}

## 空间分析结果
{analysis_summary}

## 知识库参考
{knowledge_text}

请生成包含以下内容的 Markdown 报告（正式公文风格，分条列举为主，每条「结论+数据+阐释」三要素齐全）：
1. 概述（分条列出 3-5 条核心结论）
2. 数据分析详述（用 Markdown 表格呈现关键统计并配「表 1 说明：」图注文字）
3. 风险区域识别（分条：每条含区域名、具体数据、成因阐释）
4. 应急建议（分条，每条附一句依据）
5. 参考依据（编号列举：来源类型+名称+时间口径；报告生成时间由系统自动注入，无需撰写）"""

        res = invoke_llm(prompt)
        if res is None:
            return self._generate_template(data, analysis, knowledge)
        return res.text if res.text else self._generate_template(data, analysis, knowledge)

    def _generate_template(self, data: dict, analysis: dict, knowledge: list[str]) -> str:
        """生成模板报告（与 LLM 报告同结构：表格+图注+分条+参考依据）"""
        total = data.get("total", 0)
        analysis_summary = analysis.get("summary", "未分析") if analysis else "未分析"
        return f"""# 火险分析报告

## 一、执行摘要
1. 本次共汇总火险相关记录 {total} 条。
2. 空间分析结论：{analysis_summary}
3. 建议重点关注高风险区域并加强巡防部署。

## 二、数据分析
| 指标 | 数值 |
| --- | --- |
| 火点记录总数 | {total} 条 |
| 空间分析结论 | {analysis_summary} |

表 1 说明：上表汇总本次分析的核心统计指标；火点记录总数反映监测时段内的整体活跃程度，空间分析结论指示热点聚集方位，二者结合用于判断当前火险形势。

## 三、处置建议
1. 密切监测高风险区域——依据：空间分析已识别热点聚集方位。
2. 加强巡防力量部署——依据：历史数据显示火点存在区域集中性。
3. 做好应急准备——依据：火险形势动态变化，需预留处置能力。

## 附：参考依据
1. 历史火点统计（NASA FIRMS 卫星观测，2021-2025）
2. 空间分析模块（GisAgent）输出结果

## 说明
> 此报告为自动生成模板。配置 LLM_API_KEY 后可生成包含详细分析内容的专业报告。"""