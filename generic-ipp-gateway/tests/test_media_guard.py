import unittest
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from media_guard import admit_80mm, IPPFormatError


def request(media, name="media", tag=0x44):
    data = b"\x02\x00\x00\x02\x00\x00\x00\x01\x01"
    data += b"\x02"
    if media is not None:
        key = name.encode("ascii")
        data += bytes([tag]) + len(key).to_bytes(2, "big") + key + len(media).to_bytes(2, "big") + media
    return data + b"\x03"


class MediaGuardTest(unittest.TestCase):
    def test_allow_exact_80mm(self):
        self.assertTrue(admit_80mm(request(b"custom_receipt_80x200mm")))

    def test_reject_a4(self):
        self.assertFalse(admit_80mm(request(b"iso_a4_210x297mm")))

    def test_reject_58mm(self):
        self.assertFalse(admit_80mm(request(b"custom_receipt_58x200mm")))

    def test_default_queue_media_without_explicit_request(self):
        self.assertTrue(admit_80mm(request(None)))

    def test_reject_unvalidated_media_col(self):
        self.assertFalse(admit_80mm(request(b"", name="media-col", tag=0x34)))

    def test_media_col_dimension_guard(self):
        def attr(tag, name, value):
            name = name.encode("ascii")
            return bytes([tag]) + len(name).to_bytes(2, "big") + name + len(value).to_bytes(2, "big") + value

        def col(width, named=False):
            return (b"\x02\x00\x00\x02\x00\x00\x00\x01\x01\x02" +
                    attr(0x34, "media-col", b"") +
                    attr(0x4a, "", b"media-size") +
                    attr(0x34, "", b"") +
                    attr(0x4a, "", b"x-dimension") +
                    attr(0x21, "", width.to_bytes(4, "big")) +
                    attr(0x4a, "", b"y-dimension") +
                    attr(0x21, "", (20000).to_bytes(4, "big")) +
                    ((attr(0x4a, "", b"media-size-name") +
                      attr(0x44, "", b"custom_receipt_80x200mm")) if named else b"") +
                    attr(0x37, "", b"") + attr(0x37, "", b"") + b"\x03")
        self.assertTrue(admit_80mm(col(8000)))
        self.assertFalse(admit_80mm(col(5800)))
        self.assertFalse(admit_80mm(col(5800, named=True)), "explicit 80mm name must not override contradictory 58mm width")
        self.assertFalse(admit_80mm(col(21000)))

    def test_reject_malformed(self):
        with self.assertRaises(IPPFormatError):
            admit_80mm(request(b"ok")[:-3])


if __name__ == "__main__":
    unittest.main()
