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

    def parse_zip(self):
        """Parses a ZIP of a .swood INI file and its samples without extracting."""
        try:
            valid_extensions = {"swood", "ini", "txt"}
            ini_path = next(fn for fn in self.file.namelist()
                            if fn.split(".")[-1] in valid_extensions)
        except StopIteration:
            raise complain.ComplainToUser(
                "Couldn't find config file in ZIP. Be sure it ends in .ini, .swood, or .txt.'")
        config_txt = self.file.read(ini_path)
        raise NotImplementedError
