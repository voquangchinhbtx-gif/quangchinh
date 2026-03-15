import json
import os

FILE_PATH = 'farm_data.json'

def load_data():
    """Đọc dữ liệu từ file JSON"""
    if not os.path.exists(FILE_PATH) or os.stat(FILE_PATH).st_size == 0:
        return {"crops": []}
    try:
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"crops": []}

def save_data(data):
    """Lưu dữ liệu vào file JSON - File garden.py cần hàm này!"""
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_plants():
    """Lấy danh sách cây trồng cho dashboard.py"""
    data = load_data()
    return data.get("crops", [])

def add_plant(plant_name, planting_date):
    """Thêm cây trồng mới - File garden.py cần hàm này!"""
    data = load_data()
    new_plant = {
        "id": len(data["crops"]) + 1,
        "name": plant_name,
        "date": planting_date
    }
    data["crops"].append(new_plant)
    save_data(data)
