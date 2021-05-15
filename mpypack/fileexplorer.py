try:
    from pyboard import Pyboard, PyboardError
except ImportError:
    from mpypack.pyboard import Pyboard, PyboardError
import re, ast, binascii
from pathlib import PurePath, PurePosixPath
from os import path as syspath
from io import BytesIO
from enum import IntEnum
from time import sleep
from typing import Callable, Iterator, List, Union
from threading import RLock

class FileEntityType(IntEnum):
    DIRECTORY = 0
    FILE = 1

FILE_SIZE_UNKNOWN = -1
class FileEntity:
    def __init__(self, abs_dir=PurePosixPath("/") , name:str="", type:FileEntityType=FileEntityType.FILE, size=FILE_SIZE_UNKNOWN):
        abs_dir = convert_to_posixpath(abs_dir)
        fullpath = abs_dir.joinpath(str(name))
        filedir = PurePosixPath(*fullpath.parts[:-1])
        filename = fullpath.parts[-1]
        if filename == "/":
            # root directory
            filedir = PurePosixPath("/")
            filename = ""
        self.directory = fullpath if type==FileEntityType.DIRECTORY else filedir
        self.name = "" if type==FileEntityType.DIRECTORY else filename
        self.type = type
        self.size = FILE_SIZE_UNKNOWN if type==FileEntityType.DIRECTORY else size
    @property
    def abspath(self):
        return self.directory.joinpath(self.name)
    def __fspath__(self):
        return str(self.abspath)
    def __eq__(self, o: object) -> bool:
        if isinstance(o, FileEntity):
            return self.abspath == o.abspath
        return False
    def __hash__(self) -> int:
        return hash((self.abspath, self.type))
    def __str__(self):
        return str(self.abspath)
    def __repr__(self):
        return self.print()
    def print(self):
        return '<FileEntity type="{}" dir="{}" name="{}" size="{}"/>'.format(
            "Directory" if self.type==0 else "File",
            self.directory,
            self.name,
            "UNKNOWN" if self.size==FILE_SIZE_UNKNOWN else self.size
        )

PathObject = Union[str, FileEntity, PurePath]
ProgressCallback = Union[None, Callable[[int, int],None]]

windows_path_re = re.compile(r'^\w\:')
def convert_to_posixpath(system_path:PathObject):
    system_path = convert_to_pathstr(system_path)
    system_path = system_path.replace('\\','/')
    system_path = windows_path_re.sub("", system_path, count=1)
    return PurePosixPath(system_path)
def convert_to_syspath(posix_path:PathObject):
    posix_path = convert_to_pathstr(posix_path)
    path_list = posix_path.split("/")
    return PurePath(syspath.sep.join(path_list))
def convert_to_pathstr(path:PathObject):
    if isinstance(path, FileEntity):
        return str(path.abspath)
    else: return str(path)

class FileExplorerError(IOError):
    pass

def _was_remote_exception(exception):
    """
    Helper function used to check for ENOENT (file doesn't exist),
    ENODEV (device doesn't exist, but handled in the same way) or
    EINVAL errors in an exception. Treat them all the same for the
    time being.

    :param  exception:      exception to examine
    :return:                True if non-existing
    """
    stre = str(exception)
    return any(err in stre for err in ("ENOENT", "ENODEV", "EINVAL", "OSError:"))

class FileExplorerStatus(IntEnum):
    UNKNOWN = 0
    READY = 1
    BUSY = 2

