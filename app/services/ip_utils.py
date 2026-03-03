# app/services/ip_utils.py

def add_to_last_octet(ip_str, increment):
    try:
        parts = ip_str.split(".")
        last = int(parts[-1]) + increment
        if last < 0 or last > 255:
            return "ERR"
        parts[-1] = str(last)
        return ".".join(parts)
    except:
        return "ERR"