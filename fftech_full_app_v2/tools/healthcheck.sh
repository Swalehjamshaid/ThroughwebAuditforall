
#!/usr/bin/env sh
set -e
wget -qO- http://127.0.0.1:${PORT:-8000}/auth/health || exit 1
