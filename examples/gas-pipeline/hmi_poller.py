#!/usr/bin/env python3

"""
Gas Pipeline HMI — ENIP Poller

This script runs INSIDE Mininet on the 'hmi' host.
It reads all ENIP tags from PLC1, PLC2, PLC3 and writes
the values to a JSON file that the HMI web server reads.

This represents what a REAL operator's HMI would see — the
network layer values. When an attacker spoofs ENIP tags,
THIS data changes, while the physical reality (SQLite) does not.
"""

import subprocess
import json
import time
import sys
import os

POLL_INTERVAL = 1.5  # seconds between polls

# PLC addresses and their tags
PLCS = {
    '192.168.1.10': ['PT101:1', 'AV1:1', 'FT101:1', 'LT201:1', 'PT301:1'],
    '192.168.1.20': ['LT201:2', 'AV2:2', 'PUMP1:2'],
    '192.168.1.30': ['PT301:3', 'AV3:3'],
}


def read_plc_tags(address, tags):
    """Read multiple ENIP tags from one PLC in a single cpppo call."""
    results = {}
    try:
        cmd = [sys.executable, '-m', 'cpppo.server.enip.client',
               '--print', '--address', address] + tags
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        for line in proc.stdout.strip().split('\n'):
            if '==' not in line:
                continue
            # Parse: "PT101:1              == [500.0]: 'OK'"
            parts = line.split('==')
            tag_part = parts[0].strip()
            value_part = parts[1].strip()

            # Extract tag name (before the colon)
            tag_name = tag_part.split(':')[0].strip()

            # Extract value from brackets
            start = value_part.find('[') + 1
            end = value_part.find(']')
            if start > 0 and end > start:
                try:
                    value = float(value_part[start:end])
                    results[tag_name] = value
                except ValueError:
                    results[tag_name] = None
    except Exception as e:
        print('Error reading from %s: %s' % (address, e), file=sys.stderr)

    return results


def main():
    print('HMI ENIP Poller started. Polling every %.1f seconds.' % POLL_INTERVAL)
    print('Writing to logs/hmi_data.json')

    while True:
        data = {'timestamp': time.time()}

        for address, tags in PLCS.items():
            tag_values = read_plc_tags(address, tags)
            data.update(tag_values)

        try:
            with open('logs/hmi_data.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print('Error writing JSON: %s' % e, file=sys.stderr)

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
