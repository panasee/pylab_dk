#!/usr/bin/env python

"""
This module contains the wrapper classes for used equipments in
measure_manager.py. The purpose of this module is to unify the interface
of different equipments, so that they can be combined freely

each wrapper provides the following methods(some only for source meters):
- setup: initialize the equipment, usually just basic settings not including output
- output_switch: switch the output on or off
- uni_output: set the output to a certain value
    all output methods have two implementations, one is from off to on, including
    setting up parameters like range and compliance, the other is just setting the
    output value when already on
- get_output: get the current output value
- sense: set the meter to sense current or voltage
- shutdown: shutdown the equipment
- ramp_output: ramp the output to the target value
* the member "meter" is provided for directly accessing the equipment driver
* the member "info_dict" is provided for storing the information of the equipment

Flow:
    Wrapperxxxx(GPIB)
    setup("ac/dc")
    uni_output(value, (freq), compliance, type_str)
    (change value without disabling the output)
    shutdown()
"""
from __future__ import annotations

import time
from typing import Literal, Tuple
from abc import ABC, abstractmethod

import numpy as np
from pymeasure.instruments.srs import SR830
from pymeasure.instruments.oxfordinstruments import ITC503
from pymeasure.instruments.keithley import Keithley6221
from pymeasure.instruments.keithley import Keithley2182
from common.Keithley_2400 import Keithley2400
from common.mercuryITC import MercuryITC
from common.Keithley_6430 import Keithley_6430

from common.constants import convert_unit, print_progress_bar, switch_dict
from common.data_plot import DataPlot


class Meter(ABC):
    """
    The usage should be following the steps:
    1. instantiate
    2. setup method
    3. output_switch method (embedded in output method for the first time)
    4. uni/rms/dc_output method or ramp_output method
    5(if needed). sense method
    LAST. shutdown method
    """

    @abstractmethod
    def __init__(self):
        self.info_dict = {}
        self.meter = None

    @abstractmethod
    def setup(self, *vargs, **kwargs):
        pass

    def info(self, *, sync=True):
        if sync:
            self.info_sync()
        return self.info_dict

    @abstractmethod
    def info_sync(self):
        self.info_dict.update({})

    @abstractmethod
    def sense(self, type_str: Literal["curr", "volt"]):
        pass

    def __del__(self):
        self.meter.__del__()


class SourceMeter(Meter):
    @abstractmethod
    def __init__(self):
        super().__init__()
        self.info_dict.update({"output_type": "curr"})

    @abstractmethod
    def output_switch(self, switch: bool | Literal["on", "off", "ON", "OFF"]):
        self.info_dict["output_status"] = switch if isinstance(switch, bool) else switch.lower() in ["on", "ON"]

    @abstractmethod
    def uni_output(self, value: float | str, *, freq: float | str = None, compliance: float | str = None,
                   type_str: Literal["curr", "volt"]):
        self.info_dict["output_type"] = type_str

    @abstractmethod
    def shutdown(self):
        pass

    def __del__(self):
        self.shutdown()
        self.meter.__del__()

    def ramp_output(self, type_str: Literal["curr", "volt", "V", "I"], value: float | str, *,
                    compliance: float | str = None, interval: float | str = None, sleep=0.2):
        """
        ramp the output to the target value

        Args:
            type_str: "curr" or "volt"
            interval: the step interval between each step
            sleep: the time interval between each step
            value: the target value
            compliance: the compliance value
        """
        type_str = type_str.replace("V", "volt").replace("I", "curr")
        value = convert_unit(value, "")[0]
        self.output_switch("off")
        self.output_switch("on")
        if interval is None:
            arr = np.linspace(0, value, 100)
        elif isinstance(interval, (float, str)):
            interval = convert_unit(interval, "")[0]
            arr = np.arange(0, value, interval)
            arr = np.concatenate((arr, [value]))
        else:
            raise ValueError("interval should be a float or str or just missing")

        for i in arr:
            self.uni_output(i, type_str=type_str, compliance=compliance)
            print_progress_bar(i / value * 100, 100, prefix="Ramping:")
            time.sleep(sleep)


class ACSourceMeter(SourceMeter):

    def __init__(self):
        super().__init__()

    @abstractmethod
    def rms_output(self, value: float | str, *, freq: float | str, compliance: float | str,
                   type_str: Literal["curr", "volt"]):
        pass


class DCSourceMeter(Meter):
    @abstractmethod
    def __init__(self):
        super().__init__()

    @abstractmethod
    def dc_output(self, value: float | str, *, compliance: float | str, type_str: Literal["curr", "volt"]):
        pass


