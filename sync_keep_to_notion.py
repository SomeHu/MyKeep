import os
import requests
from notion_client import Client
from dotenv import load_dotenv
import datetime

# 加载环境变量
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
KEEP_MOBILE = os.getenv("KEEP_MOBILE")
KEEP_PASSWORD = os.getenv("KEEP_PASSWORD")
WEATHERSTACK_API_KEY = "314ea3ee630aca1db8880aee4d48dc62"  # 你提供的 API 密钥

# 登录 Keep 获取 token
login_res = requests.post("https://api.gotokeep.com/v1.1/users/login", json={
    "mobile": KEEP_MOBILE,
    "password": KEEP_PASSWORD
})
token = login_res.json().get("data", {}).get("token")

# 请求 Keep 运动数据
res = requests.get("https://api.gotokeep.com/pd/v3/stats/detail", params={
    "dateUnit": "all", "type": "", "lastDate": 0
}, headers={"Authorization": f"Bearer {token}"})

data = res.json().get("data", {}).get("records", [])
print(f"\U0001f440 汇总所有类型后的记录条数： {len(data)}")

# 设置 emoji 分类
TYPE_EMOJI_MAP = {
    "running": "🏃‍♂️",
    "walking": "🚶",
    "cycling": "🚴",
    "swimming": "🏊",
    "default": "🏋️"
}

# 初始化 Notion 客户端
notion = Client(auth=NOTION_TOKEN)

# 获取天气信息
# 获取天气信息
def get_weather(location):
    # 获取标准城市名称
    location_name = get_location_name(location)

    # 如果获取到正确的城市名称，再请求天气数据
    if location_name != "未找到城市信息":
        weather_url = f"http://api.weatherstack.com/current?access_key={WEATHERSTACK_API_KEY}&query={location_name}&language=zh"
        response = requests.get(weather_url)
        weather_data = response.json()

        # 检查 API 返回的数据是否有效
        if "current" in weather_data:
            temperature = weather_data["current"].get("temperature", "未知")
            weather_description = weather_data["current"].get("weather_descriptions", ["未知"])[0]
            return f"{weather_description} ~ {temperature}°C"
        else:
            return "无法获取天气信息"
    else:
        return "无法获取城市数据"



# 去重辅助函数
def page_exists(done_date, workout_id):
    query = notion.databases.query(
        **{
            "database_id": NOTION_DATABASE_ID,
            "filter": {
                "and": [
                    {"property": "日期", "date": {"equals": done_date}},
                    {"property": "类型", "rich_text": {"contains": workout_id}}
                ]
            }
        }
    )
    return len(query.get("results", [])) > 0

# 开始处理每条记录
for group in data:
    logs = group.get("logs", [])
    for item in logs:
        stats = item.get("stats")
        if not stats:
            continue  # ⚠️ 跳过没有 stats 的记录

        done_date = stats.get("doneDate", "")
        if not done_date.startswith("2025"):
            continue

        sport_type = stats.get("type", "unknown")
        workout_id = stats.get("id", "")
        km = stats.get("kmDistance", 0.0)

        print(f"\U0001f4c5 当前处理日期: {done_date}, 类型: {sport_type}, 距离: {km}")

        if page_exists(done_date, workout_id):
            continue

        # 生成标题
        title = f"{TYPE_EMOJI_MAP.get(sport_type, TYPE_EMOJI_MAP['default'])} {stats.get('name', '未命名')} {stats.get('nameSuffix', '')}"

        # 计算配速（秒/公里）
        duration = stats.get("duration", 0)
        pace_seconds = int(duration / km) if km > 0 else 0

        # 获取心率
        hr = stats.get("heartRate")
        avg_hr = hr.get("averageHeartRate", 0) if isinstance(hr, dict) else 0

        # 获取来源（Keep App, vivo, Apple 等）
        vendor = stats.get("vendor", {})
        source = vendor.get("source", "Keep")
        device = vendor.get("deviceModel", "")
        vendor_display = f"{source} {device}".strip()

        # 获取天气信息（使用城市名称）
        weather_info = get_weather("衡阳")

        # 写入 Notion
        notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties={
            "名称": {"title": [{"text": {"content": title}}]},
            "日期": {"date": {"start": done_date}},
            "时长": {"number": duration},
            "距离": {"number": km},
            "卡路里": {"number": stats.get("calorie")},
            "类型": {"rich_text": [{"text": {"content": workout_id}}]},
            "平均配速": {"number": pace_seconds},
            "平均心率": {"number": avg_hr},
            "轨迹图": {
                "files": [{
                    "name": "track.jpg",
                    "external": {"url": stats.get("trackWaterMark", "")}
                }] if stats.get("trackWaterMark") else []
            },
            "数据来源": {"rich_text": [{"text": {"content": vendor_display}}]},
            "天气": {"rich_text": [{"text": {"content": weather_info}}]}  # 添加天气字段
        })

print("\u2705 已完成 Notion 同步")
