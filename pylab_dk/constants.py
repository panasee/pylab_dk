#!/usr/bin/env python
import re
import sys
from datetime import datetime
from functools import wraps
from typing import Literal, Generator

import numpy as np
import pylab_dk.pltconfig.color_preset as colors

# define constants
cm_to_inch = 0.3937
hplanck = 6.626 * 10 ** (-34)
hbar = hplanck / 2 / np.pi
hbar_thz = hbar * 10 ** 12
kb = 1.38 * 10 ** (-23)
unit_factor_fromSI = {"": 1, "f": 1E15, "p": 1E12, "n": 1E9, "u": 1E6, "m": 1E3, "k": 1E-3, "M": 1E-6, "G": 1E-9,
                      "T": 1E-12,
                      "P": 1E-15}
unit_factor_toSI = {"": 1, "f": 1E-15, "p": 1E-12, "n": 1E-9, "u": 1E-6, "m": 1E-3, "k": 1E3, "M": 1E6, "G": 1E9,
                    "T": 1E12,
                    "P": 1E15}

#define plotting default settings
default_plot_dict = {"color": colors.Genshin["Nilou"][0], "linewidth": 1, "linestyle": "-", "marker": "o",
                     "markersize": 1.5, "markerfacecolor": "None", "markeredgecolor": "black", "markeredgewidth": 0.3,
                     "label": "", "alpha": 0.77}

switch_dict = {"on": True, "off": False, "ON": True, "OFF": False}


def factor(unit: str, mode: str = "from_SI"):
    """
    Transform the SI unit to targeted unit or in the reverse order.

    Args:
    unit: str
        The unit to be transformed.
    mode: str
        The direction of the transformation. "from_SI" means transforming from SI unit to the targeted unit, and "to_SI" means transforming from the targeted unit to SI unit.
    """
    # add judgement for the length to avoid m (meter) T (tesla) to be recognized as milli
    if len(unit) <= 1:
        return 1
    if mode == "from_SI":
        if unit[0] in unit_factor_fromSI:
            return unit_factor_fromSI.get(unit[0])
        else:
            return 1
    if mode == "to_SI":
        if unit[0] in unit_factor_toSI:
            return unit_factor_toSI.get(unit[0])
        else:
            return 1


def is_notebook() -> bool:
    """
    judge if the code is running in a notebook environment.
    """
    if 'ipykernel' in sys.modules and 'IPython' in sys.modules:
        try:
            from IPython import get_ipython
            if 'IPKernelApp' in get_ipython().config:
                return True
        except:
            pass
    return False


def split_no_str(s: str | int | float) -> tuple[float | None, str | None]:
    """
    split the string into the string part and the float part.

    Args:
        s (str): the string to split

    Returns:
        tuple[float,str]: the string part and the integer part
    """
    if isinstance(s, (int, float)):
        return s, ""
    match = re.match(r"([+-]?[0-9.]+)([a-zA-Z]*)", s, re.I)

    if match:
        items = match.groups()
        return float(items[0]), items[1]
    else:
        return None, None


def convert_unit(before: float | int | str | list[float | int | str, ...] | tuple[float | int | str, ...] | np.ndarray,
                 target_unit: str = "") -> tuple[float, str] | tuple[list[float], list[str]]:
    """
    Convert the value with the unit to the SI unit.

    Args:
        before (float | str): the value with the unit
        target_unit (str): the target unit

    Returns:
        tuple[float, str]: the value in the target unit and the whole str with final unit
    """
    if isinstance(before, (int, float, str)):
        value, unit = split_no_str(before)
        value_SI = value * factor(unit, mode="to_SI")
        new_value = value_SI * factor(target_unit, mode="from_SI")
        return new_value, f"{new_value}{target_unit}"
    elif isinstance(before, (np.int64, np.float64)):
        return convert_unit(float(before), target_unit)
    elif isinstance(before, (list, tuple, np.ndarray)):
        return [convert_unit(i, target_unit)[0] for i in before], [convert_unit(i, target_unit)[1] for i in before]


def print_progress_bar(iteration: float, total: float, prefix='', suffix='', decimals=1, length=50, fill='#',
                       print_end="\r") -> None:
    """
    Call in a loop to create terminal progress bar

    Args:
        iteration (float): current iteration
        total (float): total iterations
        prefix (str): prefix string
        suffix (str): suffix string
        decimals (int): positive number of decimals in percent complete
        length (int): character length of bar
        fill (str): bar fill character
        print_end (str): end character (e.g. "\r", "\r\n")
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    barr = fill * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} [{barr}] {percent}% {suffix}', end=print_end, flush=True)
    # Print New Line on Complete
    if iteration == total:
        print()


def gen_seq(start, end, step):
    """
    double-ended bi-direction sequence generator
    """
    if step == 0:
        raise ValueError("step should not be zero")
    if step * (end - start) < 0:
        step *= -1
    value = start
    while (value - end) * step < 0:
        yield value
        value += step
    yield end


def handle_keyboard_interrupt(func):
    """##TODO: to add cleanup, now not used"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            print("KeyboardInterrupt caught. Cleaning up...")
            # Perform any necessary cleanup here
            return None

    return wrapper


def constant_generator(value, repeat: int | Literal["inf"] = "inf"):
    """
    generate a constant value infinitely
    """
    if repeat == "inf":
        while True:
            yield value
    else:
        idx = 0
        while idx < repeat:
            idx += 1
            yield value


def time_generator(format_str: str = "%Y-%m-%d_%H:%M:%S"):
    """
    generate current time always

    Args:
        format_str (str): the format of the time
    """
    while True:
        yield datetime.now().strftime(format_str)


def combined_generator_list(lst_gens: list[Generator]):
    """
    combine a list of generators into one generator generating a whole list
    """
    while True:
        try:
            list_ini = [next(i) for i in lst_gens]
            list_fin = []
            for i in list_ini:
                if isinstance(i, list | tuple):
                    list_fin.extend(i)
                else:
                    list_fin.append(i)
            yield list_fin
        except StopIteration:
            break


def rename_duplicates(columns: list[str]) -> list[str]:
    """
    rename the duplicates with numbers (like ["V","V"] to ["V1","V2"])
    """
    count_dict = {}
    renamed_columns = []
    for col in columns:
        if col in count_dict:
            count_dict[col] += 1
            renamed_columns.append(f"{col}{count_dict[col]}")
        else:
            count_dict[col] = 1
            renamed_columns.append(col)
    return renamed_columns


def hex_to_rgb(hex_str: str, fractional: bool = True) -> tuple[int, ...] | tuple[float, ...]:
    """
    convert hex color to rgb color

    Args:
        hex_str (str): hex color
        fractional (bool): if the return value is fractional or not
    """
    hex_str = hex_str.lstrip('#')
    if fractional:
        return tuple(int(hex_str[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))


if "__name__" == "__main__":
    if is_notebook():
        print("This is a notebook")
    else:
        print("This is not a notebook")
