import os
import json
import threading
import time
from flask import Flask, render_template, request, redirect
import docker

app = Flask(__name__, template_folder="templates")
client = docker.from_env()
CONFIG_FILE = "/config/container_limits.json"

# Utility: parse memory strings (e.g., "256m", "1g")
def parse_memory(mem_str):
    units = {"k": 10, "m": 20, "g": 30}
    if mem_str and mem_str[-1].lower() in units:
        return int(float(mem_str[:-1]) * (2 ** units[mem_str[-1].lower()]))
    return int(mem_str or 0)

# Load/save limits
def load_limits():
    try:
        return json.load(open(CONFIG_FILE, "r"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_limits(limits):
    with open(CONFIG_FILE, "w") as f:
        json.dump(limits, f, indent=2)

# Reapply limits periodically (and on reboot)
def watchdog():
    while True:
        limits = load_limits()
        for cid, settings in limits.items():
            try:
                parsed_mem = parse_memory(settings["memory"])
                cpu_period = 100000
                cpu_quota = int(float(settings["cpus"]) * cpu_period)
                client.api.update_container(
                    cid,
                    cpu_quota=cpu_quota,
                    cpu_period=cpu_period,
                    mem_limit=parsed_mem,
                    memswap_limit=parsed_mem
                )
            except docker.errors.NotFound:
                continue
        time.sleep(5)

# Start watchdog thread immediately
threading.Thread(target=watchdog, daemon=True).start()

# Main route with multi-select and dropdowns
@app.route("/", methods=["GET", "POST"])
def index():
    containers = client.containers.list()
    limits = load_limits()

    if request.method == "POST":
        selected = request.form.getlist("containers")
        new_limits = {}
        for cid in selected:
            mem_val = request.form.get(f"memory_{cid}")
            cpu_val = request.form.get(f"cpus_{cid}")
            if mem_val and cpu_val:
                new_limits[cid] = {"memory": mem_val, "cpus": cpu_val}
                parsed_mem = parse_memory(mem_val)
                cpu_period = 100000
                cpu_quota = int(float(cpu_val) * cpu_period)
                client.api.update_container(
                    cid,
                    cpu_quota=cpu_quota,
                    cpu_period=cpu_period,
                    mem_limit=parsed_mem,
                    memswap_limit=parsed_mem
                )
        save_limits(new_limits)
        return redirect("/")

    return render_template(
        "main.html",
        containers=containers,
        limits=limits,
        memory_options=["32m", "64m", "128m", "256m", "512m", "1g", "2g"],
        cpu_options = [
            "0.1", "0.2", "0.3", "0.4", "0.5",
            "0.6", "0.7", "0.8", "0.9", "1.0",
            "1.1", "1.2", "1.3", "1.4", "1.5",
            "1.6", "1.7", "1.8", "1.9", "2.0"
            ]
        )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=12000)
