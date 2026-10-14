"""Bound child output and lifetime without exposing diagnostics."""

import os
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field

from .errors import AppError


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: bytes = field(repr=False)


_ACTIVE_CHILDREN: set[tuple[subprocess.Popen, bool]] = set()
_ACTIVE_LOCK = threading.Lock()


def terminate_all_children() -> None:
    """Terminate and kill all active child processes immediately to unblock waiting threads."""
    with _ACTIVE_LOCK:
        children = list(_ACTIVE_CHILDREN)
        _ACTIVE_CHILDREN.clear()
    for child, grouped in children:
        try:
            if grouped:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError, OSError:
                    pass
            else:
                try:
                    child.kill()
                except ProcessLookupError, OSError:
                    pass
        except Exception:
            pass


def _stop(child: subprocess.Popen, *, grouped=True) -> None:
    # Grouped children lead a separate owned group, even when sharing our session.
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        try:
            if grouped:
                os.killpg(child.pid, signal.SIGTERM)
            else:
                child.terminate()
        except ProcessLookupError:
            child.wait()
            return
        time.sleep(0.1)
        try:
            if grouped:
                os.killpg(child.pid, signal.SIGKILL)
            else:
                child.kill()
        except ProcessLookupError:
            pass
        child.wait()
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


def run(
    argv: list[str],
    *,
    env: dict[str, str],
    timeout: float = 15,
    stdout_cap: int = 64,
    stderr_cap: int = 65536,
    input_data: bytes | None = None,
    stdin: bytes | None = None,
    interactive: bool = False,
    preserve_session: bool = False,
) -> Completed:
    """Drain both pipes concurrently; stderr is counted and discarded immediately."""
    if input_data is None and stdin is not None:
        input_data = stdin
    child = None
    try:
        child = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=not interactive and not preserve_session,
            process_group=0 if preserve_session and not interactive else None,
        )
        with _ACTIVE_LOCK:
            _ACTIVE_CHILDREN.add((child, not interactive))
        deadline = time.monotonic() + timeout
        output = bytearray()
        counts = [0, 0]
        caps = [stdout_cap, stderr_cap]
        with selectors.DefaultSelector() as selector:
            position = 0
            if input_data is not None:
                os.set_blocking(child.stdin.fileno(), False)
                selector.register(child.stdin, selectors.EVENT_WRITE, 2)
            for index, stream in enumerate((child.stdout, child.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppError(7)
                for key, _ in selector.select(remaining):
                    index = key.data
                    if index == 2:
                        try:
                            position += os.write(key.fd, input_data[position : position + 8192])
                        except BrokenPipeError:
                            position = len(input_data)
                        if position == len(input_data):
                            selector.unregister(key.fileobj)
                            child.stdin.close()
                        continue
                    data = os.read(key.fd, min(8192, caps[index] - counts[index] + 1))
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    counts[index] += len(data)
                    if counts[index] > caps[index]:
                        raise AppError(5)
                    if index == 0:
                        output.extend(data)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AppError(7)
            child.wait(timeout=remaining)
        return Completed(child.returncode, bytes(output))
    except subprocess.TimeoutExpired:
        raise AppError(7) from None
    except KeyboardInterrupt:
        raise AppError(130) from None
    except OSError, ValueError:
        raise AppError(3) from None
    finally:
        if child is not None:
            with _ACTIVE_LOCK:
                _ACTIVE_CHILDREN.discard((child, not interactive))
            try:
                _stop(child, grouped=not interactive)
            finally:
                child.stdout.close()
                child.stderr.close()
                if child.stdin is not None:
                    child.stdin.close()


def handoff(argv: list[str], *, env: dict[str, str], input_data: bytes, timeout=5) -> None:
    """Wait for wl-copy's parent, preserving its successful clipboard server.

    Discard output instead of inheriting a background server's open diagnostic
    pipes. Only successful handoff exempts the process group from cleanup.
    """
    child = None
    successful = False
    try:
        child = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
        )
        with _ACTIVE_LOCK:
            _ACTIVE_CHILDREN.add((child, True))
        child.communicate(input=input_data, timeout=timeout)
        if child.returncode != 0:
            raise AppError(6)
        successful = True
    except subprocess.TimeoutExpired:
        raise AppError(7) from None
    except KeyboardInterrupt:
        raise AppError(130) from None
    except OSError, ValueError:
        raise AppError(6) from None
    finally:
        if child is not None:
            with _ACTIVE_LOCK:
                _ACTIVE_CHILDREN.discard((child, True))
            if not successful:
                _stop(child)
            child.stdin.close()
