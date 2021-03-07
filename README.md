# mpypack
A micropython project packing tools.

Can sync folder to mpy board, compiling and packing the whole folder to another output folder.

If the command line tool is not what you need, you can use this as library, and develop your own build/packing python scripts.

# Quick Overview
After place the correct config file, sync files to mpy board:
``` mpypack sync ```

Enter REPL mode: 
``` mpypack repl ```

More Uesage:
```
Usage: mpypack [OPTIONS] COMMAND [ARGS]...

Options:
  -c, --config TEXT   Set config file path. (default .mpypack.conf)
  -p, --port TEXT     Name of serial port for connected board.
  -b, --baud INTEGER  Baud rate for the serial connection (default 115200).
  --version           Show the version and exit.
  --help              Show this message and exit.

Commands:
  build  Pack up source folder.
  get    Retrieve a file from the board.
  repl   Enter repl mode
  sync   Sync local file to mpy board.
```

# Environment
This command line tool also use config file and environment values as parameters.

Avaliable environment values:
```
MPYPACK_CONFIG: The config file path.

MPYPACK_PORT
MPYPACK_BAUD
MPYPACK_LOCAL
MPYPACK_REMOTE
MPYPACK_SOURCE
MPYPACK_OUTPUT
MPYPACK_INCLUDE
MPYPACK_EXCLUDE
MPYPACK_HIDDEN
MPYPACK_COMPILE
```

# Config File
The default config file is .mpypack.conf in current workspace folder. this can be set by "-c / --config" flag.

Example config file:
```ini
[mpypack_config]
# ----board----

#>>>>----port----<<<<
# port = COM3

#>>>>----baud rate----<<<<
baud = 115200

# ----parameter----

#>>>>----sync local source----<<<<
# local = D:\Code\Micropython\ESP32\Play32

#>>>>----sync remote target----<<<<
remote = /

#>>>>----build source----<<<<
# source = D:\Code\Micropython\ESP32\Play32

#>>>>----build output----<<<<
# output = D:\Code\Micropython\ESP32\Play32\.build

#>>>>----include path RegExp----<<<<
# include = \.py$

#>>>>----exclude path RedExp----<<<<
# exclude = \.pyc$

#>>>>----include hidden file----<<<<
hidden = false

#>>>>----compile .py to .mpy----<<<<
compile = true

#>>>>----compile arch----<<<<
#arch = xtensawin

#>>>>----mpy-cross executable path----<<<<
# mpycross = D:\Code\Micropython\micropython\mpy-cross\mpy-cross.exe
```
