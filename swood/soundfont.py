"""Parses .swood files."""

# See https://github.com/milkey-mouse/swood/issues/1

from . import complain, instruments, sample
import zipfile


class SoundFont:
    """Parses and holds information about .swood files."""

    def __init__(self, filename):
        if isinstance(filename, str):
            self.file = open(filename)
        else:
            self.file = filename

        try:
            try:
                self.file = zipfile.ZipFile(
                    self.file, compression=zipfile.ZIP_DEFLATED)
            except RuntimeError:
                self.file = zipfile.ZipFile(self.file)
            self.parse_zip()
        except zipfile.BadZipFile:
            self.parse_ini()
