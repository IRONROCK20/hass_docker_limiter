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
        try:
            return int(float(mem_str[:-1]) * (2 ** units[mem_str[-1].lower()]))
        except ValueError:
            return 0
    try:
        return int(mem_str or 0)
    except ValueError:
        return 0

# Load/save limits: keys are container names (strings)
def load_limits():
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            else:
                return {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_limits(limits):
    # limits: dict mapping container_name -> {"memory": "...", "cpus": "..."}
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(limits, f, indent=2)

# Reapply limits periodically (and on reboot)
def watchdog():
    while True:
        limits = load_limits()
        for name, settings in limits.items():
            try:
                # Lookup container by name
                cont = client.containers.get(name)
            except docker.errors.NotFound:
                # Container not found (maybe stopped or renamed): skip
                # You may choose to log: print(f"[WARN] container '{name}' not found, skipping")
                continue
            except docker.errors.APIError as e:
                print(f"[ERROR] Docker API error when getting container '{name}': {e}")
                continue

            # Parse desired limits
            mem_str = settings.get("memory", "")
            cpu_str = settings.get("cpus", "")
            parsed_mem = parse_memory(mem_str)
            try:
                desired_cpus = float(cpu_str)
            except (ValueError, TypeError):
                print(f"[ERROR] invalid cpu value for container '{name}': {cpu_str}, skipping")
                continue

            # Prepare update params
            cpu_period = 100000
            cpu_quota = int(desired_cpus * cpu_period)
            try:
                client.api.update_container(
                    cont.id,
                    cpu_quota=cpu_quota,
                    cpu_period=cpu_period,
                    mem_limit=parsed_mem,
                    memswap_limit=parsed_mem
                )
                # Optionally log success:
                # print(f"[INFO] Reapplied limits to '{name}': memory={parsed_mem}, cpus={desired_cpus}")
            except docker.errors.APIError as e:
                print(f"[ERROR] failed to update container '{name}': {e}")
        # Sleep before next iteration
        time.sleep(5)

# Start watchdog thread immediately
threading.Thread(target=watchdog, daemon=True).start()

# Main route with multi-select and dropdowns
@app.route("/", methods=["GET", "POST"])
def index():
    # List all running containers
    containers = client.containers.list()
    # Load saved limits: keys are container names
    limits = load_limits()

    if request.method == "POST":
        # `containers` form field will contain a list of selected container names
        selected_names = request.form.getlist("containers")

        new_limits = {}
        for name in selected_names:
            # For each selected container name, retrieve form fields memory_<name> and cpus_<name>
            mem_val = request.form.get(f"memory_{name}")
            cpu_val = request.form.get(f"cpus_{name}")
            if mem_val and cpu_val:
                # Validate parseable?
                if parse_memory(mem_val) <= 0:
                    # Skip or warn; here we skip invalid memory entries
                    print(f"[WARN] Invalid memory '{mem_val}' for container '{name}', skipping")
                    continue
                try:
                    float(cpu_val)
                except (ValueError, TypeError):
                    print(f"[WARN] Invalid cpus '{cpu_val}' for container '{name}', skipping")
                    continue

                new_limits[name] = {"memory": mem_val, "cpus": cpu_val}

                # Apply immediately
                try:
                    cont = client.containers.get(name)
                except docker.errors.NotFound:
                    print(f"[WARN] container '{name}' not found when applying new limits")
                    continue
                except docker.errors.APIError as e:
                    print(f"[ERROR] Docker API error when getting container '{name}': {e}")
                    continue

                parsed_mem = parse_memory(mem_val)
                cpu_period = 100000
                cpu_quota = int(float(cpu_val) * cpu_period)
                try:
                    client.api.update_container(
                        cont.id,
                        cpu_quota=cpu_quota,
                        cpu_period=cpu_period,
                        mem_limit=parsed_mem,
                        memswap_limit=parsed_mem
                    )
                    # Optionally store success log:
                    # print(f"[INFO] Applied new limits to '{name}': memory={parsed_mem}, cpus={cpu_val}")
                except docker.errors.APIError as e:
                    print(f"[ERROR] failed to update container '{name}': {e}")

        # Save the updated limits (only selected containers are kept; others removed)
        save_limits(new_limits)
        # Redirect GET after POST
        return redirect("/")

    # GET: render the page, passing containers list and existing limits
    return render_template(
        "main.html",
        containers=containers,   # list of Container objects
        limits=limits,           # dict: name -> {"memory":..., "cpus":...}
        memory_options=["32m", "64m", "128m", "256m", "512m", "1g", "2g"],
        cpu_options=[f"{i/10:.1f}" for i in range(1, 21)]  # "0.1" to "2.0"
    )

if __name__ == "__main__":
    # You may want to read host/port from env or config
    app.run(host="0.0.0.0", port=12000)
