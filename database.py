import json
import os

FILE_PATH = "farm_data.json"


# ==============================
# LOAD DATA
# ==============================
def load_data():
    """Đọc dữ liệu từ JSON. Nếu file lỗi hoặc trống, tạo cấu trúc chuẩn."""
    if not os.path.exists(FILE_PATH) or os.stat(FILE_PATH).st_size == 0:
        return {"crops": []}

    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {"crops": []}


# ==============================
# SAVE DATA
# ==============================
def save_data(data):
    """Lưu dữ liệu an toàn vào file JSON."""
    try:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Lỗi khi lưu dữ liệu: {e}")


# ==============================
# GET PLANTS
# ==============================
def get_plants(data=None):
    """Lấy danh sách cây trồng."""
    if isinstance(data, dict):
        return data.get("crops", [])

    current_data = load_data()
    return current_data.get("crops", [])


# ==============================
# ADD PLANT
# ==============================
def add_plant(plant_name, planting_date):
    """Thêm cây trồng mới."""
    data = load_data()

    if "crops" not in data:
        data["crops"] = []

    # Tạo ID không trùng
    new_id = max([p.get("id", 0) for p in data["crops"]], default=0) + 1

    new_plant = {
        "id": new_id,
        "name": str(plant_name).strip(),
        "date": str(planting_date)
    }

    data["crops"].append(new_plant)
    save_data(data)

    return new_plant


# ==============================
# DELETE PLANT
# ==============================
def delete_plant(plant_id):
    """Xóa cây dựa trên ID."""
    data = load_data()

    if "crops" not in data:
        return False

    plant_id = int(plant_id)

    original_count = len(data["crops"])

    data["crops"] = [
        p for p in data["crops"]
        if int(p.get("id", 0)) != plant_id
    ]

    if len(data["crops"]) < original_count:
        save_data(data)
        return True

    return False


# ==============================
# UPDATE PLANT
# ==============================
def update_plant(plant_id, new_name=None, new_date=None):
    """Cập nhật thông tin cây."""
    data = load_data()

    if "crops" not in data:
        return False

    plant_id = int(plant_id)

    for plant in data["crops"]:

        if int(plant.get("id", 0)) == plant_id:

            if new_name is not None and str(new_name).strip():
                plant["name"] = str(new_name).strip()

            if new_date is not None:
                plant["date"] = str(new_date)

            save_data(data)
            return True

    return False


# ==============================
# GET CROP NAME
# ==============================
def get_crop_name(crop_id):
    """Tìm tên cây dựa trên ID."""
    plants = get_plants()

    for p in plants:
        if str(p.get("id")) == str(crop_id):
            return p.get("name")

    return "Không xác định"


# ==============================
# GET CROP INFO (CHO AI)
# ==============================
def get_crop_info(crop_name):
    """Trả thông tin cây trồng cơ bản cho AI."""
    crops_info = {
        "Lúa": "Cây lương thực chính, cần nhiều nước và đất ngập.",
        "Ngô": "Cây lương thực chịu hạn tốt hơn lúa.",
        "Cà phê": "Cây công nghiệp lâu năm, cần khí hậu mát.",
        "Ớt": "Cây rau màu phổ biến, cần nhiều ánh sáng và thoát nước tốt.",
        "Cà chua": "Cây rau ăn quả, dễ mắc bệnh nấm và sâu."
    }

    return crops_info.get(
        crop_name,
        f"Thông tin cơ bản về cây {crop_name}"
    )
