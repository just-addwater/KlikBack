# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""KlikBack's GUI layer: a pywebview shell over `web/`, driving the CLI
as a worker process. Nothing in here decompiles in-process -- the engine
work happens in `klikback-cli --worker`, whose NDJSON events this layer
renders. `devserve.py` previews the same `web/` UI in an ordinary browser
for development on machines without pywebview installed."""
