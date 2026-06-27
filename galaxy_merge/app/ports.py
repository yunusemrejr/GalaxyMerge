import socket


def reserve_socket(port: int = 0, start: int = 7419) -> socket.socket:
    candidates = [port] if port > 0 else [0, *range(start, start + 100)]
    for candidate in candidates:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", candidate))
            sock.listen(128)
            sock.set_inheritable(True)
            return sock
        except OSError:
            continue
    raise OSError("could not reserve a Galaxy Merge server port")


def find_free_port(start: int = 7419) -> int:
    sock = reserve_socket(0, start)
    try:
        return sock.getsockname()[1]
    finally:
        sock.close()
