import os
import stat
import subprocess
from glob import glob
from os.path import join, abspath, exists
from sys import path as import_path

mpy_cross_exe = None


def set_mpy_cross_executable(exe_file: str):
    global mpy_cross_exe
    mpy_cross_exe = exe_file
    if mpy_cross_exe == None or (not exists(mpy_cross_exe)):
        return
    try:
        st = os.stat(mpy_cross_exe)
        os.chmod(mpy_cross_exe, st.st_mode | stat.S_IEXEC)
    except OSError:
        pass

def run(*args, **kwargs):
    if mpy_cross_exe == None:
        raise Exception("Could not find executable mpy_cross.")
    try:
        return subprocess.Popen([mpy_cross_exe] + list(args), **kwargs)
    except:
        raise Exception("mpy-cross compile failed!")

# find exec file
def _find_under_dir(dir: os.PathLike):
    mpy_cross_list = glob(join(dir, 'mpy-cross*'))
    if len(mpy_cross_list) > 0:
        return abspath(mpy_cross_list[0])
    else:
        return None

def _find_mpy_cross_executable():
    # find under some folder
    find_in_dir = [
        abspath("."),
    ]
    for pth in import_path:
        find_in_dir.append(abspath(join(pth, "mpy_cross")))
    for dir in find_in_dir:
        exe_file = _find_under_dir(dir)
        if exe_file != None:
            return exe_file
    return None

def _init():
    set_mpy_cross_executable(_find_mpy_cross_executable())

_init()