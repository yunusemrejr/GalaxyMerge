
import pytest

pytestmark = [pytest.mark.unit]


from galaxy_merge.app import ports


class FakeSocket:
    def __init__(self, rejected_ports: set[int]) -> None:
        self.rejected_ports = rejected_ports
        self.bound_port = -1

    def setsockopt(self, level: int, option: int, value: int) -> None:
        return None

    def bind(self, address: tuple[str, int]) -> None:
        port = address[1]
        if port in self.rejected_ports:
            raise OSError("port unavailable")
        self.bound_port = port

    def listen(self, backlog: int) -> None:
        return None

    def set_inheritable(self, inheritable: bool) -> None:
        return None

    def getsockname(self) -> tuple[str, int]:
        if self.bound_port == 0:
            return ("127.0.0.1", 45678)
        return ("127.0.0.1", self.bound_port)

    def close(self) -> None:
        return None


def test_reserve_socket_with_port_zero_asks_os_for_ephemeral_port_first(monkeypatch) -> None:
    # Given: socket creation is observable.
    attempts: list[int] = []

    def socket_factory(family: int, kind: int) -> FakeSocket:
        fake = FakeSocket(rejected_ports=set())
        original_bind = fake.bind

        def bind(address: tuple[str, int]) -> None:
            attempts.append(address[1])
            original_bind(address)

        fake.bind = bind
        return fake

    monkeypatch.setattr(ports.socket, "socket", socket_factory)

    # When: auto-port mode is requested.
    sock = ports.reserve_socket(0)

    # Then: the OS ephemeral port is tried before the fixed fallback range.
    assert attempts == [0]
    assert sock.getsockname()[1] == 45678


def test_reserve_socket_falls_back_to_legacy_range_when_ephemeral_bind_fails(monkeypatch) -> None:
    # Given: the OS ephemeral bind is unavailable.
    attempts: list[int] = []

    def socket_factory(family: int, kind: int) -> FakeSocket:
        fake = FakeSocket(rejected_ports={0})
        original_bind = fake.bind

        def bind(address: tuple[str, int]) -> None:
            attempts.append(address[1])
            original_bind(address)

        fake.bind = bind
        return fake

    monkeypatch.setattr(ports.socket, "socket", socket_factory)

    # When: auto-port mode is requested.
    sock = ports.reserve_socket(0, start=7419)

    # Then: Galaxy Merge falls back to its legacy preferred range.
    assert attempts == [0, 7419]
    assert sock.getsockname()[1] == 7419
