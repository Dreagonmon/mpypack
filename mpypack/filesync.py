try:
    import mpycross
    from fileexplorer import FileExplorer, FileEntity, FileEntityType, PathObject, convert_to_pathstr, FILE_SIZE_UNKNOWN, FileExplorerStatus, ProgressCallback
except ImportError:
    from mpypack import mpycross
    from mpypack.fileexplorer import FileExplorer, FileEntity, FileEntityType, PathObject, convert_to_pathstr, FILE_SIZE_UNKNOWN, FileExplorerStatus, ProgressCallback
from pathlib import PurePath, PurePosixPath
from os import walk, remove, PathLike, path as syspath, makedirs
from tempfile import gettempdir
from typing import Callable, Union
from shutil import rmtree
import re, json, hashlib, uuid, tempfile, traceback

PATTERN_PY = re.compile(r'\.py$', re.IGNORECASE)
PATTERN_COMPILE_IGNORED = [
    re.compile(r'^/?main\.py$', re.IGNORECASE),
    re.compile(r'^/?boot\.py$', re.IGNORECASE),
]
PATTERN_INCLUDE = [
    # re.compile(r'/\.mpypack_sha256.json$', re.IGNORECASE),
]
PATTERN_EXCLUDE = [
    re.compile(r'/?__pycache__/?', re.IGNORECASE),
    re.compile(r'\.pyc$', re.IGNORECASE),
    re.compile(r'\.pyi$', re.IGNORECASE),
    re.compile(r'README.md$', re.IGNORECASE),
]
SyncProgressCallback = Union[None, Callable[[int, int, int, int, str, str],None]]

def get_compiled_file_content(source:PathLike, arch=None):
    tmppath = PurePath(tempfile.gettempdir()).joinpath(str(uuid.uuid4())+".mpy")
    if arch != None:
        mpycross.run("-o", tmppath, "-march="+str(arch), source).wait()
    else:
        mpycross.run("-o", tmppath, source).wait()
    with open(tmppath, "rb") as f:
        data = f.read()
    remove(tmppath)
    return data

