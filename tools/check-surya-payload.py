#!/usr/bin/env python3
"""Check the SURYA RAM-disk payload before Android boot image packaging."""
import json
import sys
from pathlib import Path
from surya import validate_payload

if __name__ == '__main__':
    try:
        print(json.dumps(validate_payload(Path(sys.argv[1]).read_bytes()), indent=2))
    except (ValueError, IndexError, StopIteration) as e:
        raise SystemExit(f'payload rejected: {e}')
