try:
    from fileexplorer import FileExplorer, FileEntity, FileEntityType, PathObject, convert_to_pathstr, FILE_SIZE_UNKNOWN, FileExplorerStatus
except ImportError:
    from mpypack.fileexplorer import FileExplorer, FileEntity, FileEntityType, PathObject, convert_to_pathstr, FILE_SIZE_UNKNOWN, FileExplorerStatus
from pathlib import PurePath, PurePosixPath
from os import walk, remove, PathLike, path as syspath
from tempfile import gettempdir
import re, json, hashlib, mpy_cross, uuid
from typing import Callable, Union
import tempfile

PATTERN_PY = re.compile(r'\.py$', re.IGNORECASE)
PATTERN_IGNORED = [
    re.compile(r'^/?main\.py$', re.IGNORECASE),
    re.compile(r'^/?boot\.py$', re.IGNORECASE),
]
SyncProgressCallback = Union[None, Callable[[int, int, str, str],None]]

class FileSync():
    def __init__(self, file_explorer, local_path=".", remote_path="/", remote_record_file="/.mpypack_sha256.json", compile_ignore_pattern=PATTERN_IGNORED):
        self.__fe:FileExplorer = file_explorer
        self.__local = PurePath(syspath.abspath(local_path))
        self.__remote = PurePosixPath(remote_path)
        self.__record_file_path = PurePosixPath(remote_record_file)
        self.__pattern_compile_ignored = compile_ignore_pattern
    
    def should_compile(self, path:PathObject):
        if isinstance(path, FileEntity):
            if path.type == FileEntityType.DIRECTORY:
                return False
            pathstr = path.name
        else:
            pathstr = convert_to_pathstr(path)
        for ptn in self.__pattern_compile_ignored:
            if len(ptn.findall(pathstr)) > 0:
                return False
        return len(PATTERN_PY.findall(pathstr)) > 0

    def get_local_path(self, path:PathObject):
        pth = PurePosixPath(convert_to_pathstr(path)).relative_to(self.__remote)
        return self.__local.joinpath(pth)

    def get_remote_path(self, path:PathLike):
        pth = PurePath(path).relative_to(self.__local)
        return self.__remote.joinpath(pth)

    def __walk_local_like_remote(self, ignore_hidden=True):
        lst = []
        for cur_dir, _, files in walk(self.__local):
            for p in PurePath(cur_dir).parts:
                if not ignore_hidden:
                    break
                if p.startswith(".") and p != ".":
                    break # ignore hidden dir
            else:
                pth = self.get_remote_path(cur_dir)
                lst.append(FileEntity(pth, "", FileEntityType.DIRECTORY, FILE_SIZE_UNKNOWN))
                for f in files:
                    if ignore_hidden and f.startswith("."):
                        continue # ignore hidden file
                    size = syspath.getsize(syspath.join(cur_dir, f))
                    lst.append(FileEntity(pth, f, FileEntityType.FILE, size))
        return lst

    def __walk_remote(self):
        return self.__fe.walk(self.__remote)
    
    def __hash_local_file(self, path:PathObject, compile=False):
        pth = self.get_local_path(path)
        hash = hashlib.sha256()
        with open(pth, "rb") as f:
            hash.update(f.read())
            if compile and self.should_compile(path):
                hash.update(b'compile')
            return hash.hexdigest()

    def __upload_file(self, local_file:PathLike, remote_file:PathObject=None, compile=False):
        lol = convert_to_pathstr(local_file)
        if remote_file == None:
            remote_file = self.get_remote_path(local_file)
        rmt = convert_to_pathstr(remote_file)
        if compile and self.should_compile(lol) and self.should_compile(rmt):
            tmppath = PurePath(tempfile.gettempdir()).joinpath(str(uuid.uuid4())+".mpy")
            mpy_cross.run("-o", tmppath, lol).wait()
            with open(tmppath, "rb") as f:
                data = f.read()
            remove(tmppath)
            rmt = PATTERN_PY.sub(".mpy", rmt)
        else:
            with open(lol, "rb") as f:
                data = f.read()
        self.__fe.upload(rmt, data)

    def sync_dir_remote_with_local(self, compile=False, ignore_hidden=True, upload_only_modified=True, delete_exist_file=True, progress_callback:SyncProgressCallback=None):
        self.__fe._require_device()
        need_close = False
        if self.__fe.status == FileExplorerStatus.UNKNOWN:
            need_close = True
        try:
            if need_close:
                self.__fe.init()
            file_record = {}
            new_file_record = {}
            try:
                j = self.__fe.download(self.__record_file_path).decode("utf-8")
                file_record = json.loads(j)
            except: pass
            # get file list
            local_files = set(self.__walk_local_like_remote(ignore_hidden))
            local_files_compiled = set()
            for f in local_files:
                if compile and self.should_compile(f):
                    new_name = PATTERN_PY.sub(".mpy", f.name)
                    local_files_compiled.update([FileEntity(f.directory, new_name, f.type, f.size)])
                else:
                    local_files_compiled.update([f])
            remote_files = set(self.__walk_remote())
            # get must upload file
            exist_files = remote_files - local_files_compiled # file to delete
            try:
                f = self.__fe.stat(self.__record_file_path)
                exist_files.discard(f)
            except: pass
            need_upload_files = []
            for local_file in local_files:
                if local_file.type == FileEntityType.DIRECTORY:
                    need_upload_files.append(local_file)
                    continue
                hash = self.__hash_local_file(local_file, compile)
                key = convert_to_pathstr(local_file)
                new_file_record[key] = hash
                if not (key in file_record and file_record[key] == hash) or (not upload_only_modified):
                    need_upload_files.append(local_file)
            # start upload
            total = len(need_upload_files)
            if delete_exist_file:
                total += len(exist_files)
            finished = 0
            if delete_exist_file:
                for f in exist_files:
                    if progress_callback != None:
                        progress_callback(finished, total, "delete", str(f.abspath.relative_to(self.__remote)))
                    self.__fe.rmtree(f)
                    finished += 1
            for f in need_upload_files:
                if progress_callback != None:
                    progress_callback(finished, total, "upload", str(f.abspath.relative_to(self.__remote)))
                if f.type == FileEntityType.DIRECTORY:
                    self.__fe.mkdirs(f)
                else:
                    self.__upload_file(self.get_local_path(f), f, compile)
                finished += 1
            # write record
            self.__fe.upload(self.__record_file_path, json.dumps(new_file_record).encode("utf-8"))
        finally:
            if need_close:
                self.__fe.close()
            self.__fe._release_device()