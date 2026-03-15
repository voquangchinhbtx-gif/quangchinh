import json
import os

def load_data():
    file_path = 'farm_data.json'
    # Kiểm tra nếu file không tồn tại hoặc bị trống
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        return {"crops": [], "settings": {}} # Trả về dữ liệu mặc định
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"crops": [], "settings": {}} # Nếu lỗi định dạng thì trả về mặc định