class Wrapper6221(ACSourceMeter, DCSourceMeter):
    """
    Flow:
    Wrapper6221(GPIB)
    setup("ac/dc")
    uni_output(value, (freq), compliance, type_str)
    (change value without disabling the output)
    shutdown()
    """

    def __init__(self, GPIB: str = "GPIB0::12::INSTR"):
        super().__init__()
        self.meter = Keithley6221(GPIB)
        self.info_dict = {"GPIB": GPIB,
                          "output_type": "curr",
                          "ac_dc": "ac",
                          "output_status": False,
                          "output_value": 0,
                          }
        self.info_sync()

    def info_sync(self):
        self.info_dict.update({"source_range": self.meter.source_range,
                               "output_value": self.meter.source_current,
                               "frequency": self.meter.waveform_frequency,
                               "compliance": self.meter.source_compliance,
                               "wave_function": self.meter.waveform_function,
                               "wave_offset": self.meter.waveform_offset,
                               "wave_phasemarker": self.meter.waveform_phasemarker_phase,
                               "low_grounded": self.meter.output_low_grounded,
                               })

    def setup(self, mode: Literal["ac", "dc"] = "ac", *, offset=0, source_auto_range=False,
              low_grounded=False, wave_function="sine") -> None:
        """
        set up the Keithley 6221 instruments, overwrite the specific settings here, other settings will all be
        reserved. Note that the waveform will not begin here
        """
        source_6221 = self.meter
        source_6221.clear()
        if mode == "ac":
            self.info_dict["ac_dc"] = "ac"
            source_6221.waveform_function = wave_function
            source_6221.waveform_amplitude = 0
            source_6221.waveform_offset = offset
            source_6221.waveform_ranging = "best"
            source_6221.waveform_use_phasemarker = True
            source_6221.waveform_phasemarker_line = 3
            source_6221.waveform_duration_set_infinity()
            source_6221.waveform_phasemarker_phase = 0
            self.info_dict.update({"wave_function": wave_function, "wave_offset": offset, "wave_phasemarker": 0})
        elif mode == "dc":
            self.info_dict["ac_dc"] = "dc"
        source_6221.source_auto_range = source_auto_range
        source_6221.output_low_grounded = low_grounded
        self.info_dict.update({"low_grounded": low_grounded})

    def output_switch(self, switch: bool | Literal["on", "off", "ON", "OFF"]):
        """
        switch the output on or off
        """
        switch = switch_dict.get(switch, False) if isinstance(switch, str) else switch
        if self.info_dict["ac_dc"] == "ac":
            if switch:
                self.meter.waveform_arm()
                self.meter.waveform_start()
                self.info_dict["output_status"] = True
            else:
                self.meter.waveform_amplitude = 0
                self.meter.waveform_abort()
                self.info_dict["output_status"] = False

        elif self.info_dict["ac_dc"] == "dc":
            if switch:
                self.meter.enable_source()
                self.info_dict["output_status"] = True
            else:
                self.meter.source_current = 0
                self.meter.disable_source()
                self.info_dict["output_status"] = False

    def uni_output(self, value: float | str, *, freq: float | str = None,
                   compliance: float | str = None, type_str: Literal["curr"] = "curr"):
        if self.info_dict["ac_dc"] == "ac":
            self.rms_output(value, freq=freq, compliance=compliance, type_str=type_str)
        elif self.info_dict["ac_dc"] == "dc":
            self.dc_output(value, compliance=compliance, type_str=type_str)

    def rms_output(self, value: float | str, *, freq: float | str = None, compliance: float | str = None,
                   type_str: Literal["curr"] = "curr"):
        """
        6221 is a current source, so the output is always current
        set the output to a certain value
        """
        if type_str != "curr":
            raise ValueError("6221 is a current source, so the output is always current")

        value = convert_unit(value, "")[0]
        value_p2p = value * np.sqrt(2)

        if not self.info_dict["output_status"]:

            self.meter.waveform_frequency = convert_unit(freq, "Hz")[0]
            self.info_dict["frequency"] = freq
            if compliance is not None:
                compliance = convert_unit(compliance, "")[0]
            else:
                compliance = value_p2p * 10000
            self.meter.source_compliance = compliance

            self.meter.source_range = value_p2p / 0.6
            self.meter.waveform_amplitude = value_p2p

            self.output_switch("on")

        elif self.info_dict["output_status"]:
            if freq is not None:
                self.meter.waveform_frequency = convert_unit(freq, "Hz")[0]
                self.info_dict["frequency"] = freq
            self.meter.waveform_amplitude = value_p2p

    def dc_output(self, value: float | str, *, compliance: float | str = None, type_str: Literal["curr"] = "curr"):
        """
        6221 is a current source, so the output is always current
        set the output to a certain value
        """
        if type_str != "curr":
            raise ValueError("6221 is a current source, so the output is always current")

        value = convert_unit(value, "")[0]

        if compliance is not None:
            compliance = convert_unit(compliance, "")[0]
        else:
            compliance = 5
        self.meter.source_compliance = compliance

        self.meter.source_range = value / 0.6
        self.meter.source_current = value

        self.output_switch("on")

    def sense(self, type_str: Literal["curr", "volt"]):
        print("6221 is a source meter, no sense function")

    def shutdown(self):
        if self.info_dict["output_status"]:
            self.output_switch("off")
        self.meter.shutdown()


