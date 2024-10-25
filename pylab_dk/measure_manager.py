#!/usr/bin/env python

##TODO: still under reconstruction, not ready for use
"""This module is responsible for managing the measure-related folders and data Note each instrument better be
initialzed right before the measurement, as there may be a long time between loading and measuremnt, leading to
possibilities of parameter changing"""
import copy
from typing import Literal, Generator, Optional
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
from pylab_dk.drivers.probe_rotator import RotatorProbe
from pylab_dk.file_organizer import print_help_if_needed, FileOrganizer
from pylab_dk.data_plot import DataPlot
from pylab_dk.constants import convert_unit, print_progress_bar, gen_seq, constant_generator, \
    combined_generator_list
from pylab_dk.equip_wrapper import ITCs, ITCMercury, WrapperSR830, Wrapper2400, Wrapper6430, Wrapper2182, \
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
        self.instrs: dict[str, list[Meter] | ITCs | OxfordMercuryiPS | ITCMercury | RotatorProbe] = {}
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
            self.instrs[meter_no].append(self.meter_wrapper_dict[meter_no](addr))
            self.instrs[meter_no][-1].setup()

    def load_rotator(self) -> None:
        """
        load the rotator instrument, store it in self.instrs["rotator"]
        """
        self.instrs["rotator"] = RotatorProbe()
        print("Rotator loaded, please check the status:")
        print("Curr Angle:", self.instrs["rotator"].curr_angle())
        print("Curr Velocity:", self.instrs["rotator"].spd())

    def load_ITC503(self, gpib_up: str, gpib_down: str) -> None:
        """
        load ITC503 instruments according to the addresses, store them in self.instrs["itc503"] in corresponding order. Also store the ITC503 instruments in self.instrs["itc"] for convenience to call

        Args:
            gpib_up (str): the address of the upper ITC503
            gpib_down (str): the address of the lower ITC503
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
                           compliance: float | str, freq: float | str = None,
                           sweepmode: Optional[Literal["0-max-0", "0--max-max-0", "manual"]] = None,
                           resistor: float = None, sweep_table: Optional[list[float | str, ...]] = None) \
            -> Generator[float, None, None]:
        """
        source the current using the source meter

        Args:
            source_type (Literal["volt","curr"]): the type of the source
            ac_dc (Literal["ac","dc"]): the mode of the current
            meter (str | SourceMeter): the meter to be used, use "-0", "-1" to specify the meter if necessary
            max_value (float): the maximum current to be sourced
            step_value (float): the step of the current
            compliance (float): the compliance voltage of the source meter
            freq (float): the frequency of the ac current
            sweepmode (Literal["0-max-0","0--max-max-0","manual"]): the mode of the dc current sweep, note that the
                "manual" mode is for both ac and dc source, requiring the sweep_table to be provided
            resistor (float): the resistance of the resistor, used only for sr830 source. Once it is provided, the
                source value will be regarded automatically as current
            sweep_table (list[float|str,...]): the table of the sweep values (only if sweepmode is "manual")
        """
        # load the instrument needed
        source_type = source_type.replace("V", "volt").replace("I", "curr")
        if meter == "6221" and source_type == "volt":
            raise ValueError("6221 cannot source voltage")
        # for string meter param, could be like "6430"(call the first meter under the type)
        # or "6430-0"(call the first meter under the type), or "6430-1"(call the second meter under the type)
        if isinstance(meter, str):
            if len(meter.split("-")) == 1:
                instr = self.instrs[meter][0]
            elif len(meter_tuple := meter.split("-")) == 2:
                instr = self.instrs[meter_tuple[0]][int(meter_tuple[1])]
            else:
                raise ValueError("meter name is not in the correct format")
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
        safe_step: dict | float = instr.safe_step
        if isinstance(safe_step, dict):
            safe_step: float = safe_step[source_type]

        # core functional part
        if ac_dc == "dc":
            if sweepmode == "0-max-0":
                value_gen = self.sweep_values(0, max_value, step_value, mode="start-end-start")
            elif sweepmode == "0--max-max-0":
                value_gen = self.sweep_values(-max_value, max_value, step_value, mode="0-start-end-0")
            elif sweepmode == "manual":
                value_gen = (i for i in convert_unit(sweep_table, "")[0])
                instr.ramp_output(source_type, sweep_table[0], interval=safe_step, compliance=compliance)
            else:
                raise ValueError("sweepmode not recognized")
            for value_i in value_gen:
                instr.uni_output(value_i, compliance=compliance, type_str=source_type)
                yield value_i
        elif ac_dc == "ac":
            if resistor is not None:
                if sweepmode == "manual":
                    volt_gen = (i * resistor for i in convert_unit(sweep_table, "")[0])
                    instr.ramp_output(source_type, sweep_table[0] * resistor, interval=safe_step, compliance=compliance)
                else:
                    volt_gen = (i for i in
                                list(np.arange(0, max_value * resistor, step_value)) + [max_value * resistor])
                for value_i in volt_gen:
                    instr.uni_output(value_i, freq=freq, type_str="volt")
                    yield value_i
            else:
                if meter == "6221" or isinstance(meter, Wrapper6221):
                    instr.setup("ac")
                if sweepmode == "manual":
                    value_gen = (i for i in convert_unit(sweep_table, "")[0])
                    instr.ramp_output(source_type, sweep_table[0], interval=safe_step, compliance=compliance)
                else:
                    value_gen = (i for i in list(np.arange(0, max_value, step_value)) + [max_value])
                for value_i in value_gen:
                    instr.uni_output(value_i, freq=freq, compliance=compliance, type_str=source_type)
                    yield value_i

    def ext_sweep_apply(self, ext_type: Literal["temp", "mag", "B", "T", "angle", "Theta"], *,
                        min_value: float | str = None, max_value: float | str, step_value: float | str,
                        sweepmode: Literal["0-max-0", "0--max-max-0", "min-max", "manual"] = "0-max-0",
                        sweep_table: Optional[tuple[float | str, ...]] = None) \
            -> Generator[float, None, None]:
        """
        sweep the external field (magnetic/temperature).
        Note that this sweep is the "discrete" sweep, waiting at every point till stabilization

        Args:
            ext_type (Literal["temp","mag"]): the type of the external field
            min_value (float | str): the minimum value of the field
            max_value (float | str): the maximum value of the field
            step_value (float | str): the step of the field
            sweepmode (Literal["0-max-0","0--max-max-0","min-max", "manual"]): the mode of the field sweep
            sweep_table (tuple[float,...]): the table of the sweep values (only if sweepmode is "manual")
        """
        ext_type = ext_type.replace("T", "temp").replace("B", "mag").replace("Theta", "angle")
        if ext_type == "temp":
            instr = self.instrs["itc"]
        elif ext_type == "mag":
            instr = self.instrs["ips"]
        elif ext_type == "angle":
            instr = self.instrs["rotator"]
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
        elif sweepmode == "manual":
            value_gen = (i for i in convert_unit(sweep_table, "")[0])
        else:
            raise ValueError("sweepmode not recognized")

        for value_i in value_gen:
            if ext_type == "temp":
                instr.ramp_to_temperature(value_i, wait=True)
            elif ext_type == "mag":
                self.ramp_magfield(value_i, wait=True)
            elif ext_type == "angle":
                instr.ramp_angle(value_i)
            yield value_i

    def sense_apply(self, sense_type: Literal["volt", "curr", "temp", "mag", "V", "I", "T", "B", "H", "angle", "Theta"],
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
        sense_type = (sense_type.replace("V", "volt").replace("I", "curr").
                      replace("T", "temp").replace("B", "mag").replace("H", "mag").
                      replace("Theta", "angle"))
        print(f"Sense Type: {sense_type}")
        if sense_type in ["volt", "curr"] and meter is not None:
            if isinstance(meter, str):
                if len(meter.split("-")) == 1:
                    instr = self.instrs[meter][0]
                elif len(meter_tuple := meter.split("-")) == 2:
                    instr = self.instrs[meter_tuple[0]][int(meter_tuple[1])]
                else:
                    raise ValueError("meter name is not in the correct format")
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
        elif sense_type == "angle":
            instr = self.instrs["rotator"]
            print(f"Sense Meter/Instr: {instr}")
            while True:
                yield instr.curr_angle()

    def record_init(self, measure_mods: tuple[str], *var_tuple: float | str,
                    manual_columns: list[str] = None, return_df: bool = False) \
            -> tuple[Path, int] | tuple[Path, int, pd.DataFrame]:
        """
        initialize the record of the measurement and the csv file;
        note the file will be overwritten with an empty dataframe

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

            columns_lst = rename_duplicates(columns_lst)

        self.dfs["curr_measure"] = pd.DataFrame(columns=columns_lst)
        self.dfs["curr_measure"].to_csv(file_path, sep=",", index=False, float_format="%.12f")
        if return_df:
            return file_path, len(columns_lst), self.dfs["curr_measure"]
        return file_path, len(columns_lst)

    def record_update(self, file_path: Path, record_num: int, record_tuple: tuple[float],
                      target_df: pd.DataFrame = None,
                      force_write: bool = False, with_time: bool = True, nocache: bool = False) -> None:
        """
        update the record of the measurement and also control the size of dataframe
        when the length of current_measure dataframe is larger than 7,

        Args:
            file_path (Path): the file path
            record_num (int): the number of columns of the record
            record_tuple (tuple): tuple of the records, with no time column, so length is 1 shorter
            target_df (pd.DataFrame): dataframe to be updated (default using the self.dfs['current_measure'])
            force_write (bool): whether to force write the record
            with_time (bool): whether to record the time (first column), note the time column
                is by default included by record_init method
            nocache (bool): whether to keep store all data in memory, if true,
                the dataframe will be written to the file INCREMENTALLY and reset to EMPTY
                (necessary for plotting, only turn on when dataset is extremely large
                    and plotting is not necessary)
        """
        # use reference to ensure synchronization of changes
        if target_df is None:
            curr_df = self.dfs["curr_measure"]
        else:
            curr_df = target_df

        if with_time:
            # the time is updated here, no need to be provided
            assert len(record_tuple) == record_num - 1, "The number of columns does not match"
            curr_df.loc[len(curr_df)] = (
                    [datetime.datetime.now().strftime("%y-%m-%d_%H:%M:%S")] + list(record_tuple))
        else:
            assert len(record_tuple) == record_num, "The number of columns does not match"
            curr_df.loc[len(curr_df)] = list(record_tuple)
        length = len(curr_df)
        if nocache:
            if length >= 7 or force_write:
                curr_df.to_csv(file_path, sep=",", mode="a",
                               header=False, index=False, float_format="%.12f")
                curr_df.drop(curr_df.index, inplace=True)
        else:
            if (length % 7 == 0) or force_write:
                curr_df.to_csv(file_path, sep=",", index=False, float_format="%.12f")
                #curr_df = pd.DataFrame(columns=curr_df.columns)

    @print_help_if_needed
    def get_measure_dict(self, measure_mods: tuple[str], *var_tuple: float | str,
                         wrapper_lst: list[Meter | SourceMeter] = None, compliance_lst: list[float | str],
                         sr830_current_resistor: float = None, if_combine_gen: bool = True,
                         sweep_tables: list[list[float | str, ...]] | tuple[tuple[float | str, ...]] = None) -> dict:
        """
        do the preset of measurements and return the generators, filepath and related info
        1. meter setup should be done before calling this method, they will be bound to generators
        2. the generators are listed in parallel, if there are more than one sweep,
            do manual Cartesian product using itertools.product(gen1,gen2) -> (gen1.1,gen2.all), (gen1.2,gen2.all)...
        3. about the varying of T/B, they will be ramped to the start value first, and then the start_vary functions
            will be returned, call the function to start the varying; and the generator for varying is a sense_apply

        sweep mode: for I,V: "0-max-0", "0--max-max-0", "manual"
        sweep mode: for T,B: "0-max-0", "0--max-max-0", "min-max", "manual"

        Args:
            measure_mods (tuple[str]): the modules of measurement
            var_tuple (tuple): the variables of the measurement, use "-h" to see the variables' list
            wrapper_lst (list[Meter]): the list of the wrappers to be used
            compliance_lst (list[float]): the list of the compliance to be used (sources)
            sr830_current_resistor (float): the resistance of the resistor, used only for sr830 curr source
            if_combine_gen (bool): whether to combine the generators as a whole list generator,
                                if False, return the list of generators for further operations
            sweep_tables (list[list[float | str, ...]]): the list of the sweep tables for manual sweep,
                                the table will be fetched and used according to the order from left to right(0->1->2...)

        Returns:
            dict: a dictionary containing the list of generators, dataframe csv filepath and record number
                keys: "gen_lst"(combined list generator), "swp_idx" (indexes for sweeping generator, not including vary),
                "file_path"(csv file), "record_num"(num of record data columns, without time),
                "tmp_vary", "mag_vary" (the function used to begin the varying of T/B, no parameters needed, e.g. start magnetic field varying by calling mag_vary())
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
        vary_mod = []  # T, B, angle
        # source part
        mod_i: Literal["I", "V"]
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
                if src_mod[mod_i]["mode"] == "manual":
                    sweep_table = sweep_tables.pop(0)
                else:
                    sweep_table = None
                rec_lst.append(self.source_sweep_apply(mod_i, src_mod[mod_i]["ac_dc"], wrapper_lst[idx],
                                                       max_value=src_mod[mod_i]["max"],
                                                       step_value=src_mod[mod_i]["step"],
                                                       compliance=compliance_lst[idx], freq=src_mod[mod_i]["freq"],
                                                       sweepmode=src_mod[mod_i]["mode"],
                                                       resistor=sr830_current_resistor,
                                                       sweep_table=sweep_table))
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
                elif oth_mod["name"] == "Theta":
                    self.instrs["rotator"].ramp_angle(oth_mod["fix"], wait=True)
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
                elif oth_mod["name"] == "Theta":
                    vary_mod.append("Theta")
                    self.instrs["rotator"].ramp_angle(oth_mod["start"], wait=True)

                    def angle_vary():
                        self.instrs["rotator"].ramp_angle(oth_mod["stop"], wait=False)

                rec_lst.append(self.sense_apply(oth_mod["name"], if_during_vary=True))
            elif oth_mod["sweep_fix"] == "sweep":
                if oth_mod["mode"] == "manual":
                    sweep_table = sweep_tables.pop(0)  # pop from start
                else:
                    sweep_table = None
                rec_lst.append(self.ext_sweep_apply(oth_mod["name"],
                                                    min_value=oth_mod["min"],
                                                    max_value=oth_mod["max"],
                                                    step_value=oth_mod["step"],
                                                    sweepmode=oth_mod["mode"],
                                                    sweep_table=sweep_table))
                sweep_idx.append(idx + len(src_lst) + len(sense_lst))
        if if_combine_gen:
            total_gen = combined_generator_list(rec_lst)
        else:
            total_gen = rec_lst

        return {
            "gen_lst": total_gen,
            "swp_idx": sweep_idx,
            "file_path": file_path,
            "record_num": record_num,
            "tmp_vary": None if "T" not in vary_mod else temp_vary,
            "mag_vary": None if "B" not in vary_mod else mag_vary,
            "angle_vary": None if "Theta" not in vary_mod else angle_vary
        }

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
