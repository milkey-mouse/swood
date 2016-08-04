"""User-friendly exception handler for swood."""

import traceback
import sys
import os


class ComplainToUser(Exception):
    """When used with ComplaintFormatter, tells the user what error (of theirs) caused the failure and exits."""
    pass


class ComplaintFormatter(object):
    """Notifies the user when the program fails predictably and uploads bug reports.

    When used in a with statement, ComplaintFormatter catches all exceptions. If the
    exception is a ComplainToUser exception, it will simply print the error message
    and exit (with an exit code of 1). If the exception is something else (i.e. an
    actual, unexpected exception), it will upload the traceback to the swood debug
    server (unless the user has opted out of sending bug reports.)
    """

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc, tb):
        if isinstance(exc, ComplainToUser):
            print("Error: {}".format(exc))
            sys.exit(1)
        elif isinstance(exc, Exception):
            tb = traceback.format_exc()
            if "--optout" in sys.argv or "-o" in sys.argv or os.environ.get("SWOOD_OPTOUT") is not None:
                print(
                    "Something went wrong. A bug report will not be sent because of your environment variable/CLI option.")
                traceback.print_exc()
            else:
                print(
                    "Something went wrong. A bug report will be sent to help figure it out. (see --optout)")
                try:
                    import http.client
                    conn = http.client.HTTPSConnection("meme.institute")
                    conn.request("POST", "/swood/bugs/submit", tb)
                    resp = conn.getresponse().read().decode("utf-8")
                    if resp == "done":
                        print("New bug submitted!")
                    elif resp == "dupe":
                        print("This bug is already in the queue to be fixed.")
                    else:
                        raise Exception
                except Exception:
                    print(
                        "Apparently we can't even send a bug report right. Sorry about that.")
                    traceback.print_exc()
        return True