class Wrapper2182(Meter):
    """
    Flow:
    Wrapper2182(GPIB)
    setup(channel)
    sense()
    """

    def __init__(self, GPIB: str = "GPIB0::7::INSTR"):
        super().__init__()
        self.meter = Keithley2182(GPIB)
        self.setup()
        self.info_dict = {"GPIB": GPIB,
                          "channel": 1,
                          "sense_type": "volt"}

    def setup(self, *, channel: Literal[0, 1, 2] = 1) -> None:
        self.meter.reset()
        self.meter.active_channel = channel
        self.meter.channel_function = "voltage"
        self.meter.voltage_nplc = 5
        # source_2182.sample_continuously()
        # source_2182.ch_1.voltage_offset_enabled = True
        # source_2182.ch_1.acquire_voltage_reference()
        self.meter.ch_1.setup_voltage()

    def info_sync(self):
        """
        no parameters to sync for 2182
        """
        pass

    def sense(self, type_str: Literal["volt"] = "volt"):
        return self.meter.voltage


class WrapperSR830(ACSourceMeter):
    def __init__(self, GPIB: str = "GPIB0::8::INSTR", reset=True):
        super().__init__()
        self.meter = SR830(GPIB)
        self.info_dict = {"GPIB": GPIB,
                          }
        if reset:
            self.setup()
        self.info_sync()

    def info_sync(self):
        self.info_dict.update({"sensitivity": self.meter.sensitivity,
                               "ref_source_trigger": self.meter.reference_source_trigger,
                               "reference_source": self.meter.reference_source,
                               "harmonic": self.meter.harmonic,
                               "output_value": self.meter.sine_voltage,
                               "output_status": self.meter.sine_voltage > 0.004,
                               "frequency": self.meter.frequency,
                               "filter_slope": self.meter.filter_slope,
                               "time_constant": self.meter.time_constant,
                               "input_config": self.meter.input_config,
                               "input_coupling": self.meter.input_coupling,
                               "input_grounding": self.meter.input_grounding,
                               "input_notch_config": self.meter.input_notch_config,
                               "reserve": self.meter.reserve,
                               "filter_synchronous": self.meter.filter_synchronous})

    def setup(self, *, filter_slope=24, time_constant=0.3, input_config="A - B",
              input_coupling="AC", input_grounding="Float", sine_voltage=0,
              input_notch_config="None", reference_source="External",
              reserve="High Reserve", filter_synchronous=False) -> None:
        """
        setup the SR830 instruments using pre-stored setups here, this function will not fully reset the instruments,
        only overwrite the specific settings here, other settings will all be reserved
        """
        self.meter.filter_slope = filter_slope
        self.meter.time_constant = time_constant
        self.meter.input_config = input_config
        self.meter.input_coupling = input_coupling
        self.meter.input_grounding = input_grounding
        self.meter.sine_voltage = sine_voltage
        self.meter.input_notch_config = input_notch_config
        self.meter.reference_source = reference_source
        self.meter.reserve = reserve
        self.meter.filter_synchronous = filter_synchronous
        self.info_dict.update({"filter_slope": filter_slope, "time_constant": time_constant,
                               "input_config": input_config, "input_coupling": input_coupling,
                               "input_grounding": input_grounding, "sine_voltage": sine_voltage,
                               "input_notch_config": input_notch_config, "reference_source": reference_source,
                               "reserve": reserve, "filter_synchronous": filter_synchronous})

    def reference_set(self, *, freq: float | str = None, source: Literal["Internal", "External"] = "Internal",
                      trigger: Literal["SINE", "POS EDGE", "NEG EDGE"] = "SINE", harmonic: int = 1):
        """
        set the reference frequency and source
        """
        if freq is not None:
            self.meter.frequency = convert_unit(freq, "Hz")[0]
        self.meter.reference_source_trigger = trigger
        self.meter.reference_source = source
        self.meter.harmonic = harmonic
        self.info_sync()

    def sense(self, type_str: Literal["volt"] = "volt"):
        return self.meter.snap("X", "Y", "R", "THETA")

    def output_switch(self, switch: bool | Literal["on", "off", "ON", "OFF"]):
        switch = switch_dict.get(switch, False) if isinstance(switch, str) else switch
        if switch:
            # no actual switch of SR830
            self.info_dict["output_status"] = True
        else:
            self.meter.sine_voltage = 0
            self.info_dict["output_status"] = False

    def uni_output(self, value: float | str, *, freq: float | str = None, compliance: float | str = None,
                   type_str: Literal["volt"] = "volt"):
        self.rms_output(value, freq=freq, compliance=compliance, type_str=type_str)

    def rms_output(self, value: float | str, *, freq: float | str = None, compliance: float | str = None,
                   type_str: Literal["volt"] = "volt"):
        if type_str != "volt":
            raise ValueError("SR830 is a voltage source, so the output is always voltage")
        value = convert_unit(value, "V")[0]
        self.meter.sine_voltage = value
        self.info_dict["output_value"] = value
        self.info_dict["output_status"] = True
        if freq is not None:
            self.meter.frequency = convert_unit(freq, "Hz")[0]
            self.info_dict["frequency"] = freq

    def shutdown(self):
        if self.info_dict["output_status"]:
            self.output_switch("off")