class FileSync():
    def __init__(self, file_explorer, local_path=".", remote_path="/", remote_record_file=".mpypack_sha256.json", compile_ignore_pattern=PATTERN_COMPILE_IGNORED, include_pattern=PATTERN_INCLUDE, exclude_pattern=PATTERN_EXCLUDE):
        self.__fe:FileExplorer = file_explorer
        self.__local = PurePath(syspath.abspath(local_path))
        self.__remote = PurePosixPath(remote_path)
        self.__record_file_path = self.__remote.joinpath(remote_record_file)
        self.__pattern_compile_ignored = compile_ignore_pattern
        self.__pattern_include = include_pattern
        self.__pattern_exclude = exclude_pattern
    
    def should_compile(self, path:PathObject):
        if isinstance(path, FileEntity):
            if path.type == FileEntityType.DIRECTORY:
                return False
        pathstr = convert_to_pathstr(path)
        for ptn in self.__pattern_compile_ignored:
            if len(ptn.findall(pathstr)) > 0:
                return False
        return len(PATTERN_PY.findall(pathstr)) > 0

    def should_include(self, path:PathObject, ignore_hidden=True):
        pathstr = convert_to_pathstr(path)
        for ptn in self.__pattern_include:
            if len(ptn.findall(pathstr)) > 0:
                return True
        for ptn in self.__pattern_exclude:
            if len(ptn.findall(pathstr)) > 0:
                return False
        for p in PurePath(pathstr).parts:
            if ignore_hidden and p.startswith(".") and p != ".":
                return False # ignore hidden file
        return True

    def get_local_path(self, path:PathObject):
        pth = PurePosixPath(convert_to_pathstr(path)).relative_to(self.__remote)
        return self.__local.joinpath(pth)

    def get_remote_path(self, path:PathLike):
        pth = PurePath(path).relative_to(self.__local)
        return self.__remote.joinpath(pth)

    def __walk_local_like_remote(self, ignore_hidden=True):
        lst = []
        for cur_dir, _, files in walk(self.__local):
            dir_pth = FileEntity(self.get_remote_path(cur_dir), "", FileEntityType.DIRECTORY, FILE_SIZE_UNKNOWN)
            # if not self.should_include(dir_pth, ignore_hidden):
            #     continue # ignore hidden dir
            lst.append(dir_pth)
            for f in files:
                size = syspath.getsize(syspath.join(cur_dir, f))
                file_pth = FileEntity(dir_pth, f, FileEntityType.FILE, size)
                # if not self.should_include(file_pth, ignore_hidden):
                #     continue # ignore hidden file
                lst.append(file_pth)
        for f in lst.copy():
            print(f)
            if not self.should_include(f, ignore_hidden):
                lst.remove(f)
        return lst

    def __walk_remote(self,  ignore_hidden=True):
        lst = []
        for f in self.__fe.walk(self.__remote):
            if self.should_include(f, ignore_hidden):
                lst.append(f)
        return lst
    
    def __hash_local_file(self, path:PathObject, compile=False):
        pth = self.get_local_path(path)
        hash = hashlib.sha256()
        with open(pth, "rb") as f:
            hash.update(f.read())
            if compile and self.should_compile(path):
                hash.update(b'compile')
            return hash.hexdigest()

    def __upload_file(self, local_file:PathLike, remote_file:PathObject=None, compile=False, arch=None, progress_callback:ProgressCallback=None):
        lol = convert_to_pathstr(local_file)
        if remote_file == None:
            remote_file = self.get_remote_path(local_file)
        rmt = convert_to_pathstr(remote_file)
        if compile and self.should_compile(lol) and self.should_compile(rmt):
            data = get_compiled_file_content(lol, arch=arch)
            rmt = PATTERN_PY.sub(".mpy", rmt)
        else:
            with open(lol, "rb") as f:
                data = f.read()
        self.__fe.upload(rmt, data, progress_callback=progress_callback)

    def sync_dir_remote_with_local(self, compile=False, arch=None, ignore_hidden=True, upload_only_modified=True, delete_exist_file=True, progress_callback:SyncProgressCallback=None):
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
            # ensure target folder exist on remote
            if not self.__fe.exist(self.__remote):
                self.__fe.mkdirs(self.__remote)
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
            # get files need delete
            exist_should_delete_files = remote_files - local_files_compiled # file to delete
            try:
                f = self.__fe.stat(self.__record_file_path)
                exist_should_delete_files.discard(f)
            except: pass
            # get must upload file
            need_upload_files = []
            dir_count = 0
            for local_file in local_files:
                if local_file.type == FileEntityType.DIRECTORY:
                    need_upload_files.append(local_file)
                    dir_count += 1
                    continue
                hash = self.__hash_local_file(local_file, compile)
                key = convert_to_pathstr(local_file)
                new_file_record[key] = hash
                if not (key in file_record and file_record[key] == hash) or (not upload_only_modified):
                    need_upload_files.append(local_file)
            # start upload
            total = len(need_upload_files) - dir_count
            if delete_exist_file:
                total += len(exist_should_delete_files)
            finished = 0
            if delete_exist_file:
                for f in exist_should_delete_files:
                    if progress_callback != None:
                        progress_callback(finished, total, 0, 0, "delete", str(f.abspath.relative_to(self.__remote)))
                    self.__fe.rmtree(f)
                    finished += 1
            for f in need_upload_files:
                def upload_progress_callback(sub_p, sub_t):
                    if progress_callback != None:
                        progress_callback(finished, total, sub_p, sub_t, "upload", str(f.abspath.relative_to(self.__remote)))
                if f.type == FileEntityType.DIRECTORY:
                    self.__fe.mkdirs(f)
                    continue # dir not count
                else:
                    try:
                        self.__upload_file(self.get_local_path(f), f, compile, arch, progress_callback=upload_progress_callback)
                    except:
                        key = key = convert_to_pathstr(f)
                        del new_file_record[key]
                        print("================")
                        traceback.print_exc()
                        print('========> Upload Error:', key)
                finished += 1
            # write record
            self.__fe.upload(self.__record_file_path, json.dumps(new_file_record).encode("utf-8"))
        finally:
            if need_close:
                self.__fe.close()
            self.__fe._release_device()
    
    def build(self, compile=False, arch=None, ignore_hidden=True, target_folder:PathLike=".build", progress_callback:SyncProgressCallback=None):
        local_files = set(self.__walk_local_like_remote(ignore_hidden))
        target_folder = syspath.abspath(target_folder)
        if syspath.exists(target_folder):
            rmtree(target_folder)
        makedirs(target_folder)
        new_file_record = {}
        for f in local_files:
            print(f)
            # base info
            localpath = self.get_local_path(f)
            target = syspath.join(target_folder, PurePath(localpath).relative_to(self.__local))
            folder = syspath.dirname(target)
            if f.type == FileEntityType.DIRECTORY:
                if not syspath.exists(folder):
                    makedirs(folder)
                continue
            if progress_callback != None:
                progress_callback(0, 0, 0, 0, "build", str(f.abspath.relative_to(self.__remote)))
            # calc hash
            hash = self.__hash_local_file(f, compile)
            key = convert_to_pathstr(f)
            new_file_record[key] = hash
            # build
            if not syspath.exists(folder):
                makedirs(folder)
            if compile and self.should_compile(f):
                data = get_compiled_file_content(localpath, arch=arch)
                target = PATTERN_PY.sub(".mpy", target)
            else:
                with open(localpath, 'rb') as f:
                    data = f.read()
            with open(target, 'wb') as f:
                f.write(data)
        # write hash record
        localpath = self.get_local_path(self.__record_file_path)
        target = syspath.join(target_folder, PurePath(localpath).relative_to(self.__local))
        folder = syspath.dirname(target)
        if not syspath.exists(folder):
            makedirs(folder)
        with open(target, "wb") as f:
            f.write(json.dumps(new_file_record).encode("utf-8"))
