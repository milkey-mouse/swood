from time import sleep
import time
import sys
import os

sys.path.insert(0, os.path.realpath(".."))
import swood
assert(os.path.realpath(swood.__file__) ==
       os.path.realpath("../swood/__init__.py"))


def find_program(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        vlc_location = os.path.join(path.strip('"'), prog)
        if os.path.isfile(path):
            return vlc_location, args
    return None


def play_audio(clip):
    import subprocess
    if os.name == "nt":
        if os.path.isfile("C:/Program Files (x86)/VideoLAN/VLC/vlc.exe"):
            return subprocess.Popen(["C:/Program Files (x86)/VideoLAN/VLC/vlc.exe", clip, "vlc://quit"])
        elif find_program("vlc.exe"):
            return subprocess.Popen([find_program("vlc.exe"), clip, "vlc://quit"])
        elif os.path.isfile("C:/Program Files (x86)/Windows Media Player/wmplayer.exe"):
            return subprocess.Popen(["C:/Program Files (x86)/Windows Media Player/wmplayer.exe", clip, "/Play", "/Close"])
        elif find_program("wmplayer.exe"):
            return subprocess.Popen([find_program("wmplayer.exe"), clip, "/Play", "/Close"])
        else:
            raise FileNotFoundError("Can't find an audio player.")

running_player = None


def run(midi, *args, play=False, wait=False):
    global running_player
    print("~~~~~~~~~~ Testing '{}' ~~~~~~~~~~".format(midi))
    out = "outputs/" + midi + ".wav"
    start = time.perf_counter()
    swood.run_cmd(argv=["samples/doot.wav", "midis/" +
                        midi + ".mid", out, "--no-pbar", *args])
    print("Finished '{}' in {} seconds.".format(
        midi, round(time.perf_counter() - start, 2)))
    if play:
        if not os.path.isfile(out):
            return
        if running_player:
            running_player.wait()
            os.remove(running_player.args[1])
        running_player = play_audio(out)
        if wait:
            running_player.wait()
            os.remove(out)

if sys.argv[1] == "playall":
    run("dummy", play=True)
    run("beethoven", play=True)
    run("pitchbend", play=True, wait=True)
elif sys.argv[1] == "all":
    run("finalfantasy")
    run("dummy")
    run("beethoven")
    run("pitchbend")
elif sys.argv[1] == "bend":
    run("pitchbend")
