try:
    from fileexplorer import FileExplorer, FileExplorerStatus
    from filesync import FileSync
except ImportError:
    from mpypack.fileexplorer import FileExplorer, FileExplorerStatus
    from mpypack.filesync import FileSync

import os.path as syspath
from sys import argv
import re, platform

print_progress=lambda p, t, op, name: print("{}/{} {:.2f}%    {}: {}".format(p, t, p*100/t, op, name))

def windows_full_port_name(port_name):
    # Helper function to generate proper Windows COM port paths.  Apparently
    # Windows requires COM ports above 9 to have a special path, where ports below
    # 9 are just referred to by COM1, COM2, etc. (wacky!)  See this post for
    # more info and where this code came from:
    # http://eli.thegreenplace.net/2009/07/31/listing-all-serial-ports-on-windows-with-python/
    m = re.match("^COM(\d+)$", port_name, re.IGNORECASE)
    if m and int(m.group(1)) < 10:
        return port_name
    else:
        return "\\\\.\\{0}".format(port_name)

def main():
    if len(argv) < 2:
        return
    port_name = argv[1]
    if platform.system() == "Windows":
        port_name = windows_full_port_name(port_name)
    fe = FileExplorer(port_name)
    fs = FileSync(fe, local_path=syspath.abspath("."), remote_path="/")
    # fs = FileSync(fe, local_path='D:\Code\Micropython\ESP32\Play32', remote_path="/")
    if len(argv) >= 3 and argv[2] == 'repl':
        fe.repl()
    else:
        fs.sync_dir_remote_with_local(True, progress_callback=print_progress)
    # test start
    # fe.repl()

if __name__ == "__main__":
    main()