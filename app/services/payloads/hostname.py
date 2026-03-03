# app/services/payloads/hostname.py

def hostname_payload(hostname: str):
    # IOS-XR YANG: Cisco-IOS-XR-shellutil-cfg:host-names
    return {
        "Cisco-IOS-XR-shellutil-cfg:host-names": {
            "host-name": hostname
        }
    }