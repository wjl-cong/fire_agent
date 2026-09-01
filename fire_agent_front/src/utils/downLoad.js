/**
 * @fileoverview 地图导出工具 — 将 OpenLayers 地图渲染为 PNG 图片
 * 原理：监听 rendercomplete 事件，将所有图层 canvas 绘制到离屏 Canvas，导出为 Blob
 */

import { saveAs } from "file-saver";

// 导出地图为 PNG
export const downloadMap = (map) => {
    map.once("rendercomplete", () => {
        const mapCanvas = document.createElement("canvas");
        const size = map.getSize();
        mapCanvas.width = size[0];
        mapCanvas.height = size[1];
        const mapContext = mapCanvas.getContext("2d");

        // 遍历所有图层 canvas，应用透明度与变换矩阵后绘制到离屏 Canvas
        Array.prototype.forEach.call(
            document.querySelectorAll(".ol-layer canvas"),
            (canvas) => {
                if (canvas.width > 0) {
                    const opacity = canvas.parentNode.style.opacity;
                    mapContext.globalAlpha = opacity === "" ? 1 : Number(opacity);
                    const transform = canvas.style.transform;
                    const matrix = transform
                        .match(/^matrix\(([^(]*)\)$/)[1]
                        .split(",")
                        .map(Number);
                    CanvasRenderingContext2D.prototype.setTransform.apply(
                        mapContext,
                        matrix,
                    );
                    mapContext.drawImage(canvas, 0, 0);
                }
            },
        );

        mapCanvas.toBlob((blob) => saveAs(blob, "map.png"));
    });
    map.renderSync(); // 同步触发完整重绘，确保 rendercomplete 在当前栈触发
};