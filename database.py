import json
import os
import copy
from datetime import datetime

DATA_FILE = "aji_farm_db.json"

INIT_DATA = {
    "plants": [],
    "disease_logs": [],
    "irrigation_logs": [],
    "fertilizer_logs": [],
    "inventory": {
        "fertilizer": 100,
        "pesticide": 100
    },
    "chat_history": []
}

# =========================
# LOAD DATA
# =========================
def load_data():
    if os.path.exists(DATA_FILE) and os.stat(DATA_FILE).st_size > 0:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(INIT_DATA)

    return copy.deepcopy(INIT_DATA)


# =========================
# SAVE DATA
# =========================
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# PLANT MANAGEMENT
# =========================
def add_plant(data, crop_name, plant_date):
    """Thêm cây mới"""

    current_ids = [int(p.get("id", 0)) for p in data["plants"]]
    new_id = max(current_ids, default=0) + 1

    plant = {
        "id": new_id,
        "name": str(crop_name).strip(),
        "date": str(plant_date),
        "created_at": datetime.now().isoformat()
    }

    data["plants"].append(plant)
    save_data(data)

    return data


def delete_plant(data, plant_id):
    """Xóa cây"""

    plant_id = int(plant_id)

    data["plants"] = [
        p for p in data["plants"]
        if int(p.get("id", 0)) != plant_id
    ]

    save_data(data)
    return data


def update_plant(data, plant_id, new_name=None, new_date=None):
    """Cập nhật cây"""

    plant_id = int(plant_id)

    for plant in data["plants"]:

        if int(plant.get("id", 0)) == plant_id:

            if new_name:
                plant["name"] = str(new_name).strip()

            if new_date:
                plant["date"] = str(new_date)

            plant["updated_at"] = datetime.now().isoformat()

            break

    save_data(data)
    return data


def get_plants(data):
    return data.get("plants", [])


# =========================
# DISEASE LOG
# =========================
def add_disease_log(data, plant_id, disease_name, note=""):
    log = {
        "plant_id": int(plant_id),
        "disease": disease_name,
        "note": note,
        "date": datetime.now().isoformat()
    }

    data["disease_logs"].append(log)
    save_data(data)

    return data


# =========================
# IRRIGATION LOG
# =========================
def add_irrigation_log(data, plant_id, amount):
    log = {
        "plant_id": int(plant_id),
        "water_amount": amount,
        "date": datetime.now().isoformat()
    }

    data["irrigation_logs"].append(log)
    save_data(data)

    return data


# =========================
# FERTILIZER LOG
# =========================
def add_fertilizer_log(data, plant_id, fertilizer_name, amount):

    log = {
        "plant_id": int(plant_id),
        "fertilizer": fertilizer_name,
        "amount": amount,
        "date": datetime.now().isoformat()
    }

    data["fertilizer_logs"].append(log)

    # trừ kho
    if "fertilizer" in data["inventory"]:
        data["inventory"]["fertilizer"] -= amount

    save_data(data)

    return data


# =========================
# CHAT HISTORY (AI)
# =========================
def add_chat(data, user_msg, ai_msg):

    chat = {
        "user": user_msg,
        "ai": ai_msg,
        "time": datetime.now().isoformat()
    }

    data["chat_history"].append(chat)

    # giới hạn 100 chat
    if len(data["chat_history"]) > 100:
        data["chat_history"] = data["chat_history"][-100:]

    save_data(data)

    return data
