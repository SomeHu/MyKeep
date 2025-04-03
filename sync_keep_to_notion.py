# 导入所需的库
import os
import requests
from notion_client import Client  # 添加这一行，导入 Client 类
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
KEEP_MOBILE = os.getenv("KEEP_MOBILE")
KEEP_PASSWORD = os.getenv("KEEP_PASSWORD")
QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY")  # 新的天气 API 密钥

# 初始化 Notion 客户端
notion = Client(auth=NOTION_TOKEN)

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

TYPE_EMOJI_MAP = {
    "running": "🏃‍♂️",
    "walking": "🚶",
    "cycling": "🚴",
    "swimming": "🏊",
    "hiking": "🥾",
    "default": "🏋️"
}

notion = Client(auth=NOTION_TOKEN)

def get_weather(location_code):
    weather_url = f"https://api.qweather.com/v7/weather/now?location={location_code}&key={QWEATHER_API_KEY}"
    print(f"Weather API URL: {weather_url}")  # 调试 URL
    try:
        response = requests.get(weather_url)
        response.raise_for_status()  # 如果状态码不是 200，会抛出异常
        weather_data = response.json()
        print(f"Weather data: {weather_data}")  # 调试返回数据
        if weather_data.get("code") == "200":
            temperature = weather_data["now"]["temp"]
            description = weather_data["now"]["text"]
            return f"{description} ~ {temperature}°C"
        else:
            return f"天气 API 返回错误: {weather_data.get('code')} - {weather_data.get('message', '未知错误')}"
    except requests.exceptions.RequestException as e:
        return f"天气请求失败: {str(e)}"



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

for group in data:
    logs = group.get("logs", [])
    for item in logs:
        stats = item.get("stats")
        if not stats:
            continue
        done_date = stats.get("doneDate", "")
        # if not done_date.startswith("2025"):  # 临时注释，同步所有日期
        #     continue

        sport_type = stats.get("type", "unknown")
        workout_id = stats.get("id", "")
        km = stats.get("kmDistance", 0.0)

        print(f"\U0001f4c5 当前处理日期: {done_date}, 类型: {sport_type}, 距离: {km}")

        if page_exists(done_date, workout_id):
            continue

        # 使用新的天气 API 获取天气信息
        location_code = "101250404"  # 例如，使用 Qidong 城市的代码
        weather_info = get_weather(location_code)
        title = f"{TYPE_EMOJI_MAP.get(sport_type, TYPE_EMOJI_MAP['default'])} {stats.get('name', '未命名')} {stats.get('nameSuffix', '')}"
        duration = stats.get("duration", 0)
        pace_seconds = int(duration / km) if km > 0 else 0
        hr = stats.get("heartRate")
        avg_hr = hr.get("averageHeartRate", 0) if isinstance(hr, dict) else 0
        vendor = stats.get("vendor", {})
        source = vendor.get("source", "Keep")
        device = vendor.get("deviceModel", "")
        vendor_display = f"{source} {device}".strip()

        try:
            notion.pages.create(
                parent={"database_id": NOTION_DATABASE_ID},
                properties={
                    "名称": {"title": [{"text": {"content": title}}]},
                    "日期": {"date": {"start": done_date}},
                    "时长": {"number": duration},
                    "距离": {"number": km},
                    "卡路里": {"number": stats.get("calorie")},
                    "类型": {"rich_text": [{"text": {"content": workout_id}}]},
                    "平均配速": {"number": pace_seconds},
                    "平均心率": {"number": avg_hr},
                    "天气": {"rich_text": [{"text": {"content": weather_info}}] if weather_info else []},
                    "轨迹图": {"files": [{"name": "track.jpg", "external": {"url": stats.get("trackWaterMark", "")}}] if stats.get("trackWaterMark") else []},
                    "数据来源": {"rich_text": [{"text": {"content": vendor_display}}]}
                }
            )
            print(f"\u2705 已同步: {done_date} - {title}")
        except Exception as e:
            print(f"\U0001f6ab 同步失败: {done_date} - {title}, 错误: {str(e)}")

print("\u2705 已完成所有 Notion 同步")
