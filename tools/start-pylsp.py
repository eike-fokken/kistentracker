"""Start python-lsp-server with the configuration from pyproject.toml.

pylsp reads its plugin settings from JSON handed to it as LSP
``initializationOptions`` -- there is no way to point it at a TOML file. This
wrapper runs pylsp as a child process, forwards the client's messages on
stdin to it unchanged, and passes ``[tool.pylsp]`` from ``pyproject.toml`` as
``initializationOptions``.

The one message that cannot be forwarded as-is is the ``initialize`` request:
its response has to travel straight back to the client instead of being
relayed on pylsp's stdout. ``initialize`` is therefore sent to pylsp first and
its response re-emitted by this process with the original request id.

Usage in an LSP client config (see opencode.json)::

    poetry run python tools/start-pylsp.py
"""

import itertools
import json
import subprocess
import sys
import threading
import tomllib
from io import TextIOWrapper
from pathlib import Path
from typing import IO, cast

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def read_pylsp_settings() -> dict:
    """Return ``[tool.pylsp]`` from pyproject.toml, or an empty dict."""
    with PYPROJECT.open("rb") as pyproject:
        tools = tomllib.load(pyproject).get("tool", {})
    return tools.get("pylsp", {})


class StdioServer:
    """JSON-RPC over the stdio of a pylsp child process."""

    def __init__(self, args: list[str]) -> None:
        self._next_id = itertools.count(-1, -1)
        self._process = subprocess.Popen(  # pylint: disable=consider-using-with
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            encoding="utf-8",
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("pylsp did not get a usable stdin/stdout")
        self._stdin: TextIOWrapper = cast(TextIOWrapper, self._process.stdin)
        self._stdout: IO[str] = self._process.stdout

    def request(self, method: str, params: dict) -> dict:
        """Send a request and return its result.

        Server-to-client traffic that arrives meanwhile (progress
        notifications, ``window/workDoneProgress/create``, ...) is discarded.
        This is only used for ``initialize``, before the client is connected.
        """
        request_id = next(self._next_id)
        self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        while True:
            message = self._receive()
            if message is None:
                raise RuntimeError(f"pylsp closed the connection during {method}")
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise RuntimeError(f"pylsp rejected {method}: {message['error']}")
                return message["result"]

    def relay_session(self) -> None:
        """Forward client stdin to pylsp and pylsp stdout to the client.

        The client (opencode) frames messages as one JSON object per line,
        while pylsp uses ``Content-Length`` framing. The two directions also
        have to run at the same time: a live session needs replies while the
        client keeps writing, so ``stdin`` is forwarded on this thread and
        pylsp's output is relayed from a background thread.
        """
        reader = threading.Thread(target=self._relay_output, daemon=True)
        reader.start()
        for line in sys.stdin:
            self._send(json.loads(line))
        self._stdin.close()
        reader.join()
        self._process.wait()

    def _relay_output(self) -> None:
        """Copy pylsp's output to the client as one JSON object per line."""
        while (message := self._receive()) is not None:
            print(json.dumps(message), flush=True)

    def _send(self, message: dict) -> None:
        body = json.dumps(message).encode("utf-8")
        stdin = self._stdin.buffer
        stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
        stdin.write(body)
        stdin.flush()

    def _receive(self) -> dict | None:
        headers: dict[str, str] = {}
        while (line := self._stdout.readline()) not in ("\r\n", "\n", ""):
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        if "content-length" not in headers:
            return None
        return json.loads(self._stdout.read(int(headers["content-length"])))


def main() -> int:
    """Run pylsp with ``[tool.pylsp]`` as its initializationOptions."""
    server = StdioServer([sys.executable, "-m", "pylsp"])

    # Everything the client sends is JSON per line (opencode's LSP client
    # framing). The first message is `initialize`; answer it ourselves.
    line = sys.stdin.readline()
    if not line:
        return 1
    initialize = json.loads(line)
    params = initialize.get("params", {})
    result = server.request(
        "initialize",
        {
            **params,
            # pylsp reads its settings from `initializationOptions.pylsp`;
            # they are merged in at pylsp/config/config.py as
            # `init_opts.get("pylsp", {})`. Settings placed anywhere else in
            # the params are ignored.
            "initializationOptions": {
                **params.get("initializationOptions", {}),
                "pylsp": read_pylsp_settings(),
            },
        },
    )
    print(
        json.dumps({"jsonrpc": "2.0", "id": initialize.get("id"), "result": result}),
        flush=True,
    )

    server.relay_session()
    return 0


if __name__ == "__main__":
    sys.exit(main())
