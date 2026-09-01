/**
 * @fileoverview 矢量标绘工具 — 封装 OpenLayers Draw 交互
 * 支持绘制：点(Point)、线(LineString)、面(Polygon)、矩形(Box)、正方形(Square)
 */

import Draw, { createRegularPolygon } from 'ol/interaction/Draw'
import Polygon from 'ol/geom/Polygon'

// 创建 Draw 交互实例
// type: Point | LineString | Polygon | Square | Box
// source: VectorSource，存放绘制结果
// success: 绘制完成回调，参数为 Feature 对象
export const createDraw = ({ type, source, success }) => {
    let geometryFunction = null
    let maxPoints = null

    // 正方形：映射为 Circle + createRegularPolygon(4)
    if (type === 'Square') {
        type = 'Circle'
        geometryFunction = createRegularPolygon(4)
    }

    // 矩形（Box）：映射为 LineString，接收2个对角点，转换为闭合矩形 Polygon
    if (type === 'Box') {
        type = 'LineString'
        geometryFunction = (coordinate, geometry) => {
            if (!geometry) geometry = new Polygon(null)
            const start = coordinate[0]
            const end = coordinate[1]
            geometry.setCoordinates([
                [start, [start[0], end[1]], end, [end[0], start[1]], start]
            ])
            return geometry
        }
        maxPoints = 2
    }

    const draw = new Draw({ type, source, geometryFunction, maxPoints })

    if (typeof success === 'function') {
        draw.on('drawend', (e) => success(e.feature))
    }

    return draw
}