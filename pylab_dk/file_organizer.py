#!/usr/bin/env python

"""
This file contains the functions to organize the files in the directory.
This file should be called when create new files or directories 
"""
import os
import platform
from functools import wraps
from pathlib import Path
import json
import datetime
from typing import Literal
from itertools import islice
import shutil
import re
from pylab_dk import LOCAL_DB_PATH, OUT_DB_PATH, set_paths


def print_help_if_needed(func: callable) -> callable:
    """decorator used to print the help message if the first argument is '-h'"""

    @wraps(func)
    def wrapper(self, measure_mods: tuple[str], *var_tuple, **kwargs):
        if var_tuple[0] == "-h":
            print(FileOrganizer.name_fstr_gen(*measure_mods)[-1])
            return None
        return func(self, measure_mods, *var_tuple, **kwargs)

    return wrapper


class FileOrganizer:
    """A class to manage file and directory operations."""

    # the None value is only to avoid the error when the class is imported
    # the value must be set before the class is used
    # in all methods and properties, they are assumed to be SET and not None
    _local_database_dir = Path(LOCAL_DB_PATH) if LOCAL_DB_PATH is not None else None
    _out_database_dir = Path(OUT_DB_PATH) if OUT_DB_PATH is not None else None
    _trash_dir = _out_database_dir / "trash" if _out_database_dir is not None else None

    # load the json files to dicts for storing important records information note that the dicts are static variables
    # created with the definition of the class and shared by all instances of the class and keep changing
    # default to None to avoid the error when the class is imported, also for judging whether is the first instance
    # they are a must part for the class to work
    measure_types_json: dict = None
    """the changes should ALWAYS be synced RIGHT AFTER EVERY CHANGE"""
    proj_rec_json: dict = None
    """the changes should ALWAYS be synced RIGHT AFTER EVERY CHANGE"""
    # the third party related configs are optional
    third_party_json: dict = None
    """used for specific reason, like wafers, positions, etc."""
    third_party_location: Literal["local", "out"] = None
    """used to indicate the location of the third party json file"""
    third_party_name: str = None
    """used to indicate the name of the third party json file"""

    @staticmethod
    def reload_paths(*, local_db_path: str | Path = None, out_db_path: str | Path = None) -> None:
        """reload the paths from the environment variables"""
        set_paths(local_db_path=local_db_path, out_db_path=out_db_path)
        FileOrganizer._local_database_dir = Path(LOCAL_DB_PATH) if LOCAL_DB_PATH is not None else None
        FileOrganizer._out_database_dir = Path(OUT_DB_PATH) if OUT_DB_PATH is not None else None
        FileOrganizer._trash_dir = FileOrganizer._out_database_dir / "trash" if FileOrganizer._out_database_dir is not None else None

    def __init__(self, proj_name: str, copy_from: str = None) -> None:
        """
        initialize the class with the project name and judge if the name is in the accepted project names. Only
        out_database_path is required, as the local_database_dir is attached with the base_dir

        Args:
            proj_name: str
                The name of the project, used as the name of the base directory
        """
        #  store the data directly in the local_database_dir
        if platform.system().lower() == "windows":
            self.curr_sys = "win"
        elif platform.system().lower() == "linux":
            self.curr_sys = "linux"

        # prevent further operation if the local_database_dir or out_database_dir have not been set
        if FileOrganizer._local_database_dir is None or FileOrganizer._out_database_dir is None:
            raise ValueError("The database_dir(s) have not been set, please appoint a path first.")
        # defined vars for two databases of the project
        self._out_database_dir_proj = FileOrganizer._out_database_dir / proj_name
        self.proj_name = proj_name
        self.today = datetime.date.today()

        # only load the measure_types_json once, then it will be shared by all instances
        # so that the changes will be synced among instances to avoid conflicts
        if FileOrganizer.measure_types_json is None:
            with open(FileOrganizer._local_database_dir / "measure_types.json", "r",
                      encoding="utf-8") as __measure_type_file:
                FileOrganizer.measure_types_json = json.load(__measure_type_file)

        # initialize the out database directory
        # judge if is the first instance by proj_rec_json
        if FileOrganizer.proj_rec_json is None:
            FileOrganizer._out_database_dir.mkdir(parents=True, exist_ok=True)
            FileOrganizer._trash_dir.mkdir(exist_ok=True)
            if not (FileOrganizer._out_database_dir / "project_record.json").exists():
                with open(FileOrganizer._out_database_dir / "project_record.json", "w",
                          encoding="utf-8") as __proj_rec_file:
                    json.dump({}, __proj_rec_file)
            with open(FileOrganizer._out_database_dir / "project_record.json", "r",
                      encoding="utf-8") as __proj_rec_file:
                FileOrganizer.proj_rec_json = json.load(__proj_rec_file)

        # try to find the project in the record file, if not, then add a new item in record
        if proj_name not in FileOrganizer.proj_rec_json and copy_from is None:
            FileOrganizer.proj_rec_json[proj_name] = {
                "created_date": self.today.strftime("%Y-%m-%d"),
                "last_modified": self.today.strftime("%Y-%m-%d"),
                "measurements": [],
                "plan": {}}
            print(f"{proj_name} is not found in the project record file, a new item has been added.")
            # not dump the json file here, but in the sync method, to avoid the file being dumped multiple times
        elif proj_name not in FileOrganizer.proj_rec_json and copy_from is not None:
            if copy_from not in FileOrganizer.proj_rec_json:
                print(f"{copy_from} is not found in the project record file, please check the name.")
                return
            FileOrganizer.proj_rec_json[proj_name] = FileOrganizer.proj_rec_json[copy_from].copy()
            FileOrganizer.proj_rec_json[proj_name]["created_date"] = self.today.strftime("%Y-%m-%d")
            FileOrganizer.proj_rec_json[proj_name]["last_modified"] = self.today.strftime("%Y-%m-%d")
            print(f"{proj_name} has been copied from {copy_from}.")

        # create project folder in the out database for storing main data
        self._out_database_dir_proj.mkdir(exist_ok=True)
        if os.path.exists(FileOrganizer._local_database_dir / "assist.ipynb"):
            if not os.path.exists(self._out_database_dir_proj / "assist_post.ipynb"):
                shutil.copy(FileOrganizer._local_database_dir / "assist.ipynb",
                            self._out_database_dir_proj / "assist_post.ipynb")
            if not os.path.exists(self._out_database_dir_proj / "assist_measure.ipynb"):
                shutil.copy(FileOrganizer._local_database_dir / "assist.ipynb",
                            self._out_database_dir_proj / "assist_measure.ipynb")
        else:
            print(f"assist.ipynb not found @ {FileOrganizer._local_database_dir}, nothing copied to proj")
        # sync the project record file at the end of the function
        FileOrganizer._sync_json("proj_rec")

    def open_proj_folder(self) -> None:
        """Open the project folder"""
        FileOrganizer.open_folder(self._out_database_dir_proj)

    def get_filepath(self, measure_mods: tuple[str] | list[str], *var_tuple,
                     tmpfolder: str = None, plot: bool = False) -> Path:
        """
        Get the filepath of the measurement file.

        Args:
            measure_mods: tuple[str]
                modules used in the measurement, e.g. ("I_source_ac","V_sense","T_sweep")
            var_tuple: Tuple[int, str, float]
                a tuple containing all parameters for the measurement
            tmpfolder: str
                The name of the temperature/temporary folder, default is None
            plot: bool
                Whether the file is a plot file, default is False
        """
        measure_name, name_fstr = FileOrganizer.name_fstr_gen(*measure_mods)

        try:
            filename = FileOrganizer.filename_format(name_fstr, *var_tuple)

            if tmpfolder is not None:
                filepath = self._out_database_dir_proj / measure_name / tmpfolder / filename
                if plot:
                    filepath = self._out_database_dir_proj / "plot" / measure_name / tmpfolder / filename
            else:
                filepath = self._out_database_dir_proj / measure_name / filename
                if plot:
                    filepath = self._out_database_dir_proj / "plot" / measure_name / filename
            return filepath

        except Exception:
            print("Wrong parameters, please ensure the parameters are correct.")
            print(name_fstr)

    # TODO: delete after confirming not needed

    #    @staticmethod
    #    def measurename_decom(measure_mods: str) -> tuple[str]:
    #        """this method will decompose the measurename string into a tuple of measurename and submeasurename(None if
    #        not exist)"""
    #        measure_name_list = measure_mods.split("__")
    #        if len(measure_name_list) > 2:
    #            raise ValueError("The measurename string is not in the correct format, please check.")
    #        if_sub = (len(measure_name_list) == 2)
    #        measure_name = measure_name_list[0]
    #        measure_sub = measure_name_list[1] if if_sub else None
    #        return (measure_name, measure_sub)

    @staticmethod
    def name_fstr_gen(*params: str, require_detail: bool = False) \
            -> tuple[str, str] | tuple[str, str, list[dict]] | tuple[str, str, list[dict], list[list[str]]]:
        """
        Generate the measurename f-string from the used variables, different modules' name strs are separated by "_",
        while separator inside the name str is "-"

        Args:
            params: Tuple[str] e.g. "I_source-fixed-ac","V_sense","T-sweep"
                The variables used in the measurename string should be
                ["source", "sense"](if "source")_["fixed","sweep"]-["ac","dc"] for I,V,
                and ["fixed", "sweep"] for T,B
                both "-" and "_" are allowed as separators
            require_detail: bool
                Whether to return the mods_detail_dicts_lst, default is False
        Returns:
            Tuple[str, str]: The mainname_str and the namestr
            or
            Tuple[str, str, list[dict]]: The mainname_str, the namestr and the mods_detail_dicts_lst
            mainname_str: str "sources-senses-others"
            mods_detail_dicts_lst: list[dict["ac_dc","sweep_fix","source_sense"]]
        """
        source_dict = {"mainname": [], "indexes": [], "namestr": []}
        sense_dict = {"mainname": [], "indexes": [], "namestr": []}
        other_dict = {"mainname": [], "indexes": [], "namestr": []}
        # assign a dict for EACH module, note the order
        mods_detail_dicts_lst = [{"sweep_fix": None, "ac_dc": None, "source_sense": None} for i in range(len(params))]
        for i, var in enumerate(params):
            var_list = re.split(r"[_-]", var)
            if len(var_list) == 2:
                var_main, var_sub = var_list
                namestr = FileOrganizer.measure_types_json[f'{var_main}'][f"{var_sub}"]
            elif len(var_list) == 4:
                var_main, var_sub, var_sweep, var_ac_dc = var_list
                namestr = FileOrganizer.measure_types_json[f'{var_main}'][f"{var_sub}"][f"{var_sweep}"][f"{var_ac_dc}"]
            elif len(var_list) == 3:
                var_main, var_sub, var_ac_dc = var_list
                namestr = FileOrganizer.measure_types_json[f'{var_main}'][f"{var_sub}"][f"{var_ac_dc}"]
            else:
                raise ValueError("The variable name is not in the correct format, please check if the separator is _")

            if var_sub == "source":
                source_dict["mainname"].append(var_main)
                source_dict["indexes"].append(i)
                source_dict["namestr"].append(namestr)
            elif var_sub == "sense":
                sense_dict["mainname"].append(var_main)
                sense_dict["indexes"].append(i)
                sense_dict["namestr"].append(namestr)
            else:
                other_dict["mainname"].append(var_main)
                other_dict["indexes"].append(i)
                other_dict["namestr"].append(namestr)

            for var_i in var_list:
                if var_i in ["ac", "dc"]:
                    mods_detail_dicts_lst[i]["ac_dc"] = var_i
                elif var_i in ["sweep", "fixed", "vary"]:
                    mods_detail_dicts_lst[i]["sweep_fix"] = var_i
                elif var_i in ["source", "sense"]:
                    mods_detail_dicts_lst[i]["source_sense"] = var_i

        mainname_str = "".join(source_dict["mainname"]) + "-" + "".join(sense_dict["mainname"]) + "-" + "".join(
            other_dict["mainname"])
        mods_detail_dicts_lst = [mods_detail_dicts_lst[i] for i in
                                 source_dict["indexes"] + sense_dict["indexes"] + other_dict["indexes"]]
        namestr = "-".join(source_dict["namestr"]) + "_" + "-".join(sense_dict["namestr"]) + "_" + "-".join(
            other_dict["namestr"])
        namestr = namestr.strip("_")
        if require_detail:
            return mainname_str, namestr, mods_detail_dicts_lst
        else:
            return mainname_str, namestr

    @staticmethod
    def filename_format(name_str: str, *var_tuple) -> str:
        """This method is used to format the filename"""
        for value in var_tuple:
            name_str = re.sub(r"{\w+}", str(value), name_str, count=1)
        # the method needs to throw an error if there are still {} in the name_str
        if re.search(r"{\w+}", name_str):
            raise ValueError("The name_str still contains {}, please check the variables.")
        return name_str

    #TODO: delete after confirming not needed

    #    @staticmethod
    #    def query_namestr(measure_mod: str) ->  None:
    #        """
    #        This method is for querying the naming string of a certain measure type
    #        measure_mod: str e.g. "I_source_ac"
    #            The name of the measure module
    #        """
    #        if measure_mod in FileOrganizer.measure_types_json:
    #            if isinstance(FileOrganizer.measure_types_json[measure_mod], str):
    #                var_names = re.findall(r'{(\w+)}', FileOrganizer.measure_types_json[measure_name])
    #                print(FileOrganizer.measure_types_json[measure_name])
    #                print(var_names)
    #                return None
    #            elif isinstance(FileOrganizer.measure_types_json[measure_name], dict):
    #                for key, value in FileOrganizer.measure_types_json[measure_name].items():
    #                    var_names = re.findall(r'{(\w+)}', value)
    #                    print(f"{key}: {value}")
    #                    print(var_names)
    #                return None
    #        else:
    #            print("measure type not found, please add it first")
    #            return None

    @staticmethod
    def open_folder(path: str | Path) -> None:
        """
        Open the Windows explorer to the given path
        For non-win systems, print the path
        """
        if platform.system().lower() == "windows":
            os.system(f"start explorer {path}")
        else:
            print(f"Use terminal: {path}")

    @staticmethod
    def _sync_json(which_file: str) -> None:
        """
        sync the json dictionary with the file, should av
oid using this method directly, as the content of json may be uncontrolable

        Args:
            which_file: str
                The file to be synced with, should be either "measure_type" or "proj_rec"
        """
        if which_file == "measure_type":
            with open(FileOrganizer._local_database_dir / "measure_types.json", "w",
                      encoding="utf-8") as __measure_type_file:
                json.dump(FileOrganizer.measure_types_json, __measure_type_file, indent=4)
        elif which_file == "proj_rec":
            with open(FileOrganizer._out_database_dir / "project_record.json", "w",
                      encoding="utf-8") as __proj_rec_file:
                json.dump(FileOrganizer.proj_rec_json, __proj_rec_file, indent=4)
        elif isinstance(which_file, str):
            if FileOrganizer.third_party_location == "local":
                with open(FileOrganizer._local_database_dir / f"{which_file}.json", "w",
                          encoding="utf-8") as __third_party_file:
                    json.dump(FileOrganizer.third_party_json, __third_party_file, indent=4)
            elif FileOrganizer.third_party_location == "out":
                with open(FileOrganizer._out_database_dir / f"{which_file}.json", "w",
                          encoding="utf-8") as __third_party_file:
                    json.dump(FileOrganizer.third_party_json, __third_party_file, indent=4)
        else:
            raise TypeError("The file name should be str.")

    def create_folder(self, folder_name: str) -> None:
        """
        create a folder in the project folder

        Args:
            folder_name: str
                The name(relative path if not in the root folder) of the folder to be created
        """
        (self._out_database_dir_proj / folder_name).mkdir(exist_ok=True)

    def add_measurement(self, *measure_mods) -> None:
        """
        Add a measurement to the project record file.

        Args:
            measure_mods: Tuple[str]
                The modules used in the measurement, e.g. "I_source_ac","V_sense","T_sweep"
        """
        measurename_main, name_str = FileOrganizer.name_fstr_gen(*measure_mods)
        # first add it into the project record file
        if measurename_main in FileOrganizer.proj_rec_json[self.proj_name]["measurements"]:
            print(f"{measurename_main} is already in the project record file.")
            return
        FileOrganizer.proj_rec_json[self.proj_name]["measurements"].append(measurename_main)
        FileOrganizer.proj_rec_json[self.proj_name]["last_modified"] = self.today.strftime("%Y-%m-%d")
        print(f"{measurename_main} has been added to the project record file.")

        # add the measurement folder if not exists
        self.create_folder(measurename_main)
        print(f"{measurename_main} folder has been created in the project folder.")
        # sync the project record file
        FileOrganizer._sync_json("proj_rec")

    def add_plan(self, plan_title: str, plan_item: str) -> None:
        """
        Add/Supplement a plan_item to the project record file. If the plan_title is already in the project record file, then supplement the plan_item to the plan_title, otherwise add a new plan_title with the plan_item. (each plan_item contains a list)

        Args:
            plan_title: str
                The title of the plan_item to be added
            plan_item: str
                The content of the plan
        """
        if plan_title in FileOrganizer.proj_rec_json[self.proj_name]["plan"]:
            if plan_item not in FileOrganizer.proj_rec_json[self.proj_name]["plan"][plan_title]:
                FileOrganizer.proj_rec_json[self.proj_name]["plan"][plan_title].append(plan_item)
                print(f"plan is added to {plan_title}")
            else:
                print(f"{plan_item} is already in the plan.")
        else:
            FileOrganizer.proj_rec_json[self.proj_name]["plan"][plan_title] = [plan_item]
            print(f"{plan_title} has been added to the project record file.")
        # sync the measure type file
        FileOrganizer._sync_json("proj_rec")

    @staticmethod
    def add_measurement_type(measure_mods: str, name_str: str, overwrite: bool = False) -> None:
        """
        Add a new measurement type to the measure type file.

        Args:
            measure_mods: str
                The name(whole with subcat) of the measurement type to be added
                Example: "I_source_ac" or "V_sense" or "T_sweep"
            name_str: str
                The name string of the naming rules in this measurement type, use dict when there are many subtypes in the measurement type
                Example:  "Max{maxi}A-step{stepi}A-freq{freq}Hz-{iin}-{iout}"
            overwrite: bool
                Whether to overwrite the existing measurement type, default is False
        """

        def deepest_check_add(higher_dict: dict, deepest_sub: str,
                              name_strr: str, if_overwrite: bool,
                              already_strr: str, added_strr: str) -> None:
            if not isinstance(higher_dict, dict):
                raise TypeError("The deepest sub is not a dictionary, please check.\n"
                                + "Usually because the depth is not consistent")
            if deepest_sub in higher_dict and not if_overwrite:
                print(f"{already_strr}{higher_dict[deepest_sub]}")
            elif deepest_sub not in higher_dict:
                higher_dict[deepest_sub] = name_strr
                print(added_strr)
            else:  # in and overwrite
                if isinstance(higher_dict[deepest_sub], str):
                    higher_dict[deepest_sub] = name_strr
                    print(f"{deepest_sub} has been overwritten.")
                else:
                    raise TypeError("The deepest sub is not a string, please check.\n"
                                    + "Usually because the depth is not consistent")

        already_str = f"{measure_mods} is already in the measure type file: "
        added_str = f"{measure_mods} has been added to the measure type file."
        measure_decom = re.split(r"[_-]", measure_mods)

        if len(measure_decom) == 2:
            measure_name, measure_sub = measure_decom
            if measure_name in FileOrganizer.measure_types_json:
                deepest_check_add(FileOrganizer.measure_types_json[measure_name], measure_sub,
                                  name_str, overwrite, already_str, added_str)
            else:
                FileOrganizer.measure_types_json[measure_name] = {measure_sub: name_str}
                print(added_str)

        elif len(measure_decom) == 3:
            measure_name, measure_sub, measure_sub_sub = measure_decom
            if measure_name in FileOrganizer.measure_types_json:
                if measure_sub in FileOrganizer.measure_types_json[measure_name]:
                    deepest_check_add(FileOrganizer.measure_types_json[measure_name][measure_sub], measure_sub_sub,
                                      name_str, overwrite, already_str, added_str)
                else:
                    FileOrganizer.measure_types_json[measure_name][measure_sub] = {measure_sub_sub: name_str}
                    print(added_str)
            else:
                FileOrganizer.measure_types_json[measure_name] = {measure_sub: {measure_sub_sub: name_str}}
                print(added_str)

        elif len(measure_decom) == 4:
            measure_name, measure_sub, measure_sub_sub, measure_sub_sub_sub = measure_decom
            if measure_name in FileOrganizer.measure_types_json:
                if measure_sub in FileOrganizer.measure_types_json[measure_name]:
                    if measure_sub_sub in FileOrganizer.measure_types_json[measure_name][measure_sub]:
                        deepest_check_add(FileOrganizer.measure_types_json[measure_name][measure_sub][measure_sub_sub],
                                          measure_sub_sub_sub, name_str, overwrite, already_str, added_str)
                    else:
                        FileOrganizer.measure_types_json[measure_name][measure_sub][measure_sub_sub] = {
                            measure_sub_sub_sub: name_str}
                        print(added_str)
                else:
                    FileOrganizer.measure_types_json[measure_name][measure_sub] = {measure_sub_sub: name_str}
                    print(added_str)
            else:
                FileOrganizer.measure_types_json[measure_name] = {measure_sub: {measure_sub_sub: name_str}}
                print(added_str)

        else:
            raise ValueError("The measure_mods is not in the correct format, please check, \
                             only 1 or 2 sub-type depth are allowed, separated by _")

        # sync the measure type file
        FileOrganizer._sync_json("measure_type")

    def query_proj(self) -> dict:
        """
        Query the project record file to find the project.
        """
        return FileOrganizer.proj_rec_json[self.proj_name]

    @staticmethod
    def query_proj_all() -> dict:
        """
        Query the project record file to find all the projects.
        """
        return FileOrganizer.proj_rec_json

    @staticmethod
    def del_proj(proj_name: str) -> None:
        """To delete a project from the project record file."""
        del FileOrganizer.proj_rec_json[proj_name]
        FileOrganizer._sync_json("proj_rec")
        #move the project folder to the trash bin
        shutil.move(FileOrganizer._out_database_dir / proj_name, FileOrganizer._trash_dir / proj_name)
        print(f"{proj_name} has been moved to the trash bin.")

    def tree(self, level: int = -1, limit_to_directories: bool = True, length_limit: int = 300):
        """
        Given a directory Path object print a visual tree structure
        Cited from: https://stackoverflow.com/questions/9727673/list-directory-tree-structure-in-python
        """
        # prefix components:
        space = '    '
        branch = '│   '
        # pointers:
        tee = '├── '
        last = '└── '

        dir_path = self._out_database_dir_proj
        files = 0
        directories = 0

        def inner(dir_path: Path, prefix: str = '', level=-1):
            nonlocal files, directories
            if not level:
                return  # 0, stop iterating
            if limit_to_directories:
                contents = [d for d in dir_path.iterdir() if d.is_dir()]
            else:
                contents = list(dir_path.iterdir())
            pointers = [tee] * (len(contents) - 1) + [last]
            for pointer, path in zip(pointers, contents):
                if path.is_dir():
                    yield prefix + pointer + path.name
                    directories += 1
                    extension = branch if pointer == tee else space
                    yield from inner(path, prefix=prefix + extension, level=level - 1)
                elif not limit_to_directories:
                    yield prefix + pointer + path.name
                    files += 1

        print(dir_path.name)
        iterator = inner(dir_path, level=level)
        for line in islice(iterator, length_limit):
            print(line)
        if next(iterator, None):
            print(f'... length_limit, {length_limit}, reached, counted:')
        print(f'\n{directories} directories' + (f', {files} files' if files else ''))

    @staticmethod
    def load_third_party(third_party_name: str, location: Literal["local","out"] = "out",
                         overwrite: bool = False) -> Path | None:
        """
        Load the third party json file to the third_party_json variable
        if overwrite is True, then the existing third party json will be overwritten WITHOUT SAVING
        """
        if (FileOrganizer.third_party_json is not None
                and FileOrganizer.third_party_location is not None
                and not overwrite):
            print(f"already loaded one third party json @{FileOrganizer.third_party_location}, could choose overwrite.")
            return
        if location == "local":
            file_path = FileOrganizer._local_database_dir / f"{third_party_name}.json"
            FileOrganizer.third_party_location = "local"
        elif location == "out":
            file_path = FileOrganizer._out_database_dir / f"{third_party_name}.json"
            FileOrganizer.third_party_location = "out"
        else:
            raise ValueError("The location should be either 'local' or 'out'.")

        FileOrganizer.third_party_name = third_party_name
        if not file_path.exists():
            # create a new file with the name
            with open(file_path, "w", encoding="utf-8") as __third_party_file:
                json.dump({}, __third_party_file)
        with open(file_path, "r", encoding="utf-8") as __third_party_file:
            FileOrganizer.third_party_json = json.load(__third_party_file)

        return file_path
