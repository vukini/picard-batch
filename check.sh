#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHONPATH=src${PYTHONPATH:+:$PYTHONPATH} python3 -m unittest discover -s tests -v
