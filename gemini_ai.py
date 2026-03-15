import google.generativeai as genai
from config import GEMINI_MODEL


def load_model(api):

    genai.configure(api_key=api)

    return genai.GenerativeModel(GEMINI_MODEL)


def diagnose(model, image):

    prompt = """
Phân tích bệnh cây trong ảnh.
Cho biết:

- tên bệnh
- nguyên nhân
- cách xử lý
"""

    response = model.generate_content([prompt, image])

    return response.text

