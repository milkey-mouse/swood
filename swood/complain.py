import traceback
import sys
import os


class ComplainToUser(Exception):
    pass


class ComplaintFormatter(object):
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc, tb):
        if exc_type == ComplainToUser:
            print("Error: {}".format(exc))
        elif exc_type is not None:
            tb = traceback.format_exc()
            if "--optout" in sys.argv or os.environ.get("SWOOD_OPTOUT") is not None:
                print("Something went wrong. A bug report will not be sent because of your environment variable/CLI option.")
                traceback.print_exc()
            else:
                print("Something went wrong. A bug report will be sent to help figure it out. (see --optout)")
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
                    print("Apparently we can't even send a bug report right. Sorry about that.")
                    traceback.print_exc()
        return True
