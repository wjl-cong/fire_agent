/**
 * @fileoverview 火点数据解析工具 — 从 GeoJSON 提取统计指标
 * 输出：置信度分布 / 每日频次 / 昼夜分布 / FRP 分段统计
 *
 * 用法：
 *   parseGeoData()              — 使用默认本地 JSON
 *   parseGeoData(geoJsonData)   — 使用外部传入数据（API 或本地）
 */

import defaultGeoData from "@/assets/Yunnan_fire.json";

export const parseGeoData = (geoData) => {
  // 如果没传参，使用默认本地 JSON
  if (geoData === undefined) {
    geoData = defaultGeoData
  }
    if (!geoData || !geoData.features || !Array.isArray(geoData.features)) {
        console.warn("GeoData is invalid or empty:", geoData);
        return {
            rawFeatures: [],
            confidenceCounts: { low: 0, nominal: 0, high: 0 },
            dailyCounts: [],
            dayNightCounts: { D: 0, N: 0 },
            frpDistribution: { "0-20": 0, "20-50": 0, "50-100": 0, ">100": 0 },
        };
    }

    try {
        // 提取属性 + 补充经纬度 + 按时间降序排列
        const features = geoData.features
            .map((feature) => {
                const props = feature.properties || {};
                if (feature.geometry && feature.geometry.coordinates) {
                    props.longitude = feature.geometry.coordinates[0].toFixed(3);
                    props.latitude = feature.geometry.coordinates[1].toFixed(3);
                }
                return props;
            })
            .sort((a, b) => {
                return (
                    new Date(
                        b.acq_date +
                        " " +
                        b.acq_time.substring(0, 2) +
                        ":" +
                        b.acq_time.substring(2, 4),
                    ) -
                    new Date(
                        a.acq_date +
                        " " +
                        a.acq_time.substring(0, 2) +
                        ":" +
                        a.acq_time.substring(2, 4),
                    )
                );
            });

        // 初始化统计容器
        const confidenceCounts = { low: 0, nominal: 0, high: 0 };
        const dailyCountsMap = {};
        const dayNightCounts = { D: 0, N: 0 };
        const frpDistribution = { "0-20": 0, "20-50": 0, "50-100": 0, ">100": 0 };

        // 遍历统计
        features.forEach((props) => {
            // 置信度：high / nominal / low
            const conf = props.conf || "low";
            if (confidenceCounts[conf] !== undefined) confidenceCounts[conf]++;
            else confidenceCounts["low"]++;

            // 每日频次
            if (props.acq_date)
                dailyCountsMap[props.acq_date] =
                (dailyCountsMap[props.acq_date] || 0) + 1;

            // 昼夜：D=白天 N=夜间
            if (props.daynight === "D" || props.daynight === "N")
                dayNightCounts[props.daynight]++;

            // FRP 分段（单位 MW）
            const frp = parseFloat(props.frp);
            if (!isNaN(frp)) {
                if (frp <= 20) frpDistribution["0-20"]++;
                else if (frp <= 50) frpDistribution["20-50"]++;
                else if (frp <= 100) frpDistribution["50-100"]++;
                else frpDistribution[">100"]++;
            }
        });

        // Map 转数组（ECharts 格式），按日期升序
        const dailyCounts = Object.entries(dailyCountsMap)
            .sort((a, b) => new Date(a[0]) - new Date(b[0]))
            .map(([date, count]) => ({ name: date, value: count }));

        return {
            rawFeatures: features,
            confidenceCounts,
            dailyCounts,
            dayNightCounts,
            frpDistribution,
        };
    } catch (error) {
        console.error("Error parsing GeoData:", error);
        return {
            rawFeatures: [],
            confidenceCounts: { low: 0, nominal: 0, high: 0 },
            dailyCounts: [],
            dayNightCounts: { D: 0, N: 0 },
            frpDistribution: { "0-20": 0, "20-50": 0, "50-100": 0, ">100": 0 },
        };
    }
};