#!/usr/bin/env python3
"""
Generate a self-signed certificate for dbtrials internal/LAN deployment.

Usage:
  ./gencert.py [--out DIR] [--cn COMMON_NAME]

Defaults: --out ~/dbtrials-certs  --cn dbtrials.local
"""

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a self-signed cert for dbtrials")
    parser.add_argument("--out", default=str(Path.home() / "dbtrials-certs"))
    parser.add_argument("--cn", default="dbtrials.local")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    _run([
        "openssl", "req", "-x509",
        "-newkey", "rsa:4096", "-sha256", "-days", "3650", "-nodes",
        "-keyout", str(out_dir / "dbtrials-key.pem"),
        "-out", str(out_dir / "dbtrials.pem"),
        "-subj", f"/CN={args.cn}",
    ])

    print(f"Certificate written to {out_dir}/")
    print(f"  Key : {out_dir/'dbtrials-key.pem'}")
    print(f"  Cert: {out_dir/'dbtrials.pem'}")


if __name__ == "__main__":
    main()