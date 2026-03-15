import json
import os
from config import DATA_FILE


def load_data():

    if not os.path.exists(DATA_FILE):

        data = {"plants": []}

        with open(DATA_FILE, "w") as f:
            json.dump(data, f)

    with open(DATA_FILE) as f:
        return json.load(f)


def save_data(data):

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_plant(data, plant):

    data["plants"].append(plant)


def delete_plant(data, index):

    data["plants"].pop(index)


def get_plants(data):

    return data["plants"]

