"""
报告 Agent — 使用 LangChain LLM 生成分析报告
"""
from app.core.config import settings
from app.core.llm import get_llm, llm_available


class ReportAgent:
    """报告 Agent：将数据与分析结果转为可读报告"""

    def __init__(self, llm_client=None):
        self.llm = llm_client or get_llm()

    async def generate_report(self, data: dict, analysis: dict = None, knowledge: list[str] = None) -> str:
        """生成 Markdown 格式报告（末尾统一追加系统署名）"""
        if llm_available() and self.llm:
            return await self._generate_with_llm(data, analysis, knowledge) + settings.REPORT_FOOTER
        return self._generate_template(data, analysis, knowledge) + settings.REPORT_FOOTER

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

请生成包含以下内容的 Markdown 报告：
1. 概述
2. 数据分析详述
3. 风险区域识别
4. 应急建议
5. 参考依据"""

        resp = self.llm.invoke(prompt)
        return resp.content if hasattr(resp, "content") else str(resp)

    def _generate_template(self, data: dict, analysis: dict, knowledge: list[str]) -> str:
        """生成模板报告"""
        total = data.get("total", 0)
        analysis_summary = analysis.get("summary", "未分析") if analysis else "未分析"
        return f"""# 火险分析报告

## 概述
基于火险数据的分析结果。

## 数据分析
- 数据总量：{total} 条
- 空间分析：{analysis_summary}

## 处置建议
1. 密切监测高风险区域
2. 加强巡防力量部署
3. 做好应急准备

## 说明
> 此报告为自动生成模板。配置 LLM_API_KEY 后可生成包含详细分析内容的专业报告。"""