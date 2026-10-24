import unittest
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

    def test_reject_unspecified(self):
        self.assertFalse(admit_80mm(request(None)))

    def test_reject_unvalidated_media_col(self):
        with self.assertRaises(IPPFormatError):
            admit_80mm(request(b"", name="media-col", tag=0x34))

    def test_reject_malformed(self):
        with self.assertRaises(IPPFormatError):
            admit_80mm(request(b"ok")[:-3])


if __name__ == "__main__":
    unittest.main()
