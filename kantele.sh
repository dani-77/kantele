#!/bin/sh
# Installed as /usr/bin/kantele; the package lives in /usr/lib/kantele.
exec python3 -c 'import sys; sys.path.insert(0, "/usr/lib/kantele"); from kantele.cli import main; main()' "$@"
