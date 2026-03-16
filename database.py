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
    if not os.path.exists(DATA_FILE):
        data = {"plants": [], "chat_history": []}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# =========================
# SAVE DATA
# =========================
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =========================
# ADD PLANT
# =========================
def add_plant(data, name, date):
    plants = data.get("plants", [])
    new_id = max((p["id"] for p in plants), default=0) + 1
    plant  = {
        "id":               new_id,
        "name":             name,
        "date":             date,
        "logs":             [],
        "optimized_recipe": None,
        # Lưu trữ lịch sử các vụ trước
        # Mỗi vụ: { "season": N, "date_start": ..., "date_end": ...,
        #            "logs": [...], "diagnoses": [...], "recipe": "..." }
        "seasons":          []
    }
    data["plants"].append(plant)
    save_data(data)
    return data

# =========================
# ARCHIVE & DELETE PLANT
# Khi "Kết thúc vụ": lưu toàn bộ nhật ký/quy trình vào seasons
# rồi xoá cây khỏi danh sách active
# =========================
def archive_and_delete_plant(data, plant_id):
    """
    Lưu vụ hiện tại vào một bảng seasons riêng (crop_history)
    trước khi xoá cây khỏi danh sách active.
    """
    target = next((p for p in data["plants"] if p["id"] == plant_id), None)
    if not target:
        return data

    # Chuẩn bị bản ghi vụ
    season_record = {
        "plant_name":   target["name"],
        "date_start":   target.get("date", ""),
        "date_end":     datetime.now().strftime("%Y-%m-%d"),
        "logs":         target.get("logs", []),
        "recipe":       target.get("optimized_recipe", ""),
        "seasons":      target.get("seasons", [])
    }

    # Lưu vào crop_history (theo tên loại cây để tra cứu sau)
    if "crop_history" not in data:
        data["crop_history"] = []
    data["crop_history"].append(season_record)

    # Xoá khỏi active
    data["plants"] = [p for p in data["plants"] if p["id"] != plant_id]
    save_data(data)
    return data

# =========================
# DELETE PLANT (giữ lại để tương thích)
# =========================
def delete_plant(data, plant_id):
    return archive_and_delete_plant(data, plant_id)

# =========================
# GET CROP HISTORY
# Lấy toàn bộ lịch sử các vụ của một loại cây
# =========================
def get_crop_history(data, crop_type):
    """
    Trả về list các vụ đã kết thúc của cùng loại cây (so khớp tên).
    """
    history = data.get("crop_history", [])
    matched = []
    for record in history:
        name = record.get("plant_name", "")
        # So khớp nếu crop_type xuất hiện trong tên
        if crop_type.lower() in name.lower():
            matched.append(record)
    return matched

# =========================
# ADD CHAT HISTORY
# =========================
def add_chat(data, user_msg, ai_msg):
    if "chat_history" not in data:
        data["chat_history"] = []
    data["chat_history"].append({
        "user": user_msg,
        "ai":   ai_msg,
        "time": datetime.now().strftime("%d/%m/%Y %H:%M")
    })
    save_data(data)
    return data

# =========================
# ADD LOG
# =========================
def add_log(data, plant_id, action_type, content):
    for p in data["plants"]:
        if p["id"] == plant_id:
            if "logs" not in p:
                p["logs"] = []
            p["logs"].insert(0, {
                "date":    datetime.now().strftime("%d/%m/%Y %H:%M"),
                "type":    action_type,
                "content": content
            })
            break
    save_data(data)
    return data

# =========================
# GET PLANTS
# =========================
def get_plants(data):
    return data.get("plants", [])
