#!/usr/bin/env python3
import json
import os
import docker
import sys

CONFIG_FILE = os.environ.get("CONFIG_PATH", "/config/container_limits.json")

def parse_memory(mem_str):
    units = {"k": 10, "m": 20, "g": 30}
    if mem_str and mem_str[-1].lower() in units:
        return int(float(mem_str[:-1]) * (2 ** units[mem_str[-1].lower()]))
    try:
        return int(mem_str)
    except Exception:
        return 0

def load_limits(path):
    with open(path, "r") as f:
        return json.load(f)

def main():
    try:
        limits = load_limits(CONFIG_FILE)
    except FileNotFoundError:
        print(f"[ERROR] config file not found: {CONFIG_FILE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] invalid JSON in {CONFIG_FILE}: {e}")
        sys.exit(1)

    client = docker.from_env()
    api = client.api

    for identifier, settings in limits.items():
        # identifier is now a container name (stable) or label value
        # Attempt to get by name:
        try:
            cont = client.containers.get(identifier)
        except docker.errors.NotFound:
            # Optionally: try matching by label, if you prefer label-based mapping.
            # Example: if you used labels like {"resource_limiter": "<identifier>"}, you could do:
            # matches = client.containers.list(filters={"label": f"resource_limiter={identifier}"})
            # if matches:
            #     cont = matches[0]
            # else:
            print(f"[WARN] container '{identifier}' not found by name, skipping")
            continue
        except docker.errors.APIError as e:
            print(f"[ERROR] error retrieving container '{identifier}': {e}")
            continue

        cid = cont.id  # current ID
        name = cont.name
        print(f"[INFO] Found container name='{name}', ID={cid}")

        # desired
        desired_mem = parse_memory(settings.get("memory", "0"))
        try:
            desired_cpus = float(settings.get("cpus", 0))
        except ValueError:
            print(f"[ERROR] invalid cpus value for '{identifier}': {settings.get('cpus')}, skipping")
            continue

        # current
        hc = cont.attrs.get("HostConfig", {})
        curr_mem = hc.get("Memory", 0)
        period = hc.get("CpuPeriod", 0) or 100000
        quota = hc.get("CpuQuota", 0)
        curr_cpus = (quota / period) if period > 0 else 0

        # compare
        mem_ok = (curr_mem == desired_mem)
        cpu_ok = abs(curr_cpus - desired_cpus) < 1e-2

        if mem_ok and cpu_ok:
            print(f"[OK]   {name}: memory={curr_mem} bytes, cpus={curr_cpus:.2f}")
        else:
            print(f"[FIX]  {name}: current(mem={curr_mem}, cpu={curr_cpus:.2f}) → desired(mem={desired_mem}, cpu={desired_cpus:.2f})")
            try:
                api.update_container(
                    cid,
                    mem_limit=desired_mem,
                    memswap_limit=desired_mem,
                    cpu_period=period,
                    cpu_quota=int(desired_cpus * period)
                )
                print(f"[DONE] limits applied to {name}")
            except docker.errors.APIError as e:
                print(f"[ERROR] failed to update {name}: {e}")

if __name__ == "__main__":
    main()
