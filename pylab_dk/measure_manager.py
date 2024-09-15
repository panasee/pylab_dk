#!/usr/bin/env python

##TODO: still under reconstruction, not ready for use
"""This module is responsible for managing the measure-related folders and data Note each instrument better be
initialzed right before the measurement, as there may be a long time between loading and measuremnt, leading to
possibilities of parameter changing"""
from __future__ import annotations

import copy
from typing import Literal, Generator
import time
import datetime
import gc
import numpy as np
import pyvisa
import pandas as pd
from pathlib import Path
import re
# import qcodes as qc
from pylab_dk.drivers.MercuryiPS_VISA import OxfordMercuryiPS
from pylab_dk.file_organizer import print_help_if_needed, FileOrganizer
from pylab_dk.data_plot import DataPlot
from pylab_dk.constants import convert_unit, print_progress_bar, gen_seq, constant_generator, \
    combined_generator_list
from pylab_dk.equip_wrapper import ITC, ITCs, ITCMercury, WrapperSR830, Wrapper2400, Wrapper6430, Wrapper2182, \
    Wrapper6221, Meter, SourceMeter


class MeasureManager(DataPlot):
    """This class is a subclass of FileOrganizer and is responsible for managing the measure-related folders and data
    During the measurement, the data will be recorded in self.dfs["curr_measure"], which will be overwritten after
    """

    def __init__(self, proj_name: str) -> None:
        """Note that the FileOrganizer.out_database_init method should be called to assign the correct path to the
        out_database attribute. This method should be called before the MeasureManager object is created."""
        super().__init__(proj_name)  # Call the constructor of the parent class
        self.meter_wrapper_dict = {
            "6430": Wrapper6430,
            "2182": Wrapper2182,
            "2400": Wrapper2400,
            "6221": Wrapper6221,
            "sr830": WrapperSR830
        }
        self.instrs = {}
        # load params for plotting in measurement
        DataPlot.load_settings(False, False)

    def load_meter(self, meter_no: Literal["sr830", "6221", "2182", "2400", "6430"], *address: str) -> None:
        """
        load the instrument according to the address, store it in self.instrs[meter]

        Args:
            meter_no (str): the name of the instrument
            address (str): the address of the instrument
        """
        # some meters can not be loaded twice, so del old one first
        if meter_no in self.instrs:
            del self.instrs["meter_no"]
            gc.collect()

        self.instrs[meter_no] = []
        for addr in address:
            self.instrs[meter_no].append(self.meter_wrapper_dict[meter_no](address))
            self.instrs[meter_no][-1].setup()

    def load_ITC503(self, gpib_up: str, gpib_down: str) -> None:
        """
        load ITC503 instruments according to the addresses, store them in self.instrs["itc503"] in corresponding order. Also store the ITC503 instruments in self.instrs["itc"] for convenience to call

        Args:
            addresses (list[str]): the addresses of the ITC503 instruments (take care of the order)
        """
        self.instrs["itc503"] = ITCs(gpib_up, gpib_down)
        self.instrs["itc"] = self.instrs["itc503"]

    def load_mercury_ips(self, address: str = "TCPIP0::10.97.24.237::7020::SOCKET", if_print: bool = False,
                         limit_sphere: float = 11) -> None:
        """
        load Mercury iPS instrument according to the address, store it in self.instrs["ips"]

        Args:
            address (str): the address of the instrument
            if_print (bool): whether to print the snapshot of the instrument
            limit_sphere (float): the limit of the field
        """
        self.instrs["ips"] = OxfordMercuryiPS("mips", address)
        if if_print:
            self.instrs["ips"].print_readable_snapshot(update=True)

        def spherical_limit(x, y, z) -> bool:
            return np.sqrt(x ** 2 + y ** 2 + z ** 2) <= limit_sphere

        self.instrs["ips"].set_new_field_limits(spherical_limit)

    def ramp_magfield(self, field: float | tuple[float], *, rate: tuple[float] = (0.00333,) * 3, wait: bool = True,
                      tolerance: float = 3e-3, if_plot: bool = False) -> None:
        """
        ramp the magnetic field to the target value with the rate, current the field is only in Z direction limited by the actual instrument setting
        (currently only B_z can be ramped)

        Args:
            field (tuple[float]): the target field coor
            rate (float): the rate of the field change (T/s)
            wait (bool): whether to wait for the ramping to finish
            tolerance (float): the tolerance of the field (T)
        """
        mips = self.instrs["ips"]
        if max(rate) * 60 > 0.2:
            raise ValueError("The rate is too high, the maximum rate is 0.2 T/min")
        #mips.GRPX.field_ramp_rate(rate[0])
        #mips.GRPY.field_ramp_rate(rate[1])
        mips.GRPZ.field_ramp_rate(rate[2])
        # no x and y field for now
        #mips.x_target(field[0])
        #mips.y_target(field[1])
        if isinstance(field, (tuple, list)):
            mips.z_target(field[2])
        if isinstance(field, (float, int)):
            mips.z_target(field)

        mips.ramp(mode="simul")
        if wait:
            # the is_ramping() method is not working properly, so we use the following method to wait for the ramping
            # to finish
            if if_plot:
                self.live_plot_init(1, 1, 1, 600, 1400, titles=[["H ramping"]],
                                    axes_labels=[[[r"Time (s)", r"Field_norm (T)"]]])
            time_arr = [0]
            field_arr = [np.linalg.norm((mips.x_measured(), mips.y_measured(), mips.z_measured()))]
            count = 0
            step_count = 1
            stability_counter = 13  # [s]
            while count < stability_counter:
                field_now = (mips.x_measured(), mips.y_measured(), mips.z_measured())
                time_arr.append(step_count)
                field_arr.append(np.linalg.norm(field_now))
                if abs(np.linalg.norm(field_now) - np.linalg.norm(field)) < tolerance:
                    count += 1
                else:
                    count = 0
                print_progress_bar(count, stability_counter, prefix="Stablizing",
                                   suffix=f"B: {field_now} T")
                time.sleep(1)
                if if_plot:
                    self.live_plot_update(0, 0, 0, time_arr, field_arr)
                step_count += 1
            print("ramping finished")

    def load_mercury_itc(self, address: str = "TCPIP0::10.101.28.24::7020::SOCKET") -> None:
        """
        load Mercury iPS instrument according to the address, store it in self.instrs["ips"]
        """
        #self.instrs["mercury_itc"] = MercuryITC(address)
        self.instrs["mercury_itc"] = ITCMercury(address)
        self.instrs["itc"] = self.instrs["mercury_itc"]
        #print(self.instrs["mercury_itc"].modules)

    def source_sweep_apply(self, source_type: Literal["volt", "curr", "V", "I"], ac_dc: Literal["ac", "dc"],
                           meter: str | SourceMeter, *, max_value: float | str, step_value: float | str,
                           compliance: float | str,
                           freq: float | str = None, sweepmode: Literal["0-max-0", "0--max-max-0", None] = None,
                           resistor: float = None) -> Generator[float, None, None]:
        """
        source the current using the source meter

        Args:
            source_type (Literal["volt","curr"]): the type of the source
            ac_dc (Literal["ac","dc"]): the mode of the current
            meter (Literal["6430","6221"]): the meter to be used, use "-0", "-1" to specify the meter if necessary
            max_value (float): the maximum current to be sourced
            step_value (float): the step of the current
            compliance (float): the compliance voltage of the source meter
            freq (float): the frequency of the ac current
            sweepmode (Literal["0-max-0","0--max-max-0"]): the mode of the dc current sweep
            resistor (float): the resistance of the resistor, used only for sr830 source
        """
        # load the instrument needed
        source_type = source_type.replace("V", "volt").replace("I", "curr")
        if meter == "6221" and source_type == "volt":
            raise ValueError("6221 cannot source voltage")
        if len(meter.split("-")) == 1:
            instr = self.instrs[meter][0]
        elif len(meter_tuple := meter.split("-")) == 2:
            instr = self.instrs[meter_tuple[0]][int(meter_tuple[1])]
        elif isinstance(meter, SourceMeter):
            instr = meter
        else:
            raise ValueError("meter name not recognized")

        # convert values to SI and print info
        max_value = convert_unit(max_value, "")[0]
        step_value = convert_unit(step_value, "")[0]
        compliance = convert_unit(compliance, "")[0]
        if freq is not None:
            freq = convert_unit(freq, "Hz")[0]
        print(f"Source Meter: {instr.meter}")
        print(f"Source Type: {source_type}")
        print(f"AC/DC: {ac_dc}")
        print(f"Max Value: {max_value} {'A' if source_type == 'curr' else 'V'}")
        print(f"Step Value: {step_value} {'A' if source_type == 'curr' else 'V'}")
        print(f"Compliance: {compliance} {'V' if source_type == 'curr' else 'A'}")
        print(f"Freq: {freq} Hz")
        print(f"Sweep Mode: {sweepmode}")
        instr.setup()

        # core functional part
        if ac_dc == "dc":
            if sweepmode == "0-max-0":
                value_gen = self.sweep_values(0, max_value, step_value, mode="start-end-start")
            elif sweepmode == "0--max-max-0":
                value_gen = self.sweep_values(-max_value, max_value, step_value, mode="0-start-end-0")
            else:
                raise ValueError("sweepmode not recognized")
            instr.uni_output(value_i := next(value_gen), compliance=compliance, type_str=source_type)
            yield value_i
        elif ac_dc == "ac":
            if resistor is not None:
                volt_gen = (i for i in list(np.arange(0, max_value * resistor, step_value)) + [max_value * resistor])
                instr.uni_output(value_i := next(volt_gen), freq=freq, type_str="volt")
            else:
                if meter == "6221" or isinstance(meter, Wrapper6221):
                    instr.setup("ac")
                value_gen = (i for i in list(np.arange(0, max_value, step_value)) + [max_value])
                instr.uni_output(value_i := next(value_gen), freq=freq, compliance=compliance, type_str=source_type)
            yield value_i

    def ext_sweep_apply(self, ext_type: Literal["temp", "mag", "B", "T"], *,
                        min_value: float | str = None, max_value: float | str, step_value: float | str,
                        sweepmode: Literal["0-max-0", "0--max-max-0", "min-max"] = "0-max-0") -> Generator[
        float, None, None]:
        """
        sweep the external field (magnetic/temperature).
        Note that this sweep is the "discrete" sweep, waiting at every point till stabilization

        Args:
            ext_type (Literal["temp","mag"]): the type of the external field
            min_value (float | str): the minimum value of the field
            max_value (float | str): the maximum value of the field
            step_value (float | str): the step of the field
            sweepmode (Literal["0-max-0","0--max-max-0","min-max"]): the mode of the field sweep
        """
        ext_type = ext_type.replace("T", "temp").replace("B", "mag")
        if ext_type == "temp":
            instr = self.instrs["itc"]
        elif ext_type == "mag":
            instr = self.instrs["ips"]
        else:
            raise ValueError("ext_type not recognized")
        print(f"DISCRETE sweeping mode: {sweepmode}")
        print(f"INSTR: {instr}")
        max_value = convert_unit(max_value, "")[0]
        step_value = convert_unit(step_value, "")[0]
        if min_value is not None:
            min_value = convert_unit(min_value, "")[0]

        if sweepmode == "0-max-0":
            value_gen = self.sweep_values(0, max_value, step_value, mode="start-end-start")
        elif sweepmode == "0--max-max-0":
            value_gen = self.sweep_values(-max_value, max_value, step_value, mode="0-start-end-0")
        elif sweepmode == "min-max":
            value_gen = self.sweep_values(min_value, max_value, step_value, mode="start-end")
        else:
            raise ValueError("sweepmode not recognized")

        if ext_type == "temp":
            instr.ramp_to_temperature(value_i := next(value_gen), wait=True)
        else:  # ext_type == "mag"
            self.ramp_magfield(value_i := next(value_gen), wait=True)
        yield value_i

    def sense_apply(self, sense_type: Literal["volt", "curr", "temp", "mag", "V", "I", "T", "B", "H"],
                    meter: str | Meter = None, *, if_during_vary=False) \
            -> Generator[float | tuple[float], None, None]:
        """
        sense the current using the source meter

        Args:
            sense_type (Literal["volt","curr", "temp","mag"]): the type of the sense
            meter ("str") (applicable only for volt or curr): the meter to be used, use "-0", "-1" to specify the meter if necessary
            if_during_vary (bool): whether the sense is bonded with a varying temp/field, this will limit the generator,
                and the sense will be stopped when the temp/field is stable
        Returns:
            float | tuple[float]: the sensed value (tuple for sr830 ac sense)
        """
        sense_type = sense_type.replace("V", "volt").replace("I", "curr").replace("T", "temp").replace("B",
                                                                                                       "mag").replace(
            "H", "mag")
        print(f"Sense Type: {sense_type}")
        if sense_type in ["volt", "curr"] and meter is not None:
            if len(meter.split("-")) == 1:
                instr = self.instrs[meter][0]
            elif len(meter_tuple := meter.split("-")) == 2:
                instr = self.instrs[meter_tuple[0]][int(meter_tuple[1])]
            elif isinstance(meter, Meter):
                instr = meter
            else:
                raise ValueError("meter name not recognized")
            print(f"Sense Meter/Instr: {instr.meter}")
            instr.setup()
            while True:
                yield instr.sense(type_str=sense_type)
        elif sense_type == "temp":
            instr = self.instrs["itc"]
            print(f"Sense Meter/Instr: {instr}")
            if not if_during_vary:
                while True:
                    yield instr.temperature
            else:
                timer_i = 0
                while timer_i < 20:
                    if abs(instr.temperature - instr.temperature_set) < 0.1:
                        timer_i += 1
                    else:
                        timer_i = 0
                    yield instr.temperature
        elif sense_type == "mag":
            instr = self.instrs["ips"]
            print(f"Sense Meter/Instr: {instr}")
            if not if_during_vary:
                while True:
                    yield np.linalg.norm((instr.x_measured(), instr.y_measured(), instr.z_measured()))
            else:
                timer_i = 0
                while timer_i < 20:
                    # only z field is considered
                    if abs(np.linalg.norm(
                            (instr.x_measured(), instr.y_measured(), instr.z_measured())) - np.linalg.norm(
                            instr.z_target())) < 0.01:
                        timer_i += 1
                    else:
                        timer_i = 0
                    yield np.linalg.norm((instr.x_measured(), instr.y_measured(), instr.z_measured()))

    def record_init(self, measure_mods: tuple[str], *var_tuple: float | str,
                    manual_columns: list[str] = None, return_df: bool = False) \
            -> tuple[Path, int] | tuple[Path, int, pd.DataFrame]:
        """
        initialize the record of the measurement

        Args:
            measure_mods (str): the full name of the measurement (put main source as the first source module term)
            var_tuple (tuple): the variables of the measurement, use "-h" to see the available options
            manual_columns (list[str]): manually appoint the columns (default to None, automatically generate columns)
            return_df (bool): if the final record dataframe will be returned (default not, and saved as a member)
        Returns:
            Path: the file path
            int: the number of columns of the record
        """
        # main_mods, f_str = self.name_fstr_gen(*measure_mods)
        file_path = self.get_filepath(measure_mods, *var_tuple)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self.add_measurement(*measure_mods)
        print(f"Filename is: {file_path.name}")

        mainname_str, _, mod_detail_lst = FileOrganizer.name_fstr_gen(*measure_mods, require_detail=True)
        # IMPORTANT: judge ac_dc ONLY from the first module, and if ac, then lock-in sensor is assumed
        ac_dc = mod_detail_lst[0]["ac_dc"]
        # combine the namestr
        pure_name_lst = list(mainname_str.replace("-", "").replace("_", ""))
        if len(pure_name_lst) != len(mod_detail_lst):
            raise ValueError("length of modules doesn't correspond to detail list, check name_fstr_gen method for that")

        if manual_columns is not None:
            columns_lst = manual_columns
        else:
            columns_lst = ["time"]
            for name, detail in zip(list(pure_name_lst), mod_detail_lst):
                if detail["source_sense"] == "source":
                    columns_lst.append(f"{name}_source")
                elif name == "V" and ac_dc == "ac":
                    columns_lst += ["X", "Y", "R", "Theta"]
                else:
                    columns_lst.append(name)

            # rename the duplicates with numbers (like ["V","V"] to ["V1","V2"])
            def rename_duplicates(columns: list[str]) -> list[str]:
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

            columns_lst = rename_duplicates(columns_lst)

        self.dfs["curr_measure"] = pd.DataFrame(columns=columns_lst)
        self.dfs["curr_measure"].to_csv(file_path, sep="\t", index=False, float_format="%.12f")
        if return_df:
            return file_path, len(columns_lst), self.dfs["curr_measure"]
        return file_path, len(columns_lst)

    def record_update(self, file_path: Path, record_num: int, record_tuple: tuple[float],
                      force_write: bool = False, with_time: bool = True) -> None:
        """
        update the record of the measurement and also control the size of dataframe
        when the length of current_measure dataframe is larger than 7,
        the dataframe will be written to the file INCREMENTALLY and reset to EMPTY

        Args:
            file_path (Path): the file path
            record_num (int): the number of columns of the record
            record_tuple (tuple): the variables of the record
            force_write (bool): whether to force write the record
            with_time (bool): whether to record the time (first column)
        """
        if with_time:
            # the time is updated here, no need to be provided
            assert len(record_tuple) == record_num - 1, "The number of columns does not match"
            self.dfs["curr_measure"].loc[len(self.dfs["curr_measure"])] = [datetime.datetime.now()] + list(record_tuple)
        else:
            assert len(record_tuple) == record_num, "The number of columns does not match"
            self.dfs["curr_measure"].loc[len(self.dfs["curr_measure"])] = list(record_tuple)
        length = len(self.dfs["curr_measure"])
        if length >= 7 or force_write:
            self.dfs["curr_measure"].to_csv(file_path, sep="\t", mode="a",
                                            header=False, index=False, float_format="%.12f")
            self.dfs["curr_measure"] = self.dfs["curr_measure"].iloc[0:0]

    @print_help_if_needed
    def get_measure_dict(self, measure_mods: tuple[str], *var_tuple: float | str,
                         wrapper_lst: list[Meter | SourceMeter] = None,
                         compliance_lst: list[float | str], sr830_current_resistor: float = None) -> dict:
        """
        do the preset of measurements and return the generators, filepath and related info
        NOTE: meter setup should be done before calling this method
        NOTE: the generators are listed in parallel, if there are more than one sweep, do manual Cartesian product

        sweep mode: for I,V: "0-max-0", "0--max-max-0"
        sweep mode: for T,B: "0-max-0", "0--max-max-0", "min-max"

        Args:
            measure_mods (tuple[str]): the modules of measurement
            var_tuple (tuple): the variables of the measurement, use "-h" to see the variables' list
            wrapper_lst (list[Meter]): the list of the wrappers to be used
            compliance_lst (list[float]): the list of the compliance to be used (sources)
            sr830_current_resistor (float): the resistance of the resistor, used only for sr830 curr source

        Returns:
            dict: a dictionary containing the list of generators, dataframe csv filepath and record number
                keys: "gen_lst"(combined list generator), "swp_idx" (indexes for sweeping generator, not including vary),
                "file_path"(csv file), "record_num"(num of record data columns, without time),
                "tmp_vary", "mag_vary" (the function used to begin the varying of T/B, no parameters needed)
        """
        src_lst, sense_lst, oth_lst = self.extract_info_mods(measure_mods, *var_tuple)
        assert len(src_lst) + len(sense_lst) == len(wrapper_lst), "The number of modules and meters should be the same"
        assert len(src_lst) == len(compliance_lst), "The number of sources and compliance should be the same"
        # init record dataframe
        file_path, record_num = self.record_init(measure_mods, *var_tuple)
        # init plotly canvas
        rec_lst = []  # generators list

        # =============assemble the record generators into one list==============
        # note multiple sweeps result in multidimensional mapping
        sweep_idx = []
        vary_mod = []  # T, B
        # source part
        for idx, src_mod in enumerate(src_lst):
            if src_mod["I"]["sweep_fix"] is not None:
                mod_i = "I"
            elif src_mod["V"]["sweep_fix"] is not None:
                mod_i = "V"
            else:
                raise ValueError(f"No source is specified for source {idx}")

            if src_mod[mod_i]["sweep_fix"] == "fixed":
                wrapper_lst[idx].ramp_output("curr", src_mod[mod_i]["fix"], compliance=compliance_lst[idx])
                rec_lst.append(constant_generator(src_mod[mod_i]["fix"]))
            elif src_mod[mod_i]["sweep_fix"] == "sweep":
                rec_lst.append(self.source_sweep_apply(mod_i, src_mod[mod_i]["ac_dc"], wrapper_lst[idx],
                                                       max_value=src_mod[mod_i]["max"],
                                                       step_value=src_mod[mod_i]["step"],
                                                       compliance=compliance_lst[idx], freq=src_mod[mod_i]["freq"],
                                                       sweepmode=src_mod[mod_i]["mode"],
                                                       resistor=sr830_current_resistor))
                sweep_idx.append(idx)
        # sense part
        for idx, sense_mod in enumerate(sense_lst):
            rec_lst.append(self.sense_apply(sense_mod["type"], wrapper_lst[idx + len(src_lst)]))
        # others part
        for idx, oth_mod in enumerate(oth_lst):
            if oth_mod["sweep_fix"] == "fixed":
                if oth_mod["name"] == "T":
                    self.instrs["itc"].ramp_to_temperature(oth_mod["fix"], wait=True)
                elif oth_mod["name"] == "B":
                    self.ramp_magfield(oth_mod["fix"], wait=True)
                rec_lst.append(self.sense_apply(oth_mod["name"]))
            elif oth_mod["sweep_fix"] == "vary":
                if oth_mod["name"] == "T":
                    vary_mod.append("T")
                    self.instrs["itc"].ramp_to_temperature(oth_mod["start"], wait=True)

                    # define a function instead of directly calling the ramp_to_temperature method
                    # to avoid possible interruption or delay
                    def temp_vary():
                        self.instrs["itc"].ramp_to_temperature(oth_mod["stop"], wait=False)
                elif oth_mod["name"] == "B":
                    vary_mod.append("B")
                    self.ramp_magfield(oth_mod["start"], wait=True)

                    def mag_vary():
                        self.ramp_magfield(oth_mod["stop"], wait=False)
                rec_lst.append(self.sense_apply(oth_mod["name"], if_during_vary=True))
            elif oth_mod["sweep_fix"] == "sweep":
                rec_lst.append(self.ext_sweep_apply(oth_mod["name"], min_value=oth_mod["min"], max_value=oth_mod["max"],
                                                    step_value=oth_mod["step"], sweepmode=oth_mod["mode"]))
                sweep_idx.append(idx + len(src_lst) + len(sense_lst))
        total_gen = combined_generator_list(rec_lst)
        return {
            "gen_lst": total_gen,
            "swp_idx": sweep_idx,
            "file_path": file_path,
            "record_num": record_num,
            "tmp_vary": None if "T" not in vary_mod else temp_vary,
            "mag_vary": None if "B" not in vary_mod else mag_vary,
        }