class Wrapper6430(DCSourceMeter):
    def __init__(self, GPIB: str = "GPIB0::26::INSTR"):
        super().__init__()
        self.meter = Keithley_6430("Keithley6430", GPIB)
        self.info_dict = {}
        self.info_sync()

    def info_sync(self):
        self.info_dict.update({
            "output_status": self.meter.output_enabled(),
            "output_type": self.meter.source_mode().lower(),
            "curr_compliance": self.meter.source_current_compliance(),
            "volt_compliance": self.meter.source_voltage_compliance(),
            "source_curr_range": self.meter.source_current_range(),
            "source_volt_range": self.meter.source_voltage_range(),
            "source_delay": self.meter.source_delay(),
            "sense_type": self.meter.sense_mode().lower(),
            "sense_auto_range": self.meter.sense_autorange(),
            "sense_curr_range": self.meter.sense_current_range(),
            "sense_volt_range": self.meter.sense_voltage_range(),
            "sense_resist_range": self.meter.sense_resistance_range(),
            "sense_resist_offset_comp": self.meter.sense_resistance_offset_comp_enabled(),
            "autozero": self.meter.autozero(),
        })

    def setup(self, *, auto_zero: str = "on"):
        self.meter.reset()
        self.meter.output_enabled(False)
        self.meter.autozero(auto_zero)
        self.meter.sense_autorange(True)
        self.info_sync()

    def sense(self, type_str: Literal["curr", "volt", "resist"]):
        if type_str == "curr":
            self.meter.sense_mode("CURR:DC")
            return self.meter.sense_current()
        elif type_str == "volt":
            self.meter.sense_mode("VOLT:DC")
            return self.meter.sense_voltage()
        elif type_str == "resist":
            self.meter.sense_mode("RES")
            return self.meter.sense_resistance()

    def switch_output(self, switch: bool | Literal["on", "off", "ON", "OFF"]):
        switch = switch_dict.get(switch, False) if isinstance(switch, str) else switch
        self.meter.output_enabled(switch)
        self.info_dict["output_status"] = switch

    def uni_output(self, value: float | str, *, compliance: float | str, type_str: Literal["curr", "volt"]):
        self.dc_output(value, compliance=compliance, type_str=type_str)

    def dc_output(self, value: float | str, *, compliance: float | str, type_str: Literal["curr", "volt"]):
        value = convert_unit(value, "")[0]
        if type_str == "curr":
            self.meter.source_mode("CURR")
            self.meter.source_current_range(min(max(value / 0.7, 1E-12), 0.105))
            self.meter.source_voltage_compliance(convert_unit(compliance, "A")[0])
            self.meter.source_current(value)

        elif type_str == "volt":
            self.meter.source_mode("VOLT")
            self.meter.source_voltage_range(min(max(value / 0.7, 0.2), 200))
            self.meter.source_current_compliance(convert_unit(compliance, "V")[0])
            self.meter.source_voltage(value)

        self.info_dict["output_type"] = type_str
        self.switch_output("on")

    def shutdown(self):
        self.switch_output("off")


