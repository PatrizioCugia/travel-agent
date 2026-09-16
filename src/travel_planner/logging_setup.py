"""Keep credentials out of logs.

Rakuten authenticates by query string: applicationId and accessKey ride in the
URL of every request. httpx logs each request URL at INFO, and importing the
`mcp` package installs a logging handler that makes INFO visible — so simply
importing the MCP server was enough to print both secrets in full, to the
terminal and to data/watch.log under the scheduled run.

Called from both entry points. Anything that talks to Rakuten must call it.
"""

from __future__ import annotations

import logging

# httpx logs request URLs; httpcore is noisier still. Neither has anything to
# say at INFO that is worth leaking a key for.
NOISY_LOGGERS = ("httpx", "httpcore", "urllib3")


def quiet_http_logging(level: int = logging.WARNING) -> None:
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(level)