##TODO: wait to remove ##

#    def measure_IV_2terminal(self, v_max: float = 1E-4, v_step: float = 1E-5, curr_compliance: float = 1E-6,
#                             mode: Literal["0-max-0", "0--max-max-0"] = "0-max-0", *,
#                             meter_name=Literal["2400", "6430"], test: bool = True,
#                             source: int = None, drain: int = None, temp: int = None, tmpfolder: str = None) -> None:
#        """
#        Measure the IV curve using Keithley 6430 to test the contacts. No file will be saved if test is True
#        """
#        measure_delay = 0.3  # [s]
#        instr = self.instrs[meter_name][0]
#        if v_max > 200:
#            raise ValueError("The maximum voltage is too high")
#        #tmp_df = pd.DataFrame(columns=["V","V_sensed", "I", "R"])
#        tmp_df = pd.DataFrame(columns=["V", "I"])
#        self.live_plot_init(1, 1, 1, 600, 1400, titles=[["IV 6430"]], axes_labels=[[[r"Voltage (V)", r"Current (A)"]]])
#
#        if mode == "0-max-0":
#            v_array = list(MeasureManager.sweep_values(0, v_max, v_step, "start-end-start"))
#        elif mode == "0--max-max-0":
#            v_array = list(MeasureManager.sweep_values(-v_max, v_max, v_step, "0-start-end-0"))
#        else:
#            raise ValueError("Mode not recognized")
#        tmp_df["V"] = v_array
#        i_array = np.zeros_like(v_array)
#
#        try:
#            for ii, v in enumerate(v_array):
#                instr.uni_output(v, compliance=curr_compliance, type_str="volt")
#                time.sleep(measure_delay)
#                i_array[ii] = instr.sense(type_str="curr")
#                self.live_plot_update(0, 0, 0, tmp_df["V"][:ii + 1], i_array[:ii + 1])
#
#            tmp_df["I"] = i_array
#        except KeyboardInterrupt:
#            print("Measurement interrupted")
#        finally:
#            instr.output_enabled(False)
#            if not test:
#                file_path = self.get_filepath("IV__2-terminal", v_max, v_step, source, drain, mode, temp,
#                                              tmpfolder=tmpfolder)
#                file_path.parent.mkdir(parents=True, exist_ok=True)
#                tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#
#    @print_help_if_needed
#    def measure_VB_SR830(self, measure_mods: tuple[str], *var_tuple: float | str, source: Literal["sr830", "6221"],
#                         resistor: float = None) -> None:
#        """
#        measure voltage signal of constant current under different temperature (continuously changing).
#
#        Args:
#            measure_mods (str): the full name of the measurement
#            var_tuple (tuple): the variables of the measurement, use "-h" to see the available options
#            source (Literal["sr830","6221"]): the source of the measurement
#            resistor (float): the resistance of the resistor, used only for sr830 source to calculate the voltage
#        """
#        file_path = self.get_filepath(measure_mods, *var_tuple)
#        file_path.parent.mkdir(parents=True, exist_ok=True)
#        self.add_measurement(*measure_mods)
#        sub_type = FileOrganizer.measurename_decom(measure_mods)[-1]
#        fast = False
#        if var_tuple[2] < 2:
#            raise ValueError("npts should be no less than 2")
#        elif var_tuple[2] == 2:
#            fast = True
#        curr = convert_unit(var_tuple[3], "A")[0]
#        print(f"Filename is: {file_path.name}")
#        print(f"Curr: {curr} A")
#        print(f"Mag: {var_tuple[0]} -> {var_tuple[1]} T")
#        print(f"steps: {var_tuple[2] - 1}")
#        print(f"fast mode: {fast}")
#        # for two types of measurements, the V1 meter is the same as the 2w meter,
#        # and the V2 meter is the same as the 1w meter
#        # so the variable name will not be changed for 2pair measurement
#        self.print_pairs(sub_type, 0, 1)
#        B_arr = np.linspace(var_tuple[0], var_tuple[1], var_tuple[2])
#        freq = var_tuple[4]
#        tmp_df = pd.DataFrame(columns=["B", "X_2w", "Y_2w", "R_2w", "phi_2w", "X_1w", "Y_1w", "R_1w", "phi_1w", "T"])
#        out_range = False
#
#        meter_2w = self.instrs['sr830'][0]
#        meter_1w = self.instrs['sr830'][1]
#        meter_2w.harmonic = 2
#        meter_1w.harmonic = 1
#
#        if "1pair" in sub_type.split("-"):
#            meter_2w.harmonic = 2
#            meter_1w.harmonic = 1
#            self.live_plot_init(3, 2, 2, 600, 1400,
#                                titles=[["2w", "phi"], ["1w", "phi"], ["T", ""]],
#                                axes_labels=[[["B (T)", "V2w (V)"], ["B (T)", "phi"]],
#                                             [["B (T)", "V1w (V)"], ["B (T)", "phi"]],
#                                             [["t", "B (T)"], ["", ""]]],
#                                line_labels=[[["X", "Y"], ["", ""]],
#                                             [["X", "Y"], ["", ""]],
#                                             [["", ""], ["", ""]]])
#        elif "2pair" in sub_type.split("-"):
#            self.live_plot_init(3, 2, 2, 600, 1400,
#                                titles=[["V1", "phi"], ["V1", "phi"], ["T", ""]],
#                                axes_labels=[[["B (T)", "V1 (V)"], ["B (T)", "phi"]],
#                                             [["B (T)", "V2 (V)"], ["B (T)", "phi"]],
#                                             [["t", "B (T)"], ["", ""]]],
#                                line_labels=[[["X", "Y"], ["", ""]],
#                                             [["X", "Y"], ["", ""]],
#                                             [["", ""], ["", ""]]])
#        if source == "sr830":
#            meter_1w.reference_source_trigger = "POS EDGE"
#            meter_2w.reference_source_trigger = "SINE"
#            meter_2w.reference_source = "Internal"
#            meter_2w.frequency = freq
#            if resistor is None:
#                raise ValueError("resistor is needed for sr830 source")
#        elif source == "6221":
#            # 6221 use half peak-to-peak voltage as amplitude
#            curr_p2p = curr * np.sqrt(2)
#            source_6221 = self.instrs["6221"]
#            self.setup_6221()
#            source_6221.source_compliance = curr_p2p * 1000  # compliance voltage
#            source_6221.source_range = curr_p2p / 0.6
#            print(f"Keithley 6221 source range is set to {curr_p2p / 0.6} A")
#            source_6221.waveform_frequency = freq
#            meter_1w.reference_source_trigger = "POS EDGE"
#            meter_2w.reference_source_trigger = "POS EDGE"
#        try:
#            if source == "sr830":
#                for i in np.arange(0, curr * resistor, 0.02):
#                    meter_2w.sine_voltage = i
#                    time.sleep(0.5)
#                meter_2w.sine_voltage = curr * resistor
#            elif source == "6221":
#                source_6221.waveform_abort()
#                source_6221.waveform_amplitude = curr_p2p
#                source_6221.waveform_arm()
#                source_6221.waveform_start()
#
#            time_arr = []
#            if not fast:
#                for i, b_i in enumerate(B_arr):
#                    self.ramp_magfield(b_i, wait=True)
#                    if meter_1w.is_out_of_range():
#                        out_range = True
#                    elif meter_2w.is_out_of_range():
#                        out_range = True
#                    list_2w = meter_2w.snap("X", "Y", "R", "THETA")
#                    list_1w = meter_1w.snap("X", "Y", "R", "THETA")
#                    temp = self.instrs["itc"].temperature
#                    list_tot = [b_i] + list_2w + list_1w + [temp]
#                    print(f"B: {list_tot[0]:.4f} T\t 2w: {list_tot[1:5]}\t 1w: {list_tot[5:9]}\t T: {list_tot[-1]}")
#                    tmp_df.loc[len(tmp_df)] = list_tot
#                    time_arr.append(datetime.datetime.now())
#                    self.live_plot_update([0, 0, 0, 1, 1, 1, 2],
#                                          [0, 0, 1, 0, 0, 1, 0],
#                                          [0, 1, 0, 0, 1, 0, 0],
#                                          [tmp_df["B"]] * 6 + [time_arr],
#                                          np.array(tmp_df[["X_2w", "Y_2w", "phi_2w", "X_1w", "Y_1w", "phi_1w", "T"]]).T)
#                    if i % 3 == 0:
#                        tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            if fast:
#                i = 0
#                counter = 0
#                #self.ramp_magfield(B_arr[0], wait=True)
#                self.ramp_magfield(B_arr[1], wait=False)
#                while counter < 300:
#                    i += 1
#                    if meter_1w.is_out_of_range():
#                        out_range = True
#                    elif meter_2w.is_out_of_range():
#                        out_range = True
#                    list_2w = meter_2w.snap("X", "Y", "R", "THETA")
#                    list_1w = meter_1w.snap("X", "Y", "R", "THETA")
#                    temp = self.instrs["itc"].temperature
#                    B_now_z = self.instrs["ips"].z_measured()
#                    list_tot = [B_now_z] + list_2w + list_1w + [temp]
#                    time_arr.append(datetime.datetime.now())
#                    print(f"B: {list_tot[0]:.4f} T\t 2w: {list_tot[1:5]}\t 1w: {list_tot[5:9]}\t T: {list_tot[-1]}")
#                    tmp_df.loc[len(tmp_df)] = list_tot
#                    self.live_plot_update([0, 0, 0, 1, 1, 1, 2],
#                                          [0, 0, 1, 0, 0, 1, 0],
#                                          [0, 1, 0, 0, 1, 0, 0],
#                                          [tmp_df["B"]] * 6 + [time_arr],
#                                          np.array(tmp_df[["X_2w", "Y_2w", "phi_2w", "X_1w", "Y_1w", "phi_1w", "T"]]).T)
#                    if i % 7 == 0:
#                        tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#                    time.sleep(1)
#
#                    if abs(self.instrs["ips"].z_measured() - var_tuple[1]) < 0.003:
#                        counter += 1
#                    else:
#                        counter = 0
#            self.dfs["VB"] = tmp_df.copy()
#            # rename the columns for compatibility with the plotting function
#            self.set_unit({"I": "uA", "V": "uV"})
#            #self.df_plot_nonlinear(handlers=(ax[1],phi[1],ax[0],phi[0]))
#            if out_range:
#                print("out-range happened, rerun")
#        except KeyboardInterrupt:
#            print("Measurement interrupted")
#        finally:
#            tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            if source == "sr830":
#                meter_2w.sine_voltage = 0
#            if source == "6221":
#                source_6221.shutdown()
#
#    @print_help_if_needed
#    def measure_VT_SR830(self, measurename_all, *var_tuple, source: Literal["sr830", "6221"], resistor: float = None,
#                         stability_counter: int = 120, thermalize_counter: int = 120, ramp_rate: float = 5) -> None:
#        """
#        measure voltage signal of constant current under different temperature (continuously changing).
#        NOTE: set npts to 2 to do fast ramping.
#        The normal ramping record data at every temperature point after it's been stablized and thermalized, while the fast ramping record according to time on the way
#
#        Args:
#            measurename_all (str): the full name of the measurement
#            var_tuple (tuple): the variables of the measurement, use "-h" to see the available options
#            source (Literal["sr830","6221"]): the source of the measurement
#            resistor (float): the resistance of the resistor, used only for sr830 source to calculate the voltage
#            stability_counter (int, [s]): the counter for the stability of the temperature
#            thermalize_counter (int, [s]): the counter for the thermalization of the temperature
#            ramp_rate (float, [K/min]): the rate of the temperature ramping
#        """
#        sub_type = FileOrganizer.measurename_decom(measurename_all)[-1]
#        fast = False
#        if var_tuple[2] < 2:
#            raise ValueError("npts should be no less than 2")
#        elif var_tuple[2] == 2:
#            fast = True
#        file_path = self.get_filepath(measurename_all, *var_tuple)
#        file_path.parent.mkdir(parents=True, exist_ok=True)
#        self.add_measurement(measurename_all)
#        curr = convert_unit(var_tuple[3], "A")[0]
#        print(f"Filename is: {file_path.name}")
#        print(f"Curr: {curr} A")
#        print(f"Temperature: {var_tuple[0]} -> {var_tuple[1]} K")
#        print(f"steps: {var_tuple[2] - 1}")
#        print(f"fast mode: {fast}")
#        # for two types of measurements, the V1 meter is the same as the 2w meter,
#        # and the V2 meter is the same as the 1w meter
#        # so the variable name will not be changed for 2pair measurement
#        if "1pair" in sub_type.split("-"):
#            print(f"2w meter: {self.instrs['sr830'][0].adapter}")
#            print(f"1w meter: {self.instrs['sr830'][1].adapter}")
#        elif "2pair" in sub_type.split("-"):
#            print("===========================================")
#            print(f"V1 meter: {self.instrs['sr830'][0].adapter}\t ORDER: {self.instrs['sr830'][0].harmonic}")
#            print(f"V2 meter: {self.instrs['sr830'][1].adapter}\t ORDER: {self.instrs['sr830'][1].harmonic}")
#            print("===========================================")
#        T_arr = np.linspace(var_tuple[0], var_tuple[1], var_tuple[2])
#        freq = var_tuple[4]
#        tmp_df = pd.DataFrame(columns=["T", "X_2w", "Y_2w", "R_2w", "phi_2w", "X_1w", "Y_1w", "R_1w", "phi_1w", "curr"])
#        out_range = False
#
#        self.setup_SR830()
#        meter_2w = self.instrs['sr830'][0]
#        meter_1w = self.instrs['sr830'][1]
#        if "1pair" in sub_type.split("-"):
#            meter_2w.harmonic = 2
#            meter_1w.harmonic = 1
#            self.live_plot_init(3, 2, 2, 600, 1400,
#                                titles=[["2w", "phi"], ["1w", "phi"], ["T", ""]],
#                                axes_labels=[[["T (K)", "V2w (V)"], ["T (K)", "phi"]],
#                                             [["T (K)", "V1w (V)"], ["T (K)", "phi"]],
#                                             [["t(min)", "T (K)"], ["", ""]]],
#                                line_labels=[[["X", "Y"], ["", ""]],
#                                             [["X", "Y"], ["", ""]],
#                                             [["", ""], ["", ""]]])
#        elif "2pair" in sub_type.split("-"):
#            self.live_plot_init(3, 2, 2, 600, 1400,
#                                titles=[["V1", "phi"], ["V1", "phi"], ["T", ""]],
#                                axes_labels=[[["T (K)", "V1 (V)"], ["T (K)", "phi"]],
#                                             [["T (K)", "V2 (V)"], ["T (K)", "phi"]],
#                                             [["t(min)", "T (K)"], ["", ""]]],
#                                line_labels=[[["X", "Y"], ["", ""]],
#                                             [["X", "Y"], ["", ""]],
#                                             [["", ""], ["", ""]]])
#        if source == "sr830":
#            meter_1w.reference_source_trigger = "POS EDGE"
#            meter_2w.reference_source_trigger = "SINE"
#            meter_2w.reference_source = "Internal"
#            meter_2w.frequency = freq
#            if resistor is None:
#                raise ValueError("resistor is needed for sr830 source")
#        elif source == "6221":
#            # 6221 use half peak-to-peak voltage as amplitude
#            curr_p2p = curr * np.sqrt(2)
#            source_6221 = self.instrs["6221"]
#            self.setup_6221()
#            source_6221.source_compliance = curr_p2p * 10000  # compliance voltage
#            source_6221.source_range = curr_p2p / 0.6
#            print(f"Keithley 6221 source range is set to {curr_p2p / 0.6} A")
#            source_6221.waveform_frequency = freq
#            meter_1w.reference_source_trigger = "POS EDGE"
#            meter_2w.reference_source_trigger = "POS EDGE"
#        try:
#            if source == "sr830":
#                for i in np.arange(0, curr * resistor, 0.02):
#                    meter_2w.sine_voltage = i
#                    time.sleep(0.39)
#                meter_2w.sine_voltage = curr * resistor
#            elif source == "6221":
#                source_6221.waveform_abort()
#                source_6221.waveform_amplitude = curr_p2p
#                source_6221.waveform_arm()
#                source_6221.waveform_start()
#
#            time_arr = []
#            if not fast:
#                for i, temp_i in enumerate(T_arr):
#                    self.instrs["itc"].ramp_to_temperature(temp_i, ramp_rate=ramp_rate,
#                                                           stability_counter=stability_counter,
#                                                           thermalize_counter=thermalize_counter)
#                    if meter_1w.is_out_of_range():
#                        out_range = True
#                    elif meter_2w.is_out_of_range():
#                        out_range = True
#                    list_2w = meter_2w.snap("X", "Y", "R", "THETA")
#                    list_1w = meter_1w.snap("X", "Y", "R", "THETA")
#                    temp = self.instrs["itc"].temperature
#                    list_tot = [temp] + list_2w + list_1w + [curr]
#                    if "1pair" in sub_type.split("-"):
#                        print(f"T: {list_tot[0]:.2f} K\t 2w: {list_tot[1:5]}\t 1w: {list_tot[5:9]}")
#                    elif sub_type.split("-")[-1] == "2pair":
#                        print(f"T: {list_tot[0]:.2f} K\t V1: {list_tot[1:5]}\t V2: {list_tot[5:9]}")
#                    tmp_df.loc[len(tmp_df)] = list_tot
#                    time_arr.append(datetime.datetime.now())
#                    self.live_plot_update([0, 0, 0, 1, 1, 1, 2],
#                                          [0, 0, 1, 0, 0, 1, 0],
#                                          [0, 1, 0, 0, 1, 0, 0],
#                                          [tmp_df["T"]] * 6 + [time_arr],
#                                          np.array(tmp_df[["X_2w", "Y_2w", "phi_2w", "X_1w", "Y_1w", "phi_1w", "T"]]).T)
#                    if i % 3 == 0:
#                        tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            if fast:
#                i = 0
#                counter = 0
#                self.instrs["itc"].ramp_to_temperature(var_tuple[0], ramp_rate=ramp_rate, wait=True,
#                                                       stability_counter=stability_counter,
#                                                       thermalize_counter=thermalize_counter)
#                self.instrs["itc"].ramp_to_temperature(var_tuple[1], ramp_rate=ramp_rate, wait=False,
#                                                       stability_counter=stability_counter,
#                                                       thermalize_counter=thermalize_counter)
#                # assume 600s to end the RT curve
#                while counter < 600:
#                    i += 1
#                    if meter_1w.is_out_of_range():
#                        out_range = True
#                    elif meter_2w.is_out_of_range():
#                        out_range = True
#                    list_2w = meter_2w.snap("X", "Y", "R", "THETA")
#                    list_1w = meter_1w.snap("X", "Y", "R", "THETA")
#                    temp = self.instrs["itc"].temperature
#                    list_tot = [temp] + list_2w + list_1w + [curr]
#                    if "1pair" in sub_type.split("-"):
#                        print(f"T: {list_tot[0]:.2f} K\t 2w: {list_tot[1:5]}\t 1w: {list_tot[5:9]}")
#                    elif "2pair" in sub_type.split("-"):
#                        print(f"T: {list_tot[0]:.2f} K\t V1: {list_tot[1:5]}\t V2: {list_tot[5:9]}")
#                    tmp_df.loc[len(tmp_df)] = list_tot
#                    time_arr.append(datetime.datetime.now())
#                    self.live_plot_update([0, 0, 0, 1, 1, 1, 2],
#                                          [0, 0, 1, 0, 0, 1, 0],
#                                          [0, 1, 0, 0, 1, 0, 0],
#                                          [tmp_df["T"]] * 6 + [time_arr],
#                                          np.array(tmp_df[["X_2w", "Y_2w", "phi_2w", "X_1w", "Y_1w", "phi_1w", "T"]]).T)
#                    if i % 7 == 0:
#                        tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#                    time.sleep(1)
#
#                    if abs(temp - var_tuple[1]) < ITC.dynamic_delta(var_tuple[1], 0.01):
#                        counter += 1
#                    else:
#                        counter = 0
#            self.dfs["VT"] = tmp_df.copy()
#            # rename the columns for compatibility with the plotting function
#            self.rename_columns("VT", {"Y_2w": "V2w", "X_1w": "V1w"})
#            self.set_unit({"I": "uA", "V": "uV"})
#            #self.df_plot_nonlinear(handlers=(ax[1],phi[1],ax[0],phi[0]))
#            if out_range:
#                print("out-range happened, rerun")
#        except KeyboardInterrupt:
#            print("Measurement interrupted")
#        finally:
#            tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            if source == "sr830":
#                meter_2w.sine_voltage = 0
#            if source == "6221":
#                source_6221.shutdown()

    #@print_help_if_needed
    #def measure_RT_SR830_ITC503(self, measure_mods, *var_tuple, resist: float) -> None:
    #    """
    #    Measure the Resist-Temperature relation using SR830 as both meter and source and store the data in the corresponding file(meters need to be loaded before calling this function, and the first is the source)

    #    Args:
    #        measure_mods (str): the full name of the measurement
    #        var_tuple (tuple): the variables of the measurement, use "-h" to see the available options
    #        resist (float): the resistance of the resistor, used only to calculate corresponding voltage
    #    """
    #    file_path = self.get_filepath(measure_mods, *var_tuple)
    #    self.add_measurement(measure_mods)
    #    curr = convert_unit(var_tuple[0], "A")[0]
    #    print(f"Filename is: {file_path.name}")
    #    print(f"Curr: {curr} A")
    #    print(f"estimated T range: {var_tuple[7]}-{var_tuple[8]} K")
    #    measure_delay = 0.5  # [s]
    #    frequency = 51.637  # [Hz]
    #    volt = curr * resist  # [V]

    #    self.setup_SR830()
    #    itc = self.instrs["itc"]
    #    meter1 = self.instrs["sr830"][0]
    #    meter2 = self.instrs["sr830"][1]
    #    print("====================")
    #    print(f"The first meter is {meter1.adapter}")
    #    print(f"Measuring {meter1.harmonic}-order signal")
    #    print("====================")
    #    print(f"The second meter is {meter2.adapter}")
    #    print(f"Measuring {meter2.harmonic}-order signal")
    #    print("====================")

    #    # increase voltage 0.02V/s to the needed value
    #    print(f"increasing voltage to targeted value {volt} V")
    #    amp = np.arange(0, volt, 0.01)
    #    for v in amp:
    #        meter1.sine_voltage = v
    #        time.sleep(0.5)
    #    print("voltage reached, start measurement")

    #    self.live_plot_init(2, 2, 2, 1000, 600, titles=[["XY-T", "phi"], ["XY-T", "phi"]],
    #                        axes_labels=[[[r"T (K)", r"V (V)"], ["T (K)", "phi"]],
    #                                     [[r"T (K)", r"V (V)"], ["T (K)", "phi"]]],
    #                        line_labels=[[["X", "Y"], ["", ""]], [["X", "Y"], ["", ""]]])
    #    meter1.reference_source = "Internal"
    #    meter1.frequency = frequency
    #    tmp_df = pd.DataFrame(columns=["T", "X1", "Y1", "R1", "phi1", "X2", "Y2", "R2", "phi2"])
    #    try:
    #        count = 0
    #        while True:
    #            count += 1
    #            time.sleep(measure_delay)
    #            list1 = meter1.snap("X", "Y", "R", "THETA")
    #            list2 = meter2.snap("X", "Y", "R", "THETA")
    #            temp = [itc.temperature]
    #            list_tot = temp + list1 + list2
    #            tmp_df.loc[len(tmp_df)] = list_tot

    #            self.live_plot_update(0, 0, 0, tmp_df["T"], tmp_df["X1"])
    #            self.live_plot_update(0, 0, 1, tmp_df["T"], tmp_df["Y1"])
    #            self.live_plot_update(0, 1, 0, tmp_df["T"], tmp_df["phi1"])
    #            self.live_plot_update(1, 0, 0, tmp_df["T"], tmp_df["X2"])
    #            self.live_plot_update(1, 0, 1, tmp_df["T"], tmp_df["Y2"])
    #            self.live_plot_update(1, 1, 0, tmp_df["T"], tmp_df["phi2"])
    #            if count % 10 == 0:
    #                tmp_df.to_csv(file_path, sep="\t", index=False)
    #    except KeyboardInterrupt:
    #        print("Measurement interrupted")
    #    finally:
    #        tmp_df.to_csv(file_path, sep="\t", index=False)
    #        meter1.sine_voltage = 0

