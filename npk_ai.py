import numpy as np
from PIL import Image


def analyze_leaf_npk(image):

    img = np.array(image)

    r = img[:, :, 0].mean()
    g = img[:, :, 1].mean()
    b = img[:, :, 2].mean()

    if g < 80:
        return "Thiếu Đạm (N)"

    if r > 150 and g < 120:
        return "Thiếu Lân (P)"

    if b > 140:
        return "Thiếu Kali (K)"

    return "Lá khỏe - dinh dưỡng bình thường"