class Wrapper2400(DCSourceMeter):
    def __init__(self, GPIB: str = "GPIB0::24::INSTR"):
        super().__init__()
        self.meter = Keithley2400("Keithley2400", GPIB)
        self.info_dict = {}
        self.info_sync()

    def info_sync(self):
        self.info_dict.update({
            "output_status": self.meter.output(),
            "output_type": self.meter.mode().lower(),
            "curr_compliance": self.meter.compliancei(),
            "volt_compliance": self.meter.compliancev(),
            "curr_range": self.meter.rangei(),
            "volt_range": self.meter.rangev(),
            "sense_type": self.meter.sense().lower(),
        })

    def setup(self):
        self.info_sync()

    def sense(self, type_str: Literal["curr", "volt", "resist"]):
        if type_str == "curr":
            if self.info_dict["output_type"] == "curr":
                print("in curr mode, print the set point")
            return self.meter.curr()
        elif type_str == "volt":
            if self.info_dict["output_type"] == "volt":
                print("in curr mode, print the set point")
            return self.meter.volt()
        elif type_str == "resist":
            return self.meter.resistance()

    def switch_output(self, switch: bool | Literal["on", "off", "ON", "OFF"]):
        switch = switch_dict.get(switch, False) if isinstance(switch, str) else switch
        self.meter.output(switch)
        self.info_dict["output_status"] = switch

    def uni_output(self, value: float | str, *, compliance: float | str, type_str: Literal["curr", "volt"]):
        self.dc_output(value, compliance=compliance, type_str=type_str)

    def dc_output(self, value: float | str, *, compliance: float | str, type_str: Literal["curr", "volt"]):
        value = convert_unit(value, "")[0]
        if type_str == "curr":
            self.meter.mode("CURR")
            self.meter.rangei(value / 0.7)
            self.meter.compliancev(convert_unit(compliance, "A")[0])
            self.meter.curr(value)

        elif type_str == "volt":
            self.meter.mode("VOLT")
            self.meter.rangev(value / 0.7)
            self.meter.compliancei(convert_unit(compliance, "V")[0])
            self.meter.volt(value)

        self.info_dict["output_type"] = type_str
        self.switch_output("on")

    def shutdown(self):
        self.meter.curr(0)
        self.meter.volt(0)
        self.switch_output("off")


"""
Wrappers for ITC are following
"""


class ITC(ABC, DataPlot):
    # parent class to incorporate both two ITCs
    @property
    @abstractmethod
    def temperature(self):
        """return the precise temperature of the sample"""
        pass

    @property
    @abstractmethod
    def temperature_set(self):
        """return the setpoint temperature"""
        pass

    @temperature_set.setter
    @abstractmethod
    def temperature_set(self, temp):
        """
        set the target temperature for sample, as for other parts' temperature, use the methods for each ITC
        """
        pass

    @property
    @abstractmethod
    def pid(self):
        """
        return the PID parameters
        """
        pass

    @abstractmethod
    def set_pid(self, pid_dict):
        """
        set the PID parameters

        Args:
            pid_dict (Dict): a dictionary as {"P": float, "I": float, "D": float}
        """
        pass

    @abstractmethod
    def correction_ramping(self, temp: float, trend: Literal["up", "down", "up-huge", "down-huge"]):
        """
        Correct the sensor choosing or pressure when ramping through the temperature threshold

        Args:
            temp (float): the current temperature
            trend (Literal["up","down"]): the trend of the temperature
        """
        pass

    def wait_for_temperature(self, temp, *, if_plot=False, delta=0.01, check_interval=1, stability_counter=120,
                             thermalize_counter=120):
        """
        wait for the temperature to stablize for a certain time length

        Args: temp (float): the target temperature delta (float): the temperature difference to consider the
        temperature stablized check_interval (int,[s]): the interval to check the temperature stability_counter (
        int): the number of times the temperature is within the delta range to consider the temperature stablized
        thermalize_counter (int): the number of times to thermalize the sample if_plot (bool): whether to plot the
        temperature change
        """
        if self.temperature < temp - 100:
            trend = "up-huge"
        elif self.temperature > temp + 100:
            trend = "down-huge"
        elif self.temperature < temp:
            trend = "up"
        else:
            trend = "down"

        if if_plot:
            self.live_plot_init(1, 1, 1, 600, 1400, titles=[["T ramping"]],
                                axes_labels=[[[r"Time (s)", r"T (K)"]]])
            t_arr = [0]
            T_arr = [self.temperature]
        i = 0
        while i < stability_counter:
            self.correction_ramping(self.temperature, trend)
            if abs(self.temperature - temp) < ITC.dynamic_delta(temp, delta):
                i += 1
            elif i >= 5:
                i -= 5
            if if_plot:
                t_arr.append(t_arr[-1] + check_interval)
                T_arr.append(self.temperature)
                self.live_plot_update(0, 0, 0, t_arr, T_arr)
            print_progress_bar(i, stability_counter, prefix="Stablizing",
                               suffix=f"Temperature: {self.temperature:.2f} K")
            time.sleep(check_interval)
        print("Temperature stablized")
        for i in range(thermalize_counter):
            print_progress_bar(i + 1, thermalize_counter, prefix="Thermalizing",
                               suffix=f"Temperature: {self.temperature:.2f} K")
            if if_plot:
                t_arr.append(t_arr[-1] + check_interval)
                T_arr.append(self.temperature)
                self.live_plot_update(0, 0, 0, t_arr, T_arr)
            time.sleep(check_interval)
        print("Thermalizing finished")

    def ramp_to_temperature(self, temp, *, delta=0.01, check_interval=1, stability_counter=60, thermalize_counter=60,
                            pid=None, ramp_rate=None, wait=True, if_plot=False):
        """ramp temperature to the target value (not necessary sample temperature)"""
        self.temperature_set = temp
        if pid is not None:
            self.set_pid(pid)
        if wait:
            self.wait_for_temperature(temp, delta=delta, check_interval=check_interval,
                                      stability_counter=stability_counter,
                                      thermalize_counter=thermalize_counter, if_plot=if_plot)

    @staticmethod
    def dynamic_delta(temp, delta_lowt) -> float:
        """
        calculate a dynamic delta to help high temperature to stabilize (reach 0.1K tolerance when 300K and {delta_lowt} when 10K)
        """
        # let the delta be delta_lowt at 1.5K and 0.2K at 300K
        t_low = 1.5
        delta_hight = 0.2
        t_high = 300
        return (delta_hight - delta_lowt) * (temp - t_low) / (t_high - t_low) + delta_lowt


