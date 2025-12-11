"""Network scanner for ADB devices."""

import re
import socket
import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor
from typing import List


def get_local_ip() -> str:
    """Get the local IP address of the machine."""
    try:
        # Create a dummy socket to connect to an external IP (doesn't actually connect)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_arp_ips() -> List[str]:
    """Get list of IPs from ARP cache."""
    ips = set()
    try:
        cmd = ["arp", "-a"]
        output = subprocess.check_output(cmd, text=True)
        
        # Extract IPs using regex
        found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', output)
        
        local_ip = get_local_ip()
        subnet_prefix = ".".join(local_ip.split(".")[:-1])
        
        for ip in found:
            # Filter IPs to match local subnet (simple check)
            if ip.startswith(subnet_prefix) and ip != local_ip:
                ips.add(ip)
                
    except Exception as e:
        print(f"ARP scan failed: {e}")
        
    return list(ips)


def check_port(ip: str, port: int, timeout: float) -> str | None:
    """Check if a port is open on an IP address."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((ip, port))
        if result == 0:
            return ip
    except Exception:
        pass
    finally:
        sock.close()
    return None


def scan_network(port: int = 5555, timeout: float = 0.2, max_workers: int = 200) -> List[str]:
    """
    Scan the local network for devices with open ADB port.
    Prioritizes ARP cache for speed.
    
    Args:
        port: The port to check (default 5555 for ADB).
        timeout: Connection timeout in seconds.
        max_workers: Number of concurrent threads.
        
    Returns:
        List of IP addresses with the port open.
    """
    local_ip = get_local_ip()
    if local_ip == "127.0.0.1":
        return []

    found_ips = []
    
    # 1. Fast path: Scan ARP cache first
    arp_ips = get_arp_ips()
    if arp_ips:
        print(f"Scanning {len(arp_ips)} IPs from ARP cache...")
        with ThreadPoolExecutor(max_workers=len(arp_ips) + 1) as executor:
            futures = {executor.submit(check_port, ip, port, timeout): ip for ip in arp_ips}
            for future in futures:
                result = future.result()
                if result:
                    found_ips.append(result)
    
    # If found in ARP, return immediately (fastest)
    if found_ips:
        return found_ips

    # 2. Slow path: Full subnet scan
    print("ARP scan yielded no results, performing full subnet scan...")
    subnet = ".".join(local_ip.split(".")[:-1])
    ips_to_scan = [f"{subnet}.{i}" for i in range(1, 255)]
    
    # Remove already scanned IPs to avoid duplicate work
    ips_to_scan = [ip for ip in ips_to_scan if ip not in arp_ips and ip != local_ip]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_port, ip, port, timeout): ip for ip in ips_to_scan}
        for future in futures:
            result = future.result()
            if result:
                found_ips.append(result)
                
    return found_ips
