```python
import json
import os
from datetime import datetime

# =========================
# FILE DATABASE
# =========================

DATA_FILE = "data.json"


# =========================
# LOAD DATA
# =========================

def load_data():
    """
    Đọc dữ liệu từ file JSON.
    Nếu chưa tồn tại thì tạo file mới.
    """

    if not os.path.exists(DATA_FILE):

        data = {
            "plants": [],
            "chat_history": []
        }

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return data

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# =========================
# SAVE DATA
# =========================

def save_data(data):
    """
    Ghi dữ liệu vào file JSON
    """

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# ADD PLANT
# =========================

def add_plant(data, name, date):
    """
    Thêm cây mới
    """

    plants = data.get("plants", [])

    if plants:
        new_id = max(p["id"] for p in plants) + 1
    else:
        new_id = 1

    plant = {
        "id": new_id,
        "name": name,
        "date": date,
        "logs": []
    }

    data["plants"].append(plant)

    save_data(data)

    return data


# =========================
# DELETE PLANT
# =========================

def delete_plant(data, plant_id):
    """
    Xóa cây theo ID
    """

    data["plants"] = [
        p for p in data["plants"]
        if p["id"] != plant_id
    ]

    save_data(data)

    return data


# =========================
# ADD CHAT HISTORY
# =========================

def add_chat(data, user_msg, ai_msg):
    """
    Lưu lịch sử chat AI
    """

    if "chat_history" not in data:
        data["chat_history"] = []

    data["chat_history"].append({
        "user": user_msg,
        "ai": ai_msg,
        "time": datetime.now().strftime("%d/%m/%Y %H:%M")
    })

    save_data(data)

    return data


# =========================
# ADD LOG (NHẬT KÝ CHĂM SÓC)
# =========================

def add_log(data, plant_id, action_type, content):
    """
    plant_id: ID cây
    action_type: "Bón phân" hoặc "Phun thuốc"
    content: Nội dung chi tiết
    """

    for p in data["plants"]:

        if p["id"] == plant_id:

            # nếu chưa có logs thì tạo
            if "logs" not in p:
                p["logs"] = []

            # thêm bản ghi mới
            p["logs"].insert(0, {
                "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "type": action_type,
                "content": content
            })

            break

    save_data(data)

    return data
```
