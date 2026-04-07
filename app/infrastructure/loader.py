import sys
import os
import json

def load_json(filename):
    # Use _MEIPASS if running in PyInstaller
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    path = os.path.join(base_path, "data", filename)
    with open(path, "r") as f:
        return json.load(f)

# Keep your constant exactly as it was
NODE_OBR_ASSIGNMENT = load_json("node_obr_assignment.json")