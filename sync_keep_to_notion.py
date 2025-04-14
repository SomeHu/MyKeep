import os
import requests
from notion_client import Client
from dotenv import load_dotenv
from urllib.parse import quote

# 加载环境变量
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
KEEP_MOBILE = os.getenv("KEEP_MOBILE")
KEEP_PASSWORD = os.getenv("KEEP_PASSWORD")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
CITY_ID = os.getenv("CITY_ID", "1798082")
AMAP_KEY = os.getenv("AMAP_KEY")  # 高德地图 Key，用于生成跑步轨迹图

# 校验环境变量
if not all([NOTION_TOKEN, NOTION_DATABASE_ID, KEEP_MOBILE, KEEP_PASSWORD, OPENWEATHER_API_KEY]):
    print("缺少关键环境变量，请检查 NOTION_TOKEN、NOTION_DATABASE_ID、KEEP_MOBILE、KEEP_PASSWORD、OPENWEATHER_API_KEY 是否设置。")
    exit(1)

# 初始化 Notion 客户端
notion = Client(auth=NOTION_TOKEN)

def login_keep(mobile, password):
    r = requests.post(
        "https://api.gotokeep.com/v1.1/users/login",
        json={"mobile": mobile, "password": password}
    )
    r.raise_for_status()
    data = r.json().get("data", {})
    return data.get("token")

def fetch_keep_data(token):
    r = requests.get(
        "https://api.gotokeep.com/pd/v3/stats/detail",
        params={"dateUnit": "all", "type": "", "lastDate": 0},
        headers={"Authorization": f"Bearer {token}"}
    )
    r.raise_for_status()
    return r.json().get("data", {}).get("records", [])

def get_weather(city_id, api_key):
    url = f"http://api.openweathermap.org/data/2.5/weather?id={city_id}&appid={api_key}&units=metric&lang=zh_cn"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        wdata = resp.json()
        if wdata.get("cod") == 200:
            desc = wdata["weather"][0]["description"]
            temp = wdata["main"]["temp"]
            return f"{desc} ~ {temp}°C"
        return f"天气请求失败: {wdata.get('message','未知错误')}"
    except:
        return "无法获取天气信息"

def page_exists(notion_client, database_id, date_str, workout_id):
    query_res = notion_client.databases.query(
        database_id=database_id,
        filter={
            "and": [
                {"property": "日期", "date": {"equals": date_str}},
                {"property": "类型", "rich_text": {"contains": workout_id}}
            ]
        }
    )
    return len(query_res.get("results", [])) > 0

def create_notion_page(properties):
    return notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties=properties
    )

def append_image_block(page_id, image_url):
    notion.blocks.children.append(
        block_id=page_id,
        children=[
            {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {
                        "url": image_url
                    }
                }
            }
        ]
    )

def generate_run_map_url(coords):
    if not AMAP_KEY or not coords:
        return ""
    point_list = []
    for (lat, lng) in coords:
        # 高德静态地图坐标顺序：lng,lat
        point_list.append(f"{lng},{lat}")
    path_str = ";".join(point_list)
    base_url = "https://restapi.amap.com/v3/staticmap"
    params = {
        "key": AMAP_KEY,
        "size": "1024*512",
        "paths": f"2,0xFF0000,1,,:{path_str}"
    }
    req = requests.Request("GET", base_url, params=params).prepare()
    return req.url

def main():
    token = login_keep(KEEP_MOBILE, KEEP_PASSWORD)
    if not token:
        print("获取 Keep token 失败，请确认 Keep 账号密码是否正确。")
        return

    records = fetch_keep_data(token)
    print(f"共获取到 {len(records)} 组运动记录")

    for group in records:
        logs = group.get("logs", [])
        for item in logs:
            stats = item.get("stats") or {}
            if not stats:
                continue

            done_date = stats.get("doneDate", "")
            workout_id = stats.get("id", "")
            sport_type = stats.get("type", "").lower()
            if page_exists(notion, NOTION_DATABASE_ID, done_date, workout_id):
                continue

            km = stats.get("kmDistance", 0.0)
            duration = stats.get("duration", 0)
            calorie = stats.get("calorie", 0)
            name = stats.get("name", "未命名")
            name_suffix = stats.get("nameSuffix", "")
            heart_rate_data = stats.get("heartRate", {})
            avg_hr = heart_rate_data.get("averageHeartRate", 0) if isinstance(heart_rate_data, dict) else 0

            weather_info = get_weather(CITY_ID, OPENWEATHER_API_KEY)
            pace_seconds = int(duration / km) if km > 0 else 0
            vendor = stats.get("vendor", {})
            source = vendor.get("source", "Keep")
            device_model = vendor.get("deviceModel", "")
            vendor_str = (source + " " + device_model).strip()
            title = f"🏃‍♂️ {name} {name_suffix}"

            gps_points = stats.get("gpsData", [])
            coords = []
            for p in gps_points:
                lat = p.get("lat")
                lng = p.get("lng")
                if lat and lng:
                    coords.append((lat, lng))

            track_url = ""
            if sport_type in ["running", "jogging"] and coords:
                track_url = generate_run_map_url(coords)

            props = {
                "名称": {"title": [{"text": {"content": title}}]},
                "日期": {"date": {"start": done_date}},
                "时长": {"number": duration},
                "距离": {"number": km},
                "卡路里": {"number": calorie},
                "类型": {"rich_text": [{"text": {"content": workout_id}}]},
                "平均配速": {"number": pace_seconds},
                "平均心率": {"number": avg_hr},
                "天气": {"rich_text": [{"text": {"content": weather_info}}]},
                "数据来源": {"rich_text": [{"text": {"content": vendor_str}}]}
            }

            # 如果想在数据库属性中也记录轨迹图链接，须在 Notion 里建好同名字段，如 URL 类型
            if track_url:
                props["轨迹图"] = {"url": track_url}

            try:
                new_page = create_notion_page(props)
                print(f"已创建页面: {done_date} - {title}")
            except Exception as e:
                print(f"创建页面失败: {done_date} - {title} -> {e}")
                continue

            page_id = new_page["id"]

            # 插入跑步轨迹图
            if track_url:
                try:
                    append_image_block(page_id, track_url)
                    print("已插入跑步轨迹图")
                except Exception as e:
                    print(f"插入跑步轨迹图失败: {e}")

            # 如果是步行且有步频图（此字段仅举例，需查看 Keep 是否返回类似字段）
            step_freq_chart_url = stats.get("stepFreqChart", "")
            if sport_type == "walking" and step_freq_chart_url:
                try:
                    append_image_block(page_id, step_freq_chart_url)
                    print("已插入步频图")
                except Exception as e:
                    print(f"插入步频图失败: {e}")

if __name__ == "__main__":
    main()