class ITCMercury(ITC):
    def __init__(self, address="TCPIP0::10.97.27.13::7020::SOCKET"):
        DataPlot.load_settings(False, False)
        self.mercury = MercuryITC("mercury_itc", address)

    @property
    def pres(self):
        return self.mercury.pressure()

    def set_pres(self, pres: float):
        self.mercury.pressure_setpoint(pres)

    @property
    def flow(self):
        return self.mercury.gas_flow()

    def set_flow(self, flow: float):
        """
        set the gas flow, note the input value is percentage, from 0 to 99.9 (%)
        """
        if not 0.0 < flow < 100.0:
            raise ValueError("Flow must be between 0.0 and 100.0 (%)")
        self.mercury.gas_flow(flow)

    @property
    def pid(self):
        return {"P": self.mercury.temp_loop_P(), "I": self.mercury.temp_loop_I(),
                "D": self.mercury.temp_loop_D()}

    def set_pid(self, pid: dict):
        """
        set the pid of probe temp loop
        """
        self.mercury.temp_PID = (pid["P"], pid["I"], pid["D"])
        self.pid_control("ON")

    def pid_control(self, control: Literal["ON", "OFF"]):
        self.mercury.temp_PID_control(control)

    @property
    def temperature(self):
        return self.mercury.probe_temp()

    def set_temperature(self, temp, vti_temp=None):
        """set the target temperature for sample"""
        self.mercury.temp_setpoint(temp)
        if vti_temp is not None:
            self.mercury.vti_temp_setpoint(vti_temp)
        else:
            self.mercury.vti_temp_setpoint(self.mercury.calculate_vti_temp(temp))

    @property
    def temperature_set(self):
        return self.mercury.temp_setpoint()

    @temperature_set.setter
    def temperature_set(self, temp):
        self.set_temperature(temp)

    @property
    def vti_temperature(self):
        return self.mercury.vti_temp()

    def set_vti_temperature(self, temp):
        self.mercury.vti_temp_setpoint(temp)

    def ramp_to_temperature(self, temp, *, delta=0.01, check_interval=1, stability_counter=120, thermalize_counter=120,
                            pid=None, ramp_rate=None, wait=True, if_plot=False):
        """ramp temperature to the target value (not necessary sample temperature) Args: temp (float): the target
        temperature delta (float): the temperature difference to consider the temperature stablized check_interval (
        int,[s]): the interval to check the temperature stability_counter (int): the number of times the temperature
        is within the delta range to consider the temperature stablized thermalize_counter (int): the number of times
        to thermalize the sample pid (Dict): a dictionary as {"P": float, "I": float, "D": float} ramp_rate (float,
        [K/min]): the rate to ramp the temperature
        """
        self.temperature_set = temp
        if pid is not None:
            self.set_pid(pid)

        if ramp_rate is not None:
            self.mercury.probe_ramp_rate(ramp_rate)
            # self.mercury.vti_heater_rate(ramp_rate)
            self.mercury.probe_temp_ramp_mode("ON")
        else:
            self.mercury.probe_temp_ramp_mode("OFF")
        if wait:
            self.wait_for_temperature(temp, delta=delta, check_interval=check_interval,
                                      stability_counter=stability_counter,
                                      thermalize_counter=thermalize_counter, if_plot=if_plot)

    def correction_ramping(self, temp: float, trend: Literal["up", "down", "up-huge", "down-huge"]):
        """
        Correct the sensor choosing or pressure when ramping through the temperature threshold

        Args:
            temp (float): the current temperature
            trend (Literal["up","down","up-huge","down-huge"]): the trend of the temperature
        """
        if trend == "up-huge":
            self.set_pres(5)
        elif trend == "down-huge":
            if temp >= 5:
                self.set_pres(15)
            else:
                self.set_pres(3)
        else:
            self.set_pres(3)