#    @print_help_if_needed
#    def measure_VI_2182(self, measurename_all, *var_tuple, tmpfolder: str = None, delay: int = 5,
#                        mode: Literal["0-max-0", "0--max-max-0"] = "0-max-0") -> None:
#        """
#        Measure the IV curve using Keithley 2182 to test the contacts. No file will be saved if test is True
#
#        Args:
#            measurename_all (str): the full name of the measurement
#            var_tuple (tuple): the variables of the measurement, use "-h" to see the available options
#            tmpfolder (str): the temporary folder to store the data
#        """
#        if var_tuple[-2] == "0-max-0" or var_tuple[-2] == "0--max-max-0":
#            mode = var_tuple[-2]
#        else:
#            var_tuple = list(var_tuple)
#            var_tuple.insert(-1, mode)
#        file_path = self.get_filepath(measurename_all, *var_tuple, tmpfolder=tmpfolder)
#        file_path.parent.mkdir(parents=True, exist_ok=True)
#        self.add_measurement(measurename_all)
#        curr = convert_unit(var_tuple[0], "A")[0]
#        print(f"Filename is: {file_path.name}")
#        print(f"Max Curr: {curr} A")
#        print(f"steps: {var_tuple[1] - 1}")
#        curr_arr = np.linspace(0, curr, var_tuple[1])
#        if mode == "0-max-0":
#            curr_arr = np.concatenate((curr_arr, curr_arr[::-1]))
#        elif mode == "0--max-max-0":
#            curr_arr = np.concatenate((-curr_arr, -curr_arr[::-1], curr_arr, curr_arr[::-1]))
#        measure_delay = delay  # [s]
#        tmp_df = pd.DataFrame(columns=["I", "V", "T"])
#        out_range = False
#
#        instr_2182 = self.instrs["2182"]
#        self.setup_2182()
#        self.live_plot_init(1, 2, 1, 600, 1400,
#                            titles=[["IV", "T"]],
#                            axes_labels=[[["I (A)", "V (V)"], ["t", "T"]]],
#                            line_labels=[[["", ""], ["", ""]]])
#
#        source_6221 = self.instrs["6221"]
#        self.setup_6221("dc")
#        #source_6221.source_compliance = curr * 1E4  # compliance voltage
#        source_6221.source_compliance = 5  # compliance voltage
#        source_6221.source_range = curr / 0.6
#        source_6221.source_current = 0
#        source_6221.enable_source()
#        try:
#            for i, c in enumerate(curr_arr):
#                source_6221.source_current = c
#                time.sleep(measure_delay)
#                tmp_df.loc[len(tmp_df)] = [c, instr_2182.voltage, self.instrs["itc"].temperature]
#                self.live_plot_update(0, 0, 0, [tmp_df["I"]], [tmp_df["V"]])
#                self.live_plot_update(0, 1, 0, [measure_delay * np.arange(len(tmp_df["T"]))], [tmp_df["T"]])
#                if i % 10 == 0:
#                    tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            self.dfs["IV"] = tmp_df.copy()
#            self.set_unit({"I": "uA", "V": "uV"})
#        except KeyboardInterrupt:
#            print("Measurement interrupted")
#        finally:
#            tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            source_6221.disable_source()
#            source_6221.shutdown()
#            instr_2182.shutdown()
#
#    @print_help_if_needed
#    def measure_VI_SR830(self, measurename_all, *var_tuple: int | float | str, tmpfolder: str = None,
#                         source: Literal["sr830", "6221"], delay: int = 15, offset_6221=0,
#                         order: tuple[int, int] = (1, 2)) -> None:
#        """
#        conduct the 1-pair nonlinear measurement using 2 SR830 meters and store the data in the corresponding file. Using first meter to measure 2w signal and also as the source if appoint SR830 as source. (meters need to be loaded before calling this function). When using Keithley 6221 current source, the max voltage is the compliance voltage and the resistance does not have specific meaning, just used for calculating the current.
#        appoint the resistor to 1000 when using 6221(just for convenience, no special reason)
#
#        Args:
#            measurename_all (str): the full name of the measurement
#            var_tuple (any): the variables of the measurement, use "-h" to see the available options
#            tmpfolder (str): the temporary folder to store the data
#            source (Literal["sr830", "6221"]): the source of the measurement
#            delay (int): the delay time between each measurement
#            offset_6221 (int, [A]): the offset of the 6221 current source
#        """
#        file_path = self.get_filepath(measurename_all, *var_tuple, tmpfolder=tmpfolder)
#        file_path.parent.mkdir(parents=True, exist_ok=True)
#        if offset_6221 != 0:
#            file_path = file_path.with_name(file_path.name + f"offset{offset_6221}")
#        self.add_measurement(measurename_all)
#        print(f"Filename is: {file_path.name}")
#        print(f"Max Curr: {var_tuple[0] / var_tuple[1]} A")
#        print(f"steps: {var_tuple[2] - 1}")
#        print(f"2w meter: {self.instrs['sr830'][0].adapter}")
#        print(f"1w meter: {self.instrs['sr830'][1].adapter}")
#        amp = np.linspace(0, var_tuple[0], var_tuple[2])
#        freq = var_tuple[3]
#        resist = var_tuple[1]
#        measure_delay = delay  # [s]
#        tmp_df = pd.DataFrame(columns=["curr", "X_2w", "Y_2w", "R_2w", "phi_2w", "X_1w", "Y_1w", "R_1w", "phi_1w", "T"])
#        out_range = False
#
#        self.setup_SR830()
#        meter_2w = self.instrs['sr830'][0]
#        meter_1w = self.instrs['sr830'][1]
#        meter_2w.harmonic = order[1]
#        meter_1w.harmonic = order[0]
#
#        self.live_plot_init(2, 2, 2, 600, 1400,
#                            titles=[["2w", "phi"], ["1w", "phi"]],
#                            axes_labels=[[["I (A)", "V2w (V)"], ["I (A)", "phi"]],
#                                         [["I (A)", "V1w (V)"], ["I (A)", "phi"]]],
#                            line_labels=[[["X", "Y"], ["", ""]], [["X", "Y"], ["", ""]]])
#        if source == "sr830":
#            meter_1w.reference_source_trigger = "POS EDGE"
#            meter_2w.reference_source_trigger = "SINE"
#            meter_2w.reference_source = "Internal"
#            meter_2w.frequency = freq
#        elif source == "6221":
#            # 6221 use half peak-to-peak voltage as amplitude
#            amp *= np.sqrt(2)
#            source_6221 = self.instrs["6221"]
#            self.setup_6221(offset=offset_6221)
#            source_6221.source_compliance = amp[-1] + 0.1
#            source_6221.source_range = amp[-1] / resist / 0.7
#            print(f"Keithley 6221 source range is set to {amp[-1] / resist / 0.7} A")
#            source_6221.waveform_frequency = freq
#            meter_1w.reference_source_trigger = "POS EDGE"
#            meter_2w.reference_source_trigger = "POS EDGE"
#        try:
#            for i, v in enumerate(amp):
#                if source == "sr830":
#                    meter_2w.sine_voltage = v
#                elif source == "6221":
#                    source_6221.waveform_abort()
#                    source_6221.waveform_amplitude = v / resist
#                    source_6221.waveform_arm()
#                    source_6221.waveform_start()
#                time.sleep(measure_delay)
#                if meter_1w.is_out_of_range():
#                    out_range = True
#                if meter_2w.is_out_of_range():
#                    out_range = True
#                list_2w = meter_2w.snap("X", "Y", "R", "THETA")
#                list_1w = meter_1w.snap("X", "Y", "R", "THETA")
#                temp = self.instrs["itc"].temperature
#                if source == "sr830":
#                    list_tot = [v / resist] + list_2w + list_1w + [temp]
#                if source == "6221":
#                    list_tot = [v / resist / np.sqrt(2)] + list_2w + list_1w + [temp]
#                print(
#                    f"curr: {list_tot[0] * 1E6:.8f} uA\t 2w: {list_tot[1:5]}\t 1w: {list_tot[5:9]}\t T: {list_tot[-1]}")
#                tmp_df.loc[len(tmp_df)] = list_tot
#                self.live_plot_update([0, 0, 0, 1, 1, 1],
#                                      [0, 0, 1, 0, 0, 1],
#                                      [0, 1, 0, 0, 1, 0],
#                                      [tmp_df["curr"]] * 6,
#                                      np.array(tmp_df[["X_2w", "Y_2w", "phi_2w", "X_1w", "Y_1w", "phi_1w"]]).T)
#                if i % 10 == 0:
#                    tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            self.dfs["nonlinear"] = tmp_df.copy()
#            # rename the columns for compatibility with the plotting function
#            self.rename_columns("nonlinear", {"Y_2w": "V2w", "X_1w": "V1w"})
#            self.set_unit({"I": "uA", "V": "uV"})
#            if out_range:
#                print("out-range happened, rerun")
#        except KeyboardInterrupt:
#            print("Measurement interrupted")
#        finally:
#            tmp_df.to_csv(file_path, sep="\t", index=False, float_format="%.12f")
#            if source == "sr830":
#                meter_2w.sine_voltage = 0
#            if source == "6221":
#                source_6221.shutdown()

    @staticmethod
    def get_visa_resources() -> tuple[str, ...]:
        """
        return a list of visa resources
        """
        return pyvisa.ResourceManager().list_resources()

    @staticmethod
    def write_header(file_path: Path, header: str) -> None:
        """
        write the header to the file

        Args:
            file_path (str): the file path
            header (str): the header to write
        """
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header)

    @staticmethod
    def sweep_values(start_value: float, end_value: float, step: float,
                     mode: Literal["start-end", "start-end-start", "0-start-end-0", "0-start-end-start-0"]) \
            -> Generator[float, None, None]:
        """
        generate sweeping sequence according to the mode
        NOTE: the values at ends will be repeated
        """
        if mode == "start-end":
            yield from gen_seq(start_value, end_value, step)
        elif mode == "start-end-start":
            yield from gen_seq(start_value, end_value, step)
            yield from gen_seq(end_value, start_value, -step)
        elif mode == "0-start-end-0":
            yield from gen_seq(0, start_value, step)
            yield from gen_seq(start_value, end_value, step)
            yield from gen_seq(end_value, 0, -step)

        elif mode == "0-start-end-start-0":
            yield from gen_seq(0, start_value, step)
            yield from gen_seq(start_value, end_value, step)
            yield from gen_seq(end_value, start_value, -step)
            yield from gen_seq(start_value, 0, -step)

    def print_pairs(self, sub_type, v1_2w_meter: Literal[0, 1] = 0, v2_1w_meter: Literal[0, 1] = 1):
        if "1pair" in sub_type.split("-"):
            print("===========================================")
            print(f"2w meter: {self.instrs['sr830'][v1_2w_meter].adapter}")
            print(f"1w meter: {self.instrs['sr830'][v2_1w_meter].adapter}")
            print("===========================================")
        elif "2pair" in sub_type.split("-"):
            print("===========================================")
            print(f"V1 meter: {self.instrs['sr830'][v1_2w_meter].adapter}\t ORDER: {self.instrs['sr830'][0].harmonic}")
            print(f"V2 meter: {self.instrs['sr830'][v2_1w_meter].adapter}\t ORDER: {self.instrs['sr830'][1].harmonic}")
            print("===========================================")

    @staticmethod
    def extract_info_mods(measure_mods: tuple[str], *var_tuple: float | str) \
            -> tuple[list[dict], list[dict], list[dict]]:
        """
        Extract the information from the measure_mods and var_tuple
        """
        main_mods, f_str, mod_detail_lst \
            = FileOrganizer.name_fstr_gen(*measure_mods, require_detail=True)

        #================= 1. Load parameters from name str and var_tuple =================
        # this step can be manually done by the user
        def find_positions(lst: list[str], search_term: str) -> int:
            """
            Find positions of elements in the list that contain the search term as a substring.

            Args:
                lst (list[str]): The list to search.
                search_term (str): The term to search for.

            Returns:
                list[int]: The list of positions where the search term is found.
            """
            return [i for i, element in enumerate(lst) if search_term in element][0]

        src_no, sense_no, oth_no = list(map(len, main_mods.split("-")))
        mods_lst = list(main_mods.replace("-", "").replace("_", ""))
        source_dict = {
            "I": {
                "sweep_fix": None,
                "ac_dc": None,
                "fix": None,
                "max": None,
                "step": None,
                "mode": None,
                "freq": None
            },
            "V": {
                "sweep_fix": None,
                "ac_dc": None,
                "fix": None,
                "max": None,
                "step": None,
                "mode": None,
                "freq": None
            },
        }
        sense_dict = {
            "type": None,
            "ac_dc": None
        }
        other_dict = {
            "name": None,
            "sweep_fix": None,
            "fix": None,
            "start": None,
            "stop": None,
            "step": None,
            "mode": None
        }
        src_lst = [copy.deepcopy(source_dict) for _ in range(src_no)]
        sense_lst = [copy.deepcopy(sense_dict) for _ in range(sense_no)]
        other_lst = [copy.deepcopy(other_dict) for _ in range(oth_no)]
        # the index to retrieve the variables from var_tuple
        index_vars = 0
        for idx, (mod, detail) in enumerate(zip(mods_lst, mod_detail_lst)):
            if idx < src_no:
                vars_lst = re.findall(r'{(\w+)}',
                                      MeasureManager.measure_types_json[mod]["source"][detail["sweep_fix"]][
                                          detail["ac_dc"]])
                length = len(vars_lst)
                src_lst[idx][mod]['ac_dc'] = detail["ac_dc"]
                src_lst[idx][mod]['sweep_fix'] = detail["sweep_fix"]
                if detail["ac_dc"] == "ac":
                    src_lst[idx][mod]['freq'] = var_tuple[index_vars + find_positions(vars_lst, "freq")]
                if detail["sweep_fix"] == "sweep":
                    src_lst[idx][mod]["max"] = var_tuple[index_vars + find_positions(vars_lst, "max")]
                    src_lst[idx][mod]["step"] = var_tuple[index_vars + find_positions(vars_lst, "step")]
                    if detail["ac_dc"] == "dc":
                        src_lst[idx][mod]["mode"] = var_tuple[index_vars + find_positions(vars_lst, "mode")]
                elif detail["sweep_fix"] == "fixed":
                    src_lst[idx][mod]["fix"] = var_tuple[index_vars + find_positions(vars_lst, "fix")]
            elif idx < src_no + sense_no:
                vars_lst = re.findall(r'{(\w+)}', MeasureManager.measure_types_json[mod]["sense"])
                length = len(vars_lst)
                sense_lst[idx - src_no]["type"] = mod
                sense_lst[idx - src_no]["ac_dc"] = src_lst[0]["I"]["ac_dc"] if src_lst[0]["I"]["ac_dc"] is not None \
                    else src_lst[0]["V"]["ac_dc"]
            else:
                vars_lst = re.findall(r'{(\w+)}', MeasureManager.measure_types_json[mod][detail["sweep_fix"]])
                length = len(vars_lst)
                other_lst[idx - src_no - sense_no]["name"] = mod
                other_lst[idx - src_no - sense_no]["sweep_fix"] = detail["sweep_fix"]
                if detail["sweep_fix"] == "sweep":
                    other_lst[idx - src_no - sense_no]["start"] = var_tuple[
                        index_vars + find_positions(vars_lst, "start")]
                    other_lst[idx - src_no - sense_no]["stop"] = var_tuple[
                        index_vars + find_positions(vars_lst, "stop")]
                    other_lst[idx - src_no - sense_no]["step"] = var_tuple[
                        index_vars + find_positions(vars_lst, "step")]
                    other_lst[idx - src_no - sense_no]["mode"] = var_tuple[
                        index_vars + find_positions(vars_lst, "mode")]
                elif detail["sweep_fix"] == "fixed":
                    other_lst[idx - src_no - sense_no]["fix"] = var_tuple[index_vars + find_positions(vars_lst, "fix")]
                elif detail["sweep_fix"] == "vary":
                    other_lst[idx - src_no - sense_no]["start"] = var_tuple[
                        index_vars + find_positions(vars_lst, "start")]
                    other_lst[idx - src_no - sense_no]["stop"] = var_tuple[
                        index_vars + find_positions(vars_lst, "stop")]

            index_vars += length

        return src_lst, sense_lst, other_lst
