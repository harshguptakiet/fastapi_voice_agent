    
import os, json

DHOME = "src"
LOGS = os.path.join(os.getcwd(), "runtime", "logs")

def write_to_json_file(output_json_file, json_data):
    dest_folder = os.path.dirname(output_json_file)
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)
    with open(output_json_file, "w") as output_file:
        json.dump(json_data, output_file, indent=4)