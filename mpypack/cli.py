try:
    from fileexplorer import FileExplorer, FileExplorerStatus
    from filesync import FileSync, PATTERN_INCLUDE, PATTERN_EXCLUDE
    from mpycross import set_mpy_cross_executable
except ImportError:
    from mpypack.fileexplorer import FileExplorer, FileExplorerStatus
    from mpypack.filesync import FileSync, PATTERN_INCLUDE, PATTERN_EXCLUDE
    from mpypack.mpycross import set_mpy_cross_executable

import re, platform
from configparser import ConfigParser
from os.path import exists

import click

# const value -------->
ENV_PREFIX = "MPYPACK_{}"
DEFAULT_CONFIG_FILE = ".mpypack.conf"
CONFIG_FILE_SECTION = "mpypack_config"

CONFIG_OPTION_PORT = "port"
CONFIG_OPTION_BAUD = "baud"
CONFIG_OPTION_COMPILE = "compile"
CONFIG_OPTION_ARCH = "arch"
CONFIG_OPTION_MPYCORSS = "mpycross"
CONFIG_OPTION_LOCAL = "local"
CONFIG_OPTION_REMOTE = "remote"
CONFIG_OPTION_INCLUDE = "include"
CONFIG_OPTION_EXCLUDE = "exclude"
CONFIG_OPTION_HIDDEN = "hidden"
CONFIG_OPTION_SOURCE = "source"
CONFIG_OPTION_OUTPUT = "output"

# global value -------->
conf:ConfigParser = ConfigParser()

# help function -------->
def print_progress(p, t, sub_p, sub_t, op, name):
    if t == 0:
        count = ""
    else:
        count = "{}/{} ".format(p, t)
    if sub_t == 0:
        proc = ""
    else:
        proc = "{:.2f}%    ".format(sub_p*100/sub_t)
    print("{}\r {}{}{}: {}".format(" "*80, count, proc, op, name), end="\r")

def clear_console(message="Done."):
    print("{}\r{}".format(" "*80, message))

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

def has_config(key: str):
    return conf.has_section(CONFIG_FILE_SECTION) and conf.has_option(CONFIG_FILE_SECTION, key)

def get_config(key: str, default=None):
    if has_config(key):
        return conf[CONFIG_FILE_SECTION][key]
    return default

def update_config(key: str, value, default=None):
    # cli > env > conf_file > default
    if value == None:
        if (default == None) or (has_config(key)):
            return
        else:
            value = default
    if not conf.has_section(CONFIG_FILE_SECTION):
        conf.add_section(CONFIG_FILE_SECTION)
    conf[CONFIG_FILE_SECTION][key] = str(value)

def print_config():
    # print config
    click.echo("Config:")
    for s in conf.sections():
        for o in conf[s].keys():
            click.echo("{}: {}".format(o, conf[s][o]))

def get_file_explorer():
    # ensure required options
    if get_config(CONFIG_OPTION_PORT) == None:
        raise click.BadParameter("Missing option '-p' / '--port'")
    if get_config(CONFIG_OPTION_BAUD) == None:
        raise click.BadParameter("Missing option '-b' / '--baud'")
    port = get_config(CONFIG_OPTION_PORT)
    if platform.system() == "Windows":
        port = windows_full_port_name(port)
    return FileExplorer(port, get_config(CONFIG_OPTION_BAUD))

# cli function -------->
@click.group()
@click.option("-c", "--config", "config", default=DEFAULT_CONFIG_FILE, type=click.STRING, envvar=ENV_PREFIX.format("CONFIG"),
    help="Set config file path. (default .mpypack.conf)"
)
@click.option( "-p", "--port", "port", default=None, type=click.STRING, envvar=ENV_PREFIX.format("PORT"),
    help="Name of serial port for connected board.",
)
@click.option( "-b", "--baud", "baud", default=None, type=click.INT, envvar=ENV_PREFIX.format("BAUD"),
    help="Baud rate for the serial connection (default 115200).",
)
@click.version_option()
def cli(config, port, baud):
    global conf
    # read config file
    if exists(config):
        conf.read(config)
    # set default config
    update_config(CONFIG_OPTION_PORT, port)
    update_config(CONFIG_OPTION_BAUD, baud, 115200)

@cli.command()
def repl():
    '''
    Enter repl mode
    '''
    file_explorer = get_file_explorer()
    file_explorer.repl()
    clear_console()

