/**
 * @fileoverview 地图量测工具 — 基于 Turf.js 计算折线距离与多边形面积
 */

import * as turf from "@turf/turf";

// 计算折线长度（公里）
export const calculateDistance = (coordinates) => {
    const line = turf.lineString(coordinates);
    const length = turf.length(line, { units: "kilometers" });
    ElMessageBox.alert(`距离为：${length.toFixed(2)} 千米`);
};

// 计算多边形面积（平方千米）和周长（公里）
// coordinates[0] 取外环坐标（OL Polygon 格式为 [[[...]]]）
export const calculateArea = (coordinates) => {
    const polygon = turf.polygon([coordinates]);
    const area = turf.area(polygon);
    const perimeterLine = turf.lineString(coordinates);
    const perimeter = turf.length(perimeterLine, { units: "kilometers" });
    ElMessageBox.alert(
        `面积是：${area.toFixed(2)} 平方千米，周长是：${perimeter.toFixed(2)} 千米`,
    );
};