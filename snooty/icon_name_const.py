from pathlib import Path

ICON_SET = None
ROOT_DIR = Path(__file__).parent
ICON_FILE = open("{}/.icon_names".format(ROOT_DIR))

if ICON_FILE:
    ICON_SET = set(line.strip() for line in ICON_FILE)
else:
    print("icon name file not found")