@cli.command()
@click.option("-l", "--local", "local", default=None, type=click.STRING, envvar=ENV_PREFIX.format("LOCAL"),
    help="Local path to sync. (default .)"
)
@click.option("-r", "--remote", "remote", default=None, type=click.STRING, envvar=ENV_PREFIX.format("REMOTE"),
    help="Remote path to sync. (default /)"
)
@click.option("-i", "--include", "include", default=None, type=click.STRING, envvar=ENV_PREFIX.format("INCLUDE"),
    help="Include path RegExp(test on remote path)."
)
@click.option("-e", "--exclude", "exclude", default=None, type=click.STRING, envvar=ENV_PREFIX.format("EXCLUDE"),
    help="Exclude path RegExp(test on remote path)."
)
@click.option("-h", "--hidden", "hidden", default=None, type=click.BOOL, envvar=ENV_PREFIX.format("HIDDEN"),
    help="Sync hidden file and folder(name start with '.'). (default False)"
)
@click.option("-c", "--compile", "compile", default=None, type=click.BOOL, envvar=ENV_PREFIX.format("COMPILE"),
    help="Compile .py file before upload, always ignore 'main.py' and 'boot.py'. (default False)"
)
@click.option("-a", "--arch", "arch", default=None, type=click.STRING, envvar=ENV_PREFIX.format("ARCH"),
    help="Set architecture for native emitter; x86, x64, armv6, armv7m, armv7em, armv7emsp, armv7emdp, xtensa, xtensawin"
)
@click.option("-m", "--mpycross", "mpycross", default=None, type=click.STRING, envvar=ENV_PREFIX.format("MPYCORSS"),
    help="mpy-cross exec path. Required to compile .py file. Script will search current workspace folder and mpy_cross module`s folder. If there is no mpy-cross executable, you should set it manually."
)
def sync(local, remote, include, exclude, hidden, compile, arch, mpycross):
    '''
    Sync local file to mpy board.
    '''
    # set default config
    update_config(CONFIG_OPTION_LOCAL, local, ".")
    update_config(CONFIG_OPTION_REMOTE, remote, "/")
    update_config(CONFIG_OPTION_INCLUDE, include)
    update_config(CONFIG_OPTION_EXCLUDE, exclude)
    update_config(CONFIG_OPTION_HIDDEN, hidden, False)
    update_config(CONFIG_OPTION_COMPILE, compile, False)
    update_config(CONFIG_OPTION_ARCH, arch)
    update_config(CONFIG_OPTION_MPYCORSS, mpycross)
    # get config
    c_local = get_config(CONFIG_OPTION_LOCAL)
    c_remote = get_config(CONFIG_OPTION_REMOTE)
    c_compile = get_config(CONFIG_OPTION_COMPILE).lower() == "true"
    c_arch = get_config(CONFIG_OPTION_ARCH)
    c_hidden = get_config(CONFIG_OPTION_HIDDEN).lower() == "true"
    c_include = get_config(CONFIG_OPTION_INCLUDE)
    c_include = PATTERN_INCLUDE if c_include == None else [re.compile(c_include)]
    c_exclude = get_config(CONFIG_OPTION_EXCLUDE)
    c_exclude = PATTERN_EXCLUDE if c_exclude == None else [re.compile(c_exclude)]
    c_mpycross = get_config(CONFIG_OPTION_MPYCORSS)
    # exec
    if c_mpycross != None:
        set_mpy_cross_executable(c_mpycross)
    file_explorer = get_file_explorer()
    fs = FileSync(file_explorer, local_path=c_local, remote_path=c_remote, include_pattern=c_include, exclude_pattern=c_exclude)
    fs.sync_dir_remote_with_local(compile=c_compile, arch=c_arch, ignore_hidden=(not c_hidden), progress_callback=print_progress)
    clear_console()

