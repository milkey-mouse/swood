from time import sleep
import sys
import os

sys.path.insert(0, os.path.realpath("../../swood"))
import swood

def find_program(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        vlc_location = os.path.join(path.strip('"'), prog)
        if os.path.isfile(fpath):
            return vlc_location, args
    return None

def play(clip):
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

def run(midi, *args, play=False):
    out = "samples/" + midi + ".wav"
    try:
        swood.run_cmd(["samples/doot.wav", "midis/" + midi + ".mid", out, *args])
    except exc as BaseException:  # if I let any exception through the VS Code Python debugger will catch it
        if isinstance(exc, Exception):
            raise
    if play:
        if running_player:
            running_player.wait()
        running_player = play(out)

if sys.argv[1] == "playall":
    run("pitchbend")
elif sys.argv[1] == "all":
    run("beethoven")
    run("dummy")
    run("pitchbend")
elif sys.argv[1] == "bend":
    run("pitchbend")