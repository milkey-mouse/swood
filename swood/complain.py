"""User-friendly exception handler for swood."""
import http.client
import traceback
import sys
import os

__file__ = os.path.abspath(__file__)


class ComplainToUser(Exception):
    """When used with ComplaintFormatter, tells the user what error (of theirs) caused the failure and exits."""
    pass


def can_submit():
    if not os.path.isdir(os.path.expanduser("~/.swood")):
        os.mkdir(os.path.expanduser("~/.swood"))
    sbpath = os.path.expanduser("~/.swood/submit-bugs")
    if os.path.isfile(sbpath):
        try:
            with open(sbpath) as sb:
                resp = sb.read(1)
                if resp == "1":
                    return 1
                elif resp == "0":
                    return 0
        except:
            pass
    while True:
        resp = input(
            "Something went wrong. Do you want to send an anonymous bug report? (Type Y or N): ").lower()
        if resp in ("yes", "y", "true"):
            try:
                with open(sbpath, "w") as sb:
                    sb.write("1")
            except:
                pass
            return 1
        elif resp in ("no", "n", "false"):
            try:
                with open(sbpath, "w") as sb:
                    sb.write("0")
            except:
                pass
            return 0


class ComplaintFormatter:
    """Notifies the user when the program fails predictably and uploads bug reports.

    When used in a with statement, ComplaintFormatter catches all exceptions. If the
    exception is a ComplainToUser exception, it will simply print the error message
    and exit (with an exit code of 1). If the exception is something else (i.e. an
    actual, unexpected exception), it will upload the traceback to the swood debug
    server (unless the user has opted out of sending bug reports.)
    """

    def __init__(self, version=None):
        self.version = version

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc, tb):
        if isinstance(exc, ComplainToUser):
            print("Error: {}".format(exc), file=sys.stderr)
            sys.exit(1)
        elif isinstance(exc, Exception):
            # scrub stack of full path names for extra privacy
            # also normalizes the paths, helping to detect dupes
            scrubbed_stack = traceback.extract_tb(tb)
            # cut off traces of stuff that isn't ours
            others_cutoff = next(idx for idx, fs in enumerate(scrubbed_stack) if os.path.samefile(
                os.path.dirname(fs.filename), os.path.dirname(__file__)))
            scrubbed_stack = scrubbed_stack[others_cutoff:]
            # rewrite paths so they contain only relative directories
            # (hides username on Windows and Linux)
            dirstart = os.path.abspath(
                os.path.join(os.path.dirname(__file__), ".."))
            for fs in scrubbed_stack:
                fs.filename = os.path.relpath(
                    fs.filename, start=dirstart).replace("\\", "/")
            str_tb = "Traceback (most recent call last):\n" + \
                "".join(traceback.format_list(scrubbed_stack)) + \
                "".join(traceback.format_exception_only(exc_type, exc))

            if self.version is not None:
                str_tb = "# " + self.version + "\n" + str_tb

            if "--optout" in sys.argv or "-o" in sys.argv:
                print(
                    "Something went wrong. A bug report will not be sent because of your command-line flag.", file=sys.stderr)
                return False
            elif os.environ.get("SWOOD_OPTOUT") == "1":
                print(
                    "Something went wrong. A bug report will not be sent because of your environment variable.", file=sys.stderr)
                return False
            elif not can_submit():
                print(
                    "Something went wrong. A bug report will not be sent because of your config setting.", file=sys.stderr)
                return False
            else:
                print(
                    "Something went wrong. A bug report will be sent to help figure it out. (see --optout)", file=sys.stderr)
                try:
                    conn = http.client.HTTPSConnection("meme.institute")
                    conn.request("POST", "/swood/bugs/submit", str_tb)
                    resp = conn.getresponse().read().decode("utf-8")
                    if resp == "done":
                        print("New bug submitted!", file=sys.stderr)
                    elif resp == "dupe":
                        print(
                            "This bug is already in the queue to be fixed.", file=sys.stderr)
                    else:
                        raise Exception
                except Exception:
                    print("Submission of bug report failed.", file=sys.stderr)
                    traceback.print_exc()
        return True