@cli.command()
@click.option("-r", "--remote", "remote", default=None, type=click.STRING, envvar=ENV_PREFIX.format("REMOTE"),
    help="Remote path to sync. (default /)"
)
@click.option("-s", "--source", "source", default=None, type=click.STRING, envvar=ENV_PREFIX.format("SOURCE"),
    help="Local path to build. (default .)"
)
@click.option("-o", "--output", "output", default=None, type=click.STRING, envvar=ENV_PREFIX.format("OUTPUT"),
    help="Output folder path to build. (default .build)"
)
@click.option("-i", "--include", "include", default=None, type=click.STRING, envvar=ENV_PREFIX.format("INCLUDE"),
    help="Include path RegExp(test on remote path)."
)
@click.option("-e", "--exclude", "exclude", default=None, type=click.STRING, envvar=ENV_PREFIX.format("EXCLUDE"),
    help="Exclude path RegExp(test on remote path)."
)
@click.option("-h", "--hidden", "hidden", default=None, type=click.BOOL, envvar=ENV_PREFIX.format("HIDDEN"),
    help="Include hidden file and folder(name start with '.'). (default False)"
)
@click.option("-c", "--compile", "compile", default=None, type=click.BOOL, envvar=ENV_PREFIX.format("COMPILE"),
    help="Compile .py file, always ignore 'main.py' and 'boot.py'. (default False)"
)
@click.option("-a", "--arch", "arch", default=None, type=click.STRING, envvar=ENV_PREFIX.format("ARCH"),
    help="Set architecture for native emitter; x86, x64, armv6, armv7m, armv7em, armv7emsp, armv7emdp, xtensa, xtensawin"
)
@click.option("-m", "--mpycross", "mpycross", default=None, type=click.STRING, envvar=ENV_PREFIX.format("MPYCORSS"),
    help="mpy-cross exec path. Required to compile .py file. Script will search current workspace folder and mpy_cross module`s folder. If there is no mpy-cross executable, you should set it manually."
)
def build(remote, source, output, include, exclude, hidden, compile, arch, mpycross):
    '''
    Pack up source folder.
    Copy (and maybe compile) source file to another folder.
    '''
    # set default config
    update_config(CONFIG_OPTION_REMOTE, remote, "/")
    update_config(CONFIG_OPTION_SOURCE, source, ".")
    update_config(CONFIG_OPTION_OUTPUT, output, ".build")
    update_config(CONFIG_OPTION_INCLUDE, include)
    update_config(CONFIG_OPTION_EXCLUDE, exclude)
    update_config(CONFIG_OPTION_HIDDEN, hidden, False)
    update_config(CONFIG_OPTION_COMPILE, compile, False)
    update_config(CONFIG_OPTION_ARCH, arch)
    update_config(CONFIG_OPTION_MPYCORSS, mpycross)
    # get config
    c_remote = get_config(CONFIG_OPTION_REMOTE)
    c_source = get_config(CONFIG_OPTION_SOURCE)
    c_output = get_config(CONFIG_OPTION_OUTPUT)
    c_compile = get_config(CONFIG_OPTION_COMPILE).lower() == "true"
    c_arch = get_config(CONFIG_OPTION_ARCH)
    c_hidden = get_config(CONFIG_OPTION_HIDDEN).lower() == "true"
    c_include = get_config(CONFIG_OPTION_INCLUDE)
    c_include = PATTERN_INCLUDE if c_include == None else [re.compile(c_include)]
    c_exclude = get_config(CONFIG_OPTION_EXCLUDE)
    c_exclude = PATTERN_EXCLUDE if c_exclude == None else [re.compile(c_exclude)]
    c_mpycross = get_config(CONFIG_OPTION_MPYCORSS)
    # exec
    if c_mpycross != None:
        set_mpy_cross_executable(c_mpycross)
    fs = FileSync(None, local_path=c_source, remote_path=c_remote, include_pattern=c_include, exclude_pattern=c_exclude)
    fs.build(compile=c_compile, arch=c_arch, ignore_hidden=(not c_hidden), target_folder=c_output, progress_callback=print_progress)
    clear_console()

@cli.command()
@click.argument("remote_file", type=click.STRING)
@click.argument("local_file", type=click.STRING, required=False)
def get(remote_file, local_file):
    """
    Retrieve a file from the board.
    If no local_file set, it will download to current workspace folder.
    """
    # Get the file contents.
    file_explorer = get_file_explorer()
    with file_explorer:
        file = file_explorer.stat(remote_file)
        def upload_progress_callback(sub_p, sub_t):
            print_progress(0, 0, sub_p, sub_t, "download", str(file.abspath))
        contents = file_explorer.download(file, progress_callback=upload_progress_callback)
    # write to file
    if local_file is None:
        local_file = file.name
    with open(local_file, "wb") as f:
        f.write(contents)
    clear_console()

def main():
    cli()

if __name__ == "__main__":
    main()