class FileExplorer:
    ''' Thread safe micropython remote file explorer class '''
    @property
    def CHUNK_SIZE(self): return 512
    def __init__(self, port, baudrate=115200):
        self.__device = Pyboard(port, baudrate)
        self.__current_path = PurePosixPath("/")
        self.__status = FileExplorerStatus.UNKNOWN
        self.sysname = ""
        self.__device_lock = RLock()

    def __del__(self):
        self.close()

    def __protect(fn):
        def func(self, *args, **kwargs):
            if not isinstance(self, FileExplorer):
                return fn(self, *args, **kwargs)
            else:
                self.__device_lock.acquire()
                try:
                    return fn(self, *args, **kwargs)
                finally:
                    self.__device_lock.release()
        return func

    def _require_device(self):
        self.__device_lock.acquire()
    
    def _release_device(self):
        self.__device_lock.release()

    def __enter__(self):
        self.__device_lock.acquire()
        self.init()
        return self
    
    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()
        self.__device_lock.release()

    @property
    def status(self):
        if self.__status == FileExplorerStatus.READY:
            if self.__device_lock.acquire(blocking=False):
                self.__device_lock.release()
                return FileExplorerStatus.READY
            else:
                return FileExplorerStatus.BUSY
        return self.__status

    @property
    def is_ready(self):
        return self.__status == FileExplorerStatus.READY

    @__protect
    def init(self):
        if self.is_ready:
            return
        self.__device.init()
        try:
            self.__device.enter_raw_repl()
        except PyboardError:
            sleep(0.5)
            self.__device.enter_raw_repl() # try again
        self.__device.exec("try:\n    import uos\nexcept ImportError:\n    import os as uos\nimport sys")
        self.__device.exec("try:\n    import ubinascii\nexcept ImportError:\n    import binascii as ubinascii")
        self.__current_path = PurePosixPath("/", self.__device.eval("uos.getcwd()").decode("utf8"))
        self.sysname = self.__device.eval("uos.uname()[0]").decode("utf-8")
        self.__status = FileExplorerStatus.READY

    @__protect
    def close(self):
        try: self.__device.exit_raw_repl()
        except: pass
        try: self.__device.close()
        except: pass
        self.__status = FileExplorerStatus.UNKNOWN
    
    # utils function
    def abspath(self, path:PathObject) -> PurePosixPath:
        path = convert_to_posixpath(path)
        parts = list(self.__current_path.joinpath(path).parts)
        #flat path
        p = 1 # parts[0] must be "/"
        while p < len(parts):
            name = parts[p]
            if name == "..":
                p -= 1
                if p >= 1:
                    del parts[p]
                    del parts[p]
                else:
                    p = 1
                    del parts[p]
            else:
                p += 1
        return PurePosixPath(*parts)

    # file explorer function
    @__protect
    def stat(self, path:PathObject) -> FileEntity:
        posixpath = self.abspath(path)
        try:
            res = self.__device.eval("uos.stat('{}')".format(posixpath))
        except Exception as e:
            if _was_remote_exception(e):
                raise FileExplorerError("No such file or directory: {}".format(posixpath))
            else:
                raise PyboardError(e)
        entity:tuple = ast.literal_eval(res.decode("utf-8"))
        ftype, _, _, _, _, _, fsize = entity[:7]
        ftype = FileEntityType.DIRECTORY if ftype == 0x4000 else FileEntityType.FILE
        return FileEntity(self.__current_path, path, ftype, fsize)

    @__protect
    def exist(self, path:PathObject) -> Union[FileEntity, bool]:
        posixpath = self.abspath(path)
        try:
            return self.stat(posixpath)
        except FileExplorerError:
            return False

    def pwd(self):
        return convert_to_pathstr(self.__current_path)

    @__protect
    def cd(self, path:PathObject="/"):
        posixpath = self.abspath(path)
        file = self.exist(posixpath)
        if file and file.type == FileEntityType.DIRECTORY:
            self.__current_path = posixpath
        else:
            raise FileExplorerError("No such directory: {}".format(posixpath))

    @__protect
    def ls(self, path:PathObject="") -> List[FileEntity]:
        posixpath = self.abspath(path)
        files:List[FileEntity] = []
        try:
            res = self.__device.eval("list(uos.ilistdir('{}'))".format(posixpath))
        except Exception as e:
            if _was_remote_exception(e):
                raise FileExplorerError("No such directory: {}".format(posixpath))
            else:
                raise PyboardError(e)
        entities = ast.literal_eval(res.decode("utf-8"))
        for entity in entities:
            fname, ftype = entity[:2]
            ftype = FileEntityType.DIRECTORY if ftype == 0x4000 else FileEntityType.FILE
            fsize = entity[3] if len(entity)>=4 else FILE_SIZE_UNKNOWN
            files.append(FileEntity(posixpath, fname, ftype, fsize))
        files.sort(key=lambda f: (f.type, f.name))
        return files
    
    @__protect
    def rm(self, path:PathObject):
        posixpath = self.abspath(path)
        file = self.stat(path)
        try:
            if file.type == FileEntityType.DIRECTORY:
                self.__device.eval("uos.rmdir('{}')".format(posixpath))
            else:
                self.__device.eval("uos.remove('{}')".format(posixpath))
        except PyboardError as e:
            if _was_remote_exception(e):
                raise FileExplorerError("Directory not empty: {}".format(posixpath))
            else:
                raise e
    
    @__protect
    def rmtree(self, path:PathObject):
        file = self.exist(path)
        if not file:
            return
        if file.type == FileEntityType.DIRECTORY:
            files = self.ls(file)
            for sub_file in files:
                self.rmtree(sub_file)
        self.rm(file)

    @__protect
    def mkdir(self, path:PathObject) -> FileEntity:
        posixpath = self.abspath(path)
        try:
            self.__device.eval("uos.mkdir('{}')".format(posixpath))
        except PyboardError as e:
            if _was_remote_exception(e):
                raise FileExplorerError("Directory may be invalid or exists: {}".format(posixpath))
            else:
                raise e
        return FileEntity(posixpath, "", FileEntityType.DIRECTORY, FILE_SIZE_UNKNOWN)
    
    @__protect
    def mkdirs(self, path:PathObject) -> FileEntity:
        posixpath = self.abspath(path)
        exist = self.exist(posixpath)
        if exist and exist.type == FileEntityType.DIRECTORY:
            return exist
        # create directories
        parts = posixpath.parts
        last = None
        for p in range(len(parts)):
            dir = PurePosixPath(*parts[:p+1])
            if self.exist(dir):
                continue
            last = self.mkdir(dir)
        return last

    @__protect
    def walk(self, path:PathObject, topdown=True) -> List[FileEntity]:
        posixpath = self.abspath(path)
        dir = self.exist(posixpath)
        lst = []
        if dir == False or dir.type != FileEntityType.DIRECTORY:
            raise FileExplorerError("Target is not directory: {}".format(posixpath))
        if dir == False:
            return lst
        files = self.ls(dir)
        if topdown:
            lst.append(dir)
            for file in files:
                if file.type != FileEntityType.DIRECTORY:
                    lst.append(file)
        for file in files:
            if file.type == FileEntityType.DIRECTORY:
                lst.extend(self.walk(file, topdown))
        if not topdown:
            lst.append(dir)
            for file in files:
                if file.type != FileEntityType.DIRECTORY:
                    lst.append(file)
        return lst

    @__protect
    def download(self, path:PathObject, progress_callback:ProgressCallback=None) -> bytes:
        posixpath = self.abspath(path)
        file = self.exist(path)
        if file == False or file.type == FileEntityType.DIRECTORY:
            raise FileExplorerError("Target is directory: {}".format(posixpath))
        try:
            dst = BytesIO()
            self.__device.exec("f = open('{}', 'rb')".format(posixpath))
            while dst.tell() < file.size:
                chunck = self.__device.exec("c = ubinascii.b2a_base64(f.read({}))\r\nsys.stdout.write(c)\r\n".format(self.CHUNK_SIZE))
                chunck = binascii.a2b_base64(chunck)
                dst.write(chunck)
                if progress_callback != None:
                    progress_callback(dst.tell(), file.size)
            self.__device.exec("f.close()")
            assert dst.tell() == file.size
            return dst.getvalue()
        except PyboardError as e:
            if _was_remote_exception(e):
                raise FileExplorerError("Read file failed: {}".format(posixpath))
            else:
                raise e

    @__protect
    def upload(self, path:PathObject, data:Iterator, progress_callback:ProgressCallback=None):
        posixpath = self.abspath(path)
        file = self.exist(path)
        if file and file.type == FileEntityType.DIRECTORY:
            raise FileExplorerError("Target is directory: {}".format(posixpath))
        filedir = PurePosixPath(*posixpath.parts[:-1])
        filename = posixpath.parts[-1]
        self.mkdirs(filedir)
        try:
            size = len(data)
            self.__device.exec("f = open('{}', 'wb')".format(posixpath))
            for p in range(0, size, self.CHUNK_SIZE):
                chunck = binascii.b2a_base64(data[p:p+self.CHUNK_SIZE]).decode("utf-8").replace("\r","").replace("\n","")
                self.__device.exec("f.write(ubinascii.a2b_base64('{}'))".format(chunck))
                if progress_callback != None:
                    p += self.CHUNK_SIZE
                    p = p if p < size else size
                    progress_callback(p, size)
            self.__device.exec("f.close()")
            return FileEntity(filedir, filename, FileEntityType.FILE, size)
        except PyboardError as e:
            if _was_remote_exception(e):
                raise FileExplorerError("Write file failed: {}".format(posixpath))
            else:
                raise e
    
    # extra function
    @__protect
    def exec(self, command, data_consumer=None):
        return self.__device.exec(command, data_consumer)

    @__protect
    def repl(self):
        need_init = False
        if self.__status != FileExplorerStatus.UNKNOWN:
            need_init = True
            self.close()
        self.__device.init()
        try:
            from serial.tools.miniterm import Miniterm, unichr, key_description
            miniterm = Miniterm(self.__device.serial)
            miniterm.raw = False
            miniterm.eol="crlf"
            miniterm.exit_character = unichr(0x1D)  # GS/CTRL+]
            miniterm.menu_character = unichr(0x14)  # Menu: CTRL+T
            miniterm.set_rx_encoding("UTF-8")
            miniterm.set_tx_encoding("UTF-8")
            miniterm.update_transformations()
            print('--- Miniterm on {p.name}  {p.baudrate},{p.bytesize},{p.parity},{p.stopbits} ---'.format(p=miniterm.serial))
            print('--- Quit: {} | Menu: {} ---\n'.format(
                key_description(miniterm.exit_character),
                key_description(miniterm.menu_character),
            ))
            miniterm.start()
            try:
                miniterm.join(True)
            except KeyboardInterrupt:
                pass
            print("\n--- exit ---")
            miniterm.join()
            miniterm.console.cleanup()
            miniterm.close()
        finally:
            try: self.__device.close()
            except: pass
            if need_init:
                self.init()
