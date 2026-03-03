import json
import os

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data"
)

def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r") as f:
        return json.load(f)

# Load Node OBR assignment data
NODE_OBR_ASSIGNMENT = load_json("node_obr_assignment.json")

# Load TODO assignment data
