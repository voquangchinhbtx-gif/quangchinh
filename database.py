import json
import os

def load_data():
    file_path = 'farm_data.json'
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        return {"crops": []} 
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"crops": []}

def get_plants():
    """Hàm này là cái mà file dashboard.py đang tìm!"""
    data = load_data()
    # Trả về danh sách cây trồng, nếu không có thì trả về danh sách rỗng
    return data.get("crops", [])

# Nếu các file khác có đòi hỏi thêm hàm get_crop_info hay get_crop_name, 
# bạn cũng nên khai báo sẵn ở đây để tránh lỗi tiếp theo.
