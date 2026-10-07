"""Offline protocol checks with a loopback receiver; never access the panel."""
import socket
import struct
import threading
import unittest

import push_panel_image as client


class Receiver:
    def __init__(self, status=0, magic=b"VACK", truncate=False):
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(1)
        self.port = self.socket.getsockname()[1]
        self.error = None
        self.header = None
        self.payload = None
        self.status, self.magic, self.truncate = status, magic, truncate
        self.thread = threading.Thread(target=self.run)

    def run(self):
        try:
            with self.socket, self.socket.accept()[0] as connection:
                connection.settimeout(5)
                self.header = client.HEADER.unpack(client.receive_exact(connection, client.HEADER.size))
                self.payload = client.receive_exact(connection, self.header[3])
                ack = client.ACK.pack(self.magic, self.status)
                connection.sendall(ack[:2])
                if not self.truncate:
                    connection.sendall(ack[2:5])
                    connection.sendall(ack[5:])
        except BaseException as error:
            self.error = error

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.thread.join(10)
        if self.thread.is_alive():
            raise AssertionError("Offline receiver did not complete")
        if self.error:
            raise self.error


class ProtocolTests(unittest.TestCase):
    def test_fnv_reference(self):
        self.assertEqual(client.checksum(b""), 0x811c9dc5)
        self.assertEqual(client.checksum(b"hello"), 0x4f9f2cab)

    def test_pixel_byte_order(self):
        self.assertEqual(client.packed_pixels([0xf800, 0x07e0, 0x001f]),
                         bytes.fromhex("00f8e0071f00"))

    def test_patterns(self):
        first, second = client.test_pattern(), client.test_pattern(True)
        self.assertEqual(len(first), 307200)
        self.assertEqual(len(second), 307200)
        self.assertNotEqual(client.checksum(first), client.checksum(second))

    def test_stream_and_split_ack(self):
        payload = client.test_pattern()
        with Receiver() as receiver:
            result = client.push("127.0.0.1", payload, receiver.port)
        self.assertTrue(result["accepted_for_gui"])
        self.assertFalse(result["persistent_image"])
        self.assertEqual(receiver.header, (b"VIMG", 480, 320, 307200, client.checksum(payload)))
        self.assertEqual(receiver.payload, payload)

    def test_wrong_length_before_network(self):
        with self.assertRaises(ValueError):
            client.push("invalid.invalid", b"wrong length")

    def test_rejection(self):
        with Receiver(status=2) as receiver, self.assertRaisesRegex(RuntimeError, "status 2"):
            client.push("127.0.0.1", client.test_pattern(), receiver.port)

    def test_wrong_ack_magic(self):
        with Receiver(magic=b"FAIL") as receiver, self.assertRaises(ValueError):
            client.push("127.0.0.1", client.test_pattern(), receiver.port)

    def test_truncated_ack(self):
        with Receiver(truncate=True) as receiver, self.assertRaises(ConnectionError):
            client.push("127.0.0.1", client.test_pattern(), receiver.port)


if __name__ == "__main__":
    unittest.main()
