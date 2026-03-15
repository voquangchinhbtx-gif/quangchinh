CROPS = {

    "chili": {
        "name": "Ớt",
        "npk": "16-16-8"
    },

    "tomato": {
        "name": "Cà chua",
        "npk": "15-15-15"
    },

    "cucumber": {
        "name": "Dưa leo",
        "npk": "20-20-20"
    }
}


def get_crop_info(crop):

    return CROPS.get(crop, {
        "name": crop,
        "npk": "?"
    })

