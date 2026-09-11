"""Bounded SSE reader. Network workers never touch application state."""

import http.client
import json
import queue
import socket
import threading
import time
from urllib.parse import urlsplit

from pet_yaya.adapters.openai_dialogue import DialogueServiceError
from pet_yaya.domain.cancellation import CancellationToken


def stream_chat_events(url, headers, payload, timeout_seconds, cancellation):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DialogueServiceError("本地模型服务地址无效。")
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout_seconds)
    events = queue.Queue(maxsize=32)
    stopped = threading.Event()
    active_socket = []
    deadline = time.monotonic() + timeout_seconds

    def put(kind, value):
        while not stopped.is_set():
            try:
                events.put((kind, value), timeout=0.05)
                return
            except queue.Full:
                pass

    def read():
        try:
            connection.connect()
            active_socket.append(connection.sock)
            if stopped.is_set():
                return
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("POST", path, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers)
            with connection.getresponse() as response:
                if response.status != 200:
                    raise DialogueServiceError(f"模型流式服务返回 HTTP {response.status}。")
                if "text/event-stream" not in response.getheader("Content-Type", ""):
                    raise DialogueServiceError("模型未返回SSE流式数据。")
                data = []
                event_size = 0
                while not stopped.is_set():
                    line = response.readline(65537)
                    if not line:
                        raise DialogueServiceError("模型流式连接提前结束。")
                    if len(line) > 65536:
                        raise DialogueServiceError("模型流式事件过大。")
                    line = line.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if data:
                            raw = "\n".join(data)
                            if raw == "[DONE]":
                                put("done", None)
                                return
                            put("event", json.loads(raw))
                        data = []
                        event_size = 0
                    elif line.startswith("data:"):
                        value = line[5:].removeprefix(" ")
                        data.append(value)
                        event_size += len(value)
                        if event_size > 65536:
                            raise DialogueServiceError("模型流式事件过大。")
        except Exception as error:
            message = str(error) if isinstance(error, DialogueServiceError) else "模型流式连接失败或数据格式错误。"
            put("error", DialogueServiceError(message))
        finally:
            connection.close()

    cancellation.check()
    threading.Thread(target=read, daemon=True, name="yaya-stream-reader").start()
    try:
        while True:
            cancellation.check()
            if time.monotonic() >= deadline:
                raise DialogueServiceError("模型流式回复超时。")
            try:
                kind, value = events.get(timeout=0.05)
            except queue.Empty:
                continue
            cancellation.check()
            if kind == "error":
                raise value
            if kind == "done":
                return
            if not isinstance(value, dict):
                raise DialogueServiceError("模型流式事件格式错误。")
            yield value
    finally:
        stopped.set()
        # shutdown wakes blocked reads without waiting for the model to finish.
        for sock in active_socket:
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()


def speech_prefix(document):
    """Return only a top-level speech string, including incomplete JSON escapes."""
    decoder = json.JSONDecoder()
    pos = 0
    size = len(document)

    def skip(index):
        while index < size and document[index].isspace():
            index += 1
        return index

    pos = skip(pos)
    if pos >= size or document[pos] != "{":
        return ""
    pos += 1
    while pos < size:
        pos = skip(pos)
        try:
            key, pos = decoder.raw_decode(document, pos)
        except (ValueError, json.JSONDecodeError):
            return ""
        pos = skip(pos)
        if pos >= size or document[pos] != ":":
            return ""
        pos = skip(pos + 1)
        if key == "speech":
            if pos >= size or document[pos] != '"':
                return ""
            start = pos
            pos += 1
            # Decode the longest complete string prefix, never exposing raw escapes.
            while pos < size:
                if document[pos] == '"':
                    try:
                        return json.loads(document[start:pos + 1])
                    except ValueError:
                        return ""
                if document[pos] == "\\":
                    if pos + 1 >= size:
                        break
                    count = 6 if document[pos + 1] == "u" else 2
                    if pos + count > size:
                        break
                    # Wait for both halves of a surrogate pair.
                    if count == 6:
                        try:
                            code = int(document[pos + 2:pos + 6], 16)
                        except ValueError:
                            return ""
                        if 0xD800 <= code <= 0xDBFF:
                            if pos + 12 > size:
                                break
                            count = 12
                    pos += count
                else:
                    pos += 1
            try:
                return json.loads(document[start:pos] + '"')
            except ValueError:
                return ""
        try:
            _, pos = decoder.raw_decode(document, pos)
        except ValueError:
            return ""
        pos = skip(pos)
        if pos >= size or document[pos] != ",":
            return ""
        pos += 1
    return ""

