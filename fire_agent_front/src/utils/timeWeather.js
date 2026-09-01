/**
 * @fileoverview 时间与天气工具函数
 * - 格式化系统时间/日期（界面时钟）
 * - 调用高德地图 API 获取 IP 定位与实时天气
 */

// 更新当前时间（HH:mm:ss，24小时制）
export const upDateCurrentTime = (currentTimeRef) => {
    const now = new Date();
    currentTimeRef.value = now.toLocaleTimeString("zh-CN", {
        hour12: false
    });
};

// 更新当前日期（YYYY年MM月DD日 星期X）
export const upDateCurrentDate = (currentDateRef) => {
    const now = new Date();
    const options = {
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "long",
    };
    currentDateRef.value = now.toLocaleDateString("zh-CN", options);
};

/**
 * 浏览器定位（经纬度），超时则返回 null
 */
const getBrowserPosition = () =>
    new Promise((resolve) => {
        if (typeof navigator === "undefined" || !navigator.geolocation) {
            resolve(null);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) =>
            resolve({
                lng: pos.coords.longitude,
                lat: pos.coords.latitude,
            }),
            () => resolve(null), {
                enableHighAccuracy: false,
                timeout: 4500,
                maximumAge: 300000,
            },
        );
    });

/**
 * 逆地理：经纬度 → 城市名 / adcode（比纯 IP 更接近真实位置，如成都 vs 绵阳）
 */
const regeoToCity = async (amapKey, lng, lat) => {
    const url = `https://restapi.amap.com/v3/geocode/regeo?key=${amapKey}&location=${lng},${lat}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.status !== "1" || !data.regeocode?.addressComponent) return null;
    const ac = data.regeocode.addressComponent;
    let name = ac.city;
    if (Array.isArray(name) || !name) name = ac.district || ac.province || "";
    if (typeof name === "string" && name.trim()) return {
        city: name.trim(),
        adcode: ac.adcode
    };
    if (ac.adcode) return {
        city: null,
        adcode: ac.adcode
    };
    return null;
};

// 根据定位获取城市并查询天气（第二参数为 weatherInfo 的 ref）
// 优先：浏览器经纬度 + 逆地理；其次：IP 定位（优先城市汉字名再 adcode）
export const fethLocation = async (amapKey, weatherInfoRef) => {
    try {
        const pos = await getBrowserPosition();
        if (pos) {
            const rg = await regeoToCity(amapKey, pos.lng, pos.lat);
            if (rg?.city) {
                await fethWeather(rg.city, amapKey, weatherInfoRef, rg.adcode);
                return;
            }
            if (rg?.adcode) {
                await fethWeather(rg.adcode, amapKey, weatherInfoRef, null);
                return;
            }
        }

        const response = await fetch(
            `https://restapi.amap.com/v3/ip?key=${amapKey}`,
        );
        const data = await response.json();
        if (data.status === "1") {
            const cityName = data.city && String(data.city).trim();
            const param =
                cityName ||
                (data.adcode && String(data.adcode).length > 0 ? data.adcode : "510100");
            await fethWeather(param, amapKey, weatherInfoRef, data.adcode || null);
        } else {
            console.error("获取位置失败", data.info, data);
        }
    } catch (error) {
        console.error("获取位置失败", error);
    }
};

// 查询实时天气：先按 cityParam（城市名或 adcode），失败则用 fallbackAdcode 再试
export const fethWeather = async (cityParam, amapKey, weatherInfoRef, fallbackAdcode) => {
    const tryOnce = async (city) => {
        const q = encodeURIComponent(String(city));
        const response = await fetch(
            `https://restapi.amap.com/v3/weather/weatherInfo?city=${q}&key=${amapKey}`,
        );
        return response.json();
    };

    try {
        if (!weatherInfoRef) return;
        let data = await tryOnce(cityParam);
        const ok = (d) => d.status === "1" && d.lives && d.lives.length > 0;
        if (
            !ok(data) &&
            fallbackAdcode &&
            String(cityParam) !== String(fallbackAdcode)
        ) {
            data = await tryOnce(fallbackAdcode);
        }
        if (ok(data)) {
            weatherInfoRef.value = data.lives[0];
        } else {
            console.error("获取天气失败", data.info, data);
        }
    } catch (error) {
        console.error("获取天气失败", error);
    }
};