class ITCs(ITC):
    """ Represents the ITC503 Temperature Controllers and provides a high-level interface for interacting with the instruments.

    There are two ITC503 incorporated in the setup, named up and down. The up one measures the temperature of the heat switch(up R1), PT2(up R2), leaving R3 no specific meaning. The down one measures the temperature of the sorb(down R1), POT LOW(down R2), POT HIGH(down R3).
    """

    def __init__(self, address_up="GPIB0::23::INSTR", address_down="GPIB0::24::INSTR", clear_buffer=True):
        self.itc_up = ITC503(address_up, clear_buffer=clear_buffer)
        self.itc_down = ITC503(address_down, clear_buffer=clear_buffer)

    def chg_display(self, itc_name, target):
        """
        This function is used to change the front display of the ITC503

        Parameters: itc_name (str): The name of the ITC503, "up" or "down" or "all" target (str):  'temperature
        setpoint', 'temperature 1', 'temperature 2', 'temperature 3', 'temperature error', 'heater',
        'heater voltage', 'gasflow', 'proportional band', 'integral action time', 'derivative action time',
        'channel 1 freq/4', 'channel 2 freq/4', 'channel 3 freq/4'.

        Returns:
        None
        """
        if itc_name == "all":
            self.itc_up.front_panel_display = target
            self.itc_down.front_panel_display = target
        elif itc_name == "up":
            self.itc_up.front_panel_display = target
        elif itc_name == "down":
            self.itc_down.front_panel_display = target

    def chg_pointer(self, itc_name, target: tuple):
        """
        used to change the pointer of the ITCs

        Parameters: itc_name (str): The name of the ITC503, "up" or "down" or "all" target (tuple): A tuple property
        to set pointers into tables for loading and examining values in the table, of format (x, y). The significance
        and valid values for the pointer depends on what property is to be read or set. The value for x and y can be
        in the range 0 to 128.

        Returns:
        None
        """
        if itc_name == "all":
            self.itc_up.pointer = target
            self.itc_down.pointer = target
        elif itc_name == "up":
            self.itc_up.pointer = target
        elif itc_name == "down":
            self.itc_down.pointer = target

    @property
    def temperature_set(self):
        return self.itc_down.temperature_setpoint

    @temperature_set.setter
    def temperature_set(self, temp):
        """
        set the target temperature for sample, as for other parts' temperature, use the methods for each ITC

        Args:
            temp (float): the target temperature
            itc_name (Literal["up","down","all"]): the ITC503 to set the temperature
        """
        self.itc_down.temperature_setpoint = temp

    def ramp_to_temperature_selective(self, temp, itc_name: Literal["up", "down"], P=None, I=None, D=None):
        """
        used to ramp the temperature of the ITCs, this method will wait for the temperature to stablize and thermalize for a certain time length
        """
        self.control_mode = ("RU", itc_name)
        if itc_name == "up":
            itc_here = self.itc_up
        if itc_name == "down":
            itc_here = self.itc_down
        itc_here.temperature_setpoint = temp
        if P is not None and I is not None and D is not None:
            itc_here.auto_pid = False
            itc_here.proportional_band = P
            itc_here.integral_action_time = I
            itc_here.derivative_action_time = D
        else:
            itc_here.auto_pid = True
        itc_here.heater_gas_mode = "AM"
        print(f"temperature setted to {temp}")

    @property
    def version(self):
        """ Returns the version of the ITC503. """
        return [self.itc_up.version, self.itc_down.version]

    @property
    def control_mode(self):
        """ Returns the control mode of the ITC503. """
        return [self.itc_up.control_mode, self.itc_down.control_mode]

    @control_mode.setter
    def control_mode(self, mode: Tuple[Literal["LU", "RU", "LL", "RL"], Literal["all", "up", "down"]]):
        """ Sets the control mode of the ITC503. A two-element list is required. The second elecment is "all" or "up"
        or "down" to specify which ITC503 to set."""
        if mode[1] == "all":
            self.itc_up.control_mode = mode[0]
            self.itc_down.control_mode = mode[0]
        elif mode[1] == "up":
            self.itc_up.control_mode = mode[0]
        elif mode[1] == "down":
            self.itc_down.control_mode = mode[0]

    @property
    def heater_gas_mode(self):
        """ Returns the heater gas mode of the ITC503. """
        return [self.itc_up.heater_gas_mode, self.itc_down.heater_gas_mode]

    @heater_gas_mode.setter
    def heater_gas_mode(self, mode: Tuple[Literal["MANUAL", "AM", "MA", "AUTO"], Literal["all", "up", "down"]]):
        """ Sets the heater gas mode of the ITC503. A two-element list is required. The second elecment is "all" or
        "up" or "down" to specify which ITC503 to set."""
        if mode[1] == "all":
            self.itc_up.heater_gas_mode = mode[0]
            self.itc_down.heater_gas_mode = mode[0]
        elif mode[1] == "up":
            self.itc_up.heater_gas_mode = mode[0]
        elif mode[1] == "down":
            self.itc_down.heater_gas_mode = mode[0]

    @property
    def heater_power(self):
        """ Returns the heater power of the ITC503. """
        return [self.itc_up.heater, self.itc_down.heater]

    @property
    def heater_voltage(self):
        """ Returns the heater voltage of the ITC503. """
        return [self.itc_up.heater_voltage, self.itc_down.heater_voltage]

    @property
    def gas_flow(self):
        """ Returns the gasflow of the ITC503. """
        return [self.itc_up.gasflow, self.itc_down.gasflow]

    @property
    def proportional_band(self):
        """ Returns the proportional band of the ITC503. """
        return [self.itc_up.proportional_band, self.itc_down.proportional_band]

    @property
    def integral_action_time(self):
        """ Returns the integral action time of the ITC503. """
        return [self.itc_up.integral_action_time, self.itc_down.integral_action_time]

    @property
    def derivative_action_time(self):
        """ Returns the derivative action time of the ITC503. """
        return [self.itc_up.derivative_action_time, self.itc_down.derivative_action_time]

    def set_pid(self, pid: dict, mode: Literal["all", "up", "down"] = "down"):
        """ Sets the PID of the ITC503. A three-element list is required. The second elecment is "all" or "up" or "down" to specify which ITC503 to set.
        The P,I,D here are the proportional band (K), integral action time (min), and derivative action time(min), respectively.
        """
        self.control_mode = ("RU", mode)
        if mode == "all":
            self.itc_up.proportional_band = pid["P"]
            self.itc_down.proportional_band = pid["P"]
            self.itc_up.integral_action_time = pid["I"]
            self.itc_down.integral_action_time = pid["I"]
            self.itc_up.derivative_action_time = pid["D"]
            self.itc_down.derivative_action_time = pid["D"]
        if mode == "up":
            self.itc_up.proportional_band = pid["P"]
            self.itc_up.integral_action_time = pid["I"]
            self.itc_up.derivative_action_time = pid["D"]
        if mode == "down":
            self.itc_down.proportional_band = pid["P"]
            self.itc_down.integral_action_time = pid["I"]
            self.itc_down.derivative_action_time = pid["D"]

        if self.itc_up.proportional_band == 0:
            return ""
        return f"{mode} PID(power percentage): 100*(E/{pid['P']}+E/{pid['P']}*t/60{pid['I']}-dE*60{pid['D']}/{pid['P']}), [K,min,min]"

    @property
    def auto_pid(self):
        """ Returns the auto pid of the ITC503. """
        return [self.itc_up.auto_pid, self.itc_down.auto_pid]

    @auto_pid.setter
    def auto_pid(self, mode):
        """ Sets the auto pid of the ITC503. A two-element list is required. The second elecment is "all" or "up" or
        "down" to specify which ITC503 to set."""
        if mode[1] == "all":
            self.itc_up.auto_pid = mode[0]
            self.itc_down.auto_pid = mode[0]
        elif mode[1] == "up":
            self.itc_up.auto_pid = mode[0]
        elif mode[1] == "down":
            self.itc_down.auto_pid = mode[0]

    @property
    def sweep_status(self):
        """ Returns the sweep status of the ITC503. """
        return [self.itc_up.sweep_status, self.itc_down.sweep_status]

    @property
    def temperature_setpoint(self):
        """ Returns the temperature setpoint of the ITC503. """
        return [self.itc_up.temperature_setpoint, self.itc_down.temperature_setpoint]

    @temperature_setpoint.setter
    def temperature_setpoint(self, temperature):
        """ Sets the temperature setpoint of the ITC503. A two-element list is required. The second elecment is "all"
        or "up" or "down" to specify which ITC503 to set."""
        if temperature[1] == "all":
            self.itc_up.temperature_setpoint = temperature[0]
            self.itc_down.temperature_setpoint = temperature[0]
        elif temperature[1] == "up":
            self.itc_up.temperature_setpoint = temperature[0]
        elif temperature[1] == "down":
            self.itc_down.temperature_setpoint = temperature[0]

    @property
    def temperatures(self):
        """ Returns the temperatures of the whole device as a dict. """
        return {"sw": self.itc_up.temperature_1, "pt2": self.itc_up.temperature_2, "sorb": self.itc_down.temperature_1,
                "pot_low": self.itc_down.temperature_2, "pot_high": self.itc_down.temperature_3}

    @property
    def temperature(self):
        """ Returns the precise temperature of the sample """
        if self.temperatures["pot_high"] < 1.9:
            return self.temperatures["pot_low"]
        elif self.temperatures["pot_high"] >= 1.9:
            return self.temperatures["pot_high"]
