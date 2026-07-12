"""
weather 工具 — 查询天气、空气质量、地名→经纬度
使用 Open-Meteo 免费 API（无需 Key，非商业用途免费）
"""
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import ToolPlugin, ToolRegistry

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


class Weather(ToolPlugin):
    name = "weather"
    description = (
        "查询天气、空气质量或将地名转换为经纬度坐标。"
        "支持：1）按城市名查天气（自动识别坐标）；2）按经纬度查天气；3）查空气质量；4）地名→坐标。"
        "天气数据来自 Open-Meteo（免费气象服务）。"
    )
    segment = "file_operations"
    parameters = {
        "action": {
            "type": "string",
            "enum": ["forecast", "air_quality", "geocode"],
            "description": "操作类型：forecast=查天气, air_quality=查空气质量, geocode=地名→经纬度",
        },
        "city": {
            "type": "string",
            "description": "城市名（与 latitude/longitude 二选一）。例如「北京」「Tokyo」「New York」",
        },
        "latitude": {"type": "number", "description": "纬度（与 city 二选一，配合 longitude 使用）"},
        "longitude": {"type": "number", "description": "经度（与 city 二选一，配合 latitude 使用）"},
        "days": {
            "type": "integer",
            "description": "预报天数（forecast 有效，1-7，默认 3）",
        },
    }
    required = ["action"]
    states = ["active", "dnd"]
    admin_description = "查询天气、空气质量、地理编码。使用 Open-Meteo 免费 API，无需配置 Key。"
    trigger_condition = "用户问到天气、空气质量或地名坐标时"

    async def execute(self, db: AsyncSession, agent_id: int, group_id: int | None,
                      arguments: dict, context: dict) -> dict:
        action = arguments["action"]
        city = arguments.get("city")
        lat = arguments.get("latitude")
        lon = arguments.get("longitude")
        days = min(max(arguments.get("days", 3), 1), 7)

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                # 如有城市名，先地理编码
                if city and (lat is None or lon is None):
                    geo = await self._geocode(client, city)
                    if not geo:
                        return {"error": True, "message": f"未找到城市「{city}」"}
                    lat, lon = geo["latitude"], geo["longitude"]
                    city_name = geo.get("name", city)
                    country = geo.get("country", "")
                else:
                    city_name = city or f"({lat}, {lon})"
                    country = ""

                if action == "geocode":
                    return {"success": True, "name": city_name, "country": country, "latitude": lat, "longitude": lon}

                if action == "forecast":
                    return await self._forecast(client, lat, lon, city_name, country, days)

                if action == "air_quality":
                    return await self._air_quality(client, lat, lon, city_name, country)

        except httpx.TimeoutException:
            return {"error": True, "message": "查询超时，请稍后再试"}
        except Exception as e:
            logger.error(f"weather 失败: {e}", exc_info=True)
            return {"error": True, "message": f"查询失败: {str(e)}"}

    async def _geocode(self, client: httpx.AsyncClient, city: str) -> dict | None:
        resp = await client.get(GEOCODING_URL, params={"name": city, "count": 5, "language": "zh"})
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        r = results[0]
        return {
            "name": r.get("name", city),
            "country": r.get("country", ""),
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "timezone": r.get("timezone", ""),
        }

    async def _forecast(self, client: httpx.AsyncClient, lat: float, lon: float,
                        city: str, country: str, days: int) -> dict:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "current_weather": True,
            "timezone": "auto",
            "forecast_days": days,
        }
        resp = await client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        max_temps = daily.get("temperature_2m_max", [])
        min_temps = daily.get("temperature_2m_min", [])
        precips = daily.get("precipitation_sum", [])
        weather_codes = daily.get("weathercode", [])

        current = data.get("current_weather", {})
        forecasts = []
        for i in range(len(dates)):
            forecasts.append({
                "date": dates[i] if i < len(dates) else "",
                "max_temp": max_temps[i] if i < len(max_temps) else None,
                "min_temp": min_temps[i] if i < len(min_temps) else None,
                "precipitation": precips[i] if i < len(precips) else None,
                "weather_code": weather_codes[i] if i < len(weather_codes) else None,
            })

        return {
            "success": True,
            "location": city,
            "country": country,
            "latitude": lat,
            "longitude": lon,
            "current": {
                "temperature": current.get("temperature"),
                "wind_speed": current.get("windspeed"),
                "weather_code": current.get("weathercode"),
            },
            "forecast": forecasts,
        }

    async def _air_quality(self, client: httpx.AsyncClient, lat: float, lon: float,
                           city: str, country: str) -> dict:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "european_aqi,us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
            "timezone": "auto",
        }
        resp = await client.get(AIR_QUALITY_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        return {
            "success": True,
            "location": city,
            "country": country,
            "european_aqi": current.get("european_aqi"),
            "us_aqi": current.get("us_aqi"),
            "pm2_5": current.get("pm2_5"),
            "pm10": current.get("pm10"),
            "nitrogen_dioxide": current.get("nitrogen_dioxide"),
            "ozone": current.get("ozone"),
        }


ToolRegistry.register(Weather)
