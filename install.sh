#!/bin/bash
set -eu
umask 077
exec python3 "$(dirname "$0")/install.py" "$@"
