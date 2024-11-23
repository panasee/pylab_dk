#!/usr/bin/env python

import numpy as np
from qcodes.instrument.visa import VisaInstrument
from qcodes.parameters import Parameter
from qcodes.utils import validators as vals


class MercuryITC(VisaInstrument):
    """
    This is a qcodes driver for the Oxford MercuryITC.

    Todo::
    - Confirm the loop relation, the pressure and needle valve
    - Necessity of "?" in the query commands?
    - Implement the flow control and pressure control loop
    - store the default pids in restore_default method

    How to use:
    - To read the probe temperature:
        self.probe_temp()
    - To set a temperature, and wait until it is reached:
        self.probe_temp(T)
    - To read/set the heater rate (K/min):
        self.heater_rate()

    """
    # declare the members for convenience of IDE
    probe_temp_addr: str
    probe_heater_addr: str
    pressure_addr: str
    needle_valve_addr: str
    vti_temp_addr: str
    vti_heater_addr: str

    def __init__(self, name="MercuryITC",
                 address="TCPIP0::10.97.27.13::7020::SOCKET",
                 probe_temp_addr='DEV:DB8.T1:TEMP',
                 probe_heater_addr='DEV:DB3.H1:HTR',
                 pressure_addr='DEV:DB5.P1:PRES',
                 needle_valve_addr='DEV:DB4.G1:AUX',
                 vti_temp_addr='DEV:MB1.T1:TEMP',
                 vti_heater_addr='DEV:MB0.H1:HTR', **kwargs):
        """
        Args:
            name (str): name of the instrument
            address (str): The address of the instrument
            addresses of the iTC modules (str):
        """
        super().__init__(name, address, terminator='\n',
                         **kwargs)
        # initialize the variables for calculating the VTI temperature
        self.vti_list = None
        self.probe_list = None
        # Assign all the module addresses to the class
        self.__dict__.update(locals())
        self.pres_loop_addr = self.pressure_addr.replace("PRES", "TEMP")
        # noinspection PyUnboundLocalVariable
        del self.self

        # Check all sensors are present, otherwise output an error
        self.modules = [self.probe_heater_addr, self.probe_temp_addr, self.pressure_addr, self.needle_valve_addr,
                        self.vti_temp_addr, self.vti_heater_addr]
        for mod in self.modules:
            self.nick = self.ask('READ:' + mod + ':NICK?')
            if self.nick[-7:] == 'INVALID':
                raise Exception("Input the correct modules addresses: " + str(self.ask('READ:SYS:CAT')))

        # Probe temperature parameters
        # Assign probe heater, vti heater and needle_valve to the temperature control loop.      

        self.ask('SET:' + self.probe_temp_addr + ':LOOP:HTR:' + self.probe_heater_addr.split(':')[1])
        self.ask('SET:' + self.pressure_addr + ':LOOP:AUX:' + self.needle_valve_addr.split(':')[1])
        self.ask('SET:' + self.vti_temp_addr + ':LOOP:HTR:' + self.vti_heater_addr.split(':')[1])

        self.probe_temp: Parameter = self.add_parameter('probe_temp',
                                                        label='Probe Temperature',
                                                        unit='K',
                                                        docstring='Temperature of the probe sensor',
                                                        get_cmd="READ:" + self.probe_temp_addr + ":SIG:TEMP?",
                                                        get_parser=self._temp_parser,
                                                        set_cmd=lambda x: self.temp_setpoint(x),
                                                        vals=vals.Numbers(min_value=1.3, max_value=300)
                                                        )
        self.temp_setpoint: Parameter = self.add_parameter('temp_setpoint',
                                                           label='Heater Temperature Setpoint',
                                                           unit='K',
                                                           docstring='Temperature setpoint for the heater',
                                                           get_cmd='READ:' + self.probe_temp_addr + ':LOOP:TSET?',
                                                           get_parser=self._temp_parser,
                                                           set_cmd=lambda x: self.ask(
                                                               'SET:' + self.probe_temp_addr + f':LOOP:TSET:{x}')
                                                           )
        self.probe_heater: Parameter = self.add_parameter('probe_heater',
                                                          label='Probe Heater Percentage',
                                                          docstring='Percentage of the probe heater',
                                                          get_cmd="READ:" + self.probe_heater_addr + ":SIG:PERC?",
                                                          get_parser=self._perc_parser,
                                                          set_cmd=lambda x: self.probe_heater_setpoint(x),
                                                          vals=vals.Numbers(min_value=0, max_value=100)
                                                          )
        self.probe_heater_setpoint: Parameter = self.add_parameter('probe_heater_setpoint',
                                                                   label='Heater Percentage Setpoint',
                                                                   docstring='Percentage setpoint for the heater',
                                                                   get_cmd='READ:' + self.probe_temp_addr + ':LOOP:HSET?',
                                                                   get_parser=self._float_parser_nounits,
                                                                   set_cmd=lambda x: self.ask(
                                                                       'SET:' + self.probe_temp_addr + f':LOOP:HSET:{x}')
                                                                   )

        self.vti_temp: Parameter = self.add_parameter('vti_temp',
                                                      label='VTI Temperature',
                                                      unit='K',
                                                      docstring='Temperature of the VTI',
                                                      get_cmd="READ:" + self.vti_temp_addr + ":SIG:TEMP?",
                                                      get_parser=self._temp_parser,
                                                      set_cmd=lambda x: self.vti_temp_setpoint(x),
                                                      )
        self.vti_temp_setpoint: Parameter = self.add_parameter('vti_temp_setpoint',
                                                               label='VTI heater Temperature Setpoint',
                                                               unit='K',
                                                               docstring='Temperature setpoint for the VTI heater',
                                                               get_cmd='READ:' + self.vti_temp_addr + ':LOOP:TSET?',
                                                               get_parser=self._temp_parser,
                                                               set_cmd=lambda x: self.ask(
                                                                   'SET:' + self.vti_temp_addr + f':LOOP:TSET:{x}')
                                                               )
        self.vti_heater: Parameter = self.add_parameter('vti_heater',
                                                        label='VTI Heater Percentage',
                                                        docstring='Percentage of the vti heater',
                                                        get_cmd="READ:" + self.vti_heater_addr + ":SIG:PERC?",
                                                        get_parser=self._perc_parser,
                                                        set_cmd=lambda x: self.probe_heater_setpoint(x),
                                                        vals=vals.Numbers(min_value=0, max_value=100)
                                                        )
        self.vti_heater_setpoint: Parameter = self.add_parameter('vti_heater_setpoint',
                                                                 label='Heater Percentage Setpoint',
                                                                 docstring='Percentage setpoint for the heater',
                                                                 get_cmd='READ:' + self.vti_temp_addr + ':LOOP:HSET?',
                                                                 get_parser=self._float_parser_nounits,
                                                                 set_cmd=lambda x: self.ask(
                                                                     'SET:' + self.vti_temp_addr + f':LOOP:HSET:{x}')
                                                                 )

        self.pressure: Parameter = self.add_parameter('pressure',
                                                      label='pressure',
                                                      unit='mbar',
                                                      get_cmd="READ:" + self.pressure_addr + ":SIG:PRES?",
                                                      get_parser=self._pressure_parser,
                                                      set_cmd=lambda x: self.pressure_setpoint(x)
                                                      )
        self.pressure_setpoint: Parameter = self.add_parameter('pressure_setpoint',
                                                               label='pressure_setpoint',
                                                               unit='mB',
                                                               docstring='pressure set point for the VTI needle valve',
                                                               get_cmd="READ:" + self.pres_loop_addr + ":LOOP:TSET?",
                                                               get_parser=self._pressure_parser,
                                                               set_cmd=lambda x: self.ask(
                                                                   'SET:' + self.pres_loop_addr + f':LOOP:TSET:{x}'),
                                                               vals=vals.Numbers(min_value=1, max_value=20)
                                                               )

        self.gas_flow: Parameter = self.add_parameter('gas_flow',
                                                      label='Gas flow in percent',
                                                      get_cmd='READ:' + self.needle_valve_addr + ':SIG:PERC?',
                                                      get_parser=self._perc_parser,
                                                      set_cmd=lambda x: self.gas_flow_setpoint(x)
                                                      )
        self.gas_flow_setpoint: Parameter = self.add_parameter('gas_flow_setpoint',
                                                               label='Gas flow setpoint in percent',
                                                               get_cmd='READ:' + self.pressure_addr + ':LOOP:FSET?',
                                                               get_parser=self._float_parser_nounits,
                                                               set_cmd=lambda x: self.ask(
                                                                   'SET:' + self.pressure_addr + f':LOOP:FSET:' + str(
                                                                       x)),
                                                               vals=vals.Numbers(min_value=0, max_value=100)
                                                               )

        self.temp_loop_P: Parameter = self.add_parameter('temp_loop_P',
                                                         label='loop P',
                                                         get_cmd='READ:' + self.probe_temp_addr + ':LOOP:P?',
                                                         get_parser=self._float_parser_nounits,
                                                         set_cmd=lambda x: self.ask(
                                                             'SET:' + self.probe_temp_addr + f':LOOP:P:{x}'),
                                                         )
        self.temp_loop_I: Parameter = self.add_parameter('temp_loop_I',
                                                         label='loop I',
                                                         get_cmd='READ:' + self.probe_temp_addr + ':LOOP:I?',
                                                         get_parser=self._float_parser_nounits,
                                                         set_cmd=lambda x: self.ask(
                                                             'SET:' + self.probe_temp_addr + f':LOOP:I:{x}'),
                                                         )
        self.temp_loop_D: Parameter = self.add_parameter('temp_loop_D',
                                                         label='loop D',
                                                         get_cmd='READ:' + self.probe_temp_addr + ':LOOP:D?',
                                                         get_parser=self._float_parser_nounits,
                                                         set_cmd=lambda x: self.ask(
                                                             'SET:' + self.probe_temp_addr + f':LOOP:D:{x}'),
                                                         )
        self.temp_PID_control: Parameter = self.add_parameter('temp_PID_control',
                                                              label='PID controlled mode',
                                                              get_cmd='READ:' + self.probe_temp_addr + ':LOOP:ENAB?',
                                                              get_parser=self._str_parser,
                                                              set_cmd=lambda x: self.ask(
                                                                  'SET:' + self.probe_temp_addr + ':LOOP:ENAB:' + str(
                                                                      x))
                                                              )
        self.temp_PID_fromtable: Parameter = self.add_parameter('temp_PID_fromtable',
                                                                label='PID from table',
                                                                get_cmd='READ:' + self.probe_temp_addr + ':LOOP:PIDT?',
                                                                get_parser=self._str_parser,
                                                                set_cmd=lambda x: self.ask(
                                                                    'SET:' + self.probe_temp_addr + ':LOOP:PIDT:' + str(
                                                                        x))
                                                                )
        self.probe_temp_ramp_mode: Parameter = self.add_parameter('probe_temp_ramp_mode',
                                                                  label='Probe Temperature Ramp Mode',
                                                                  get_cmd='READ:' + self.probe_temp_addr + ':LOOP:RENA?',
                                                                  get_parser=self._str_parser,
                                                                  set_cmd=lambda x: self.ask(
                                                                      'SET:' + self.probe_temp_addr + ':LOOP:RENA:' + str(
                                                                          x))
                                                                  )
        self.probe_ramp_rate: Parameter = self.add_parameter('probe_ramp_rate',
                                                             label='Probe Temperature Ramp Rate in K/min',
                                                             unit='K/min',
                                                             docstring='Temperature setpoint for the heater',
                                                             get_cmd='READ:' + self.probe_temp_addr + ':LOOP:RSET?',
                                                             get_parser=self._rate_parser,
                                                             set_cmd=lambda x: self.ask(
                                                                 'SET:' + self.probe_temp_addr + f':LOOP:RSET:{x}')
                                                             )

        self.vti_temp_loop_P: Parameter = self.add_parameter('vti_temp_loop_P',
                                                             label='vti loop P',
                                                             get_cmd='READ:' + self.vti_temp_addr + ':LOOP:P?',
                                                             get_parser=self._float_parser_nounits,
                                                             set_cmd=lambda x: self.ask(
                                                                 'SET:' + self.vti_temp_addr + f':LOOP:P:{x}'),
                                                             )
        self.vti_temp_loop_I: Parameter = self.add_parameter('vti_temp_loop_I',
                                                             label='loop I',
                                                             get_cmd='READ:' + self.vti_temp_addr + ':LOOP:I?',
                                                             get_parser=self._float_parser_nounits,
                                                             set_cmd=lambda x: self.ask(
                                                                 'SET:' + self.vti_temp_addr + f':LOOP:I:{x}'),
                                                             )
        self.vti_temp_loop_D: Parameter = self.add_parameter('vti_temp_loop_D',
                                                             label='loop D',
                                                             get_cmd='READ:' + self.vti_temp_addr + ':LOOP:D?',
                                                             get_parser=self._float_parser_nounits,
                                                             set_cmd=lambda x: self.ask(
                                                                 'SET:' + self.vti_temp_addr + f':LOOP:D:{x}'),
                                                             )
        self.vti_temp_PID_control: Parameter = self.add_parameter('vti_temp_PID_control',
                                                                  label='VTI PID controlled mode',
                                                                  get_cmd='READ:' + self.vti_temp_addr + ':LOOP:ENAB?',
                                                                  get_parser=self._str_parser,
                                                                  set_cmd=lambda x: self.ask(
                                                                      'SET:' + self.vti_temp_addr + ':LOOP:ENAB:' + str(
                                                                          x))
                                                                  )
        self.vti_temp_PID_fromtable: Parameter = self.add_parameter('vti_temp_PID_fromtable',
                                                                    label='VTI PID from table',
                                                                    get_cmd='READ:' + self.vti_temp_addr + ':LOOP:PIDT?',
                                                                    get_parser=self._str_parser,
                                                                    set_cmd=lambda x: self.ask(
                                                                        'SET:' + self.vti_temp_addr + ':LOOP:PIDT:' + str(
                                                                            x))
                                                                    )
        self.vti_temp_ramp_mode: Parameter = self.add_parameter('vti_temp_ramp_mode',
                                                                label='VTI Temperature Ramp Mode',
                                                                get_cmd='READ:' + self.vti_temp_addr + ':LOOP:RENA?',
                                                                get_parser=self._str_parser,
                                                                set_cmd=lambda x: self.ask(
                                                                    'SET:' + self.vti_temp_addr + ':LOOP:RENA:' + str(
                                                                        x))
                                                                )
        self.vti_ramp_rate: Parameter = self.add_parameter('vti_ramp_rate',
                                                           label='VTI Temperature Ramp Rate in K/min',
                                                           unit='K/min',
                                                           docstring='VTI temperature setpoint for the VTI heater',
                                                           get_cmd='READ:' + self.vti_temp_addr + ':LOOP:RSET?',
                                                           get_parser=self._rate_parser,
                                                           set_cmd=lambda x: self.ask(
                                                               'SET:' + self.vti_temp_addr + f':LOOP:RSET:{x}')
                                                           )

        self.pres_loop_P: Parameter = self.add_parameter('pres_loop_P',
                                                         label='pressure loop P',
                                                         get_cmd='READ:' + self.pressure_addr + ':LOOP:P?',
                                                         get_parser=self._float_parser_nounits,
                                                         set_cmd=lambda x: self.ask(
                                                             'SET:' + self.pressure_addr + f':LOOP:P:{x}'),
                                                         )
        self.pres_loop_I: Parameter = self.add_parameter('pres_loop_I',
                                                         label='pressure loop I',
                                                         get_cmd='READ:' + self.pressure_addr + ':LOOP:I?',
                                                         get_parser=self._float_parser_nounits,
                                                         set_cmd=lambda x: self.ask(
                                                             'SET:' + self.pressure_addr + f':LOOP:I:{x}'),
                                                         )
        self.pres_loop_D: Parameter = self.add_parameter('pres_loop_D',
                                                         label='pressure loop D',
                                                         get_cmd='READ:' + self.pressure_addr + ':LOOP:D?',
                                                         get_parser=self._float_parser_nounits,
                                                         set_cmd=lambda x: self.ask(
                                                             'SET:' + self.pressure_addr + f':LOOP:D:{x}'),
                                                         )
        self.pres_PID_control: Parameter = self.add_parameter('pres_PID_control',
                                                              label='PID controlled mode',
                                                              get_cmd='READ:' + self.pressure_addr + ':LOOP:ENAB?',
                                                              get_parser=self._str_parser,
                                                              set_cmd=lambda x: self.ask(
                                                                  'SET:' + self.pressure_addr + ':LOOP:ENAB:' + str(x))
                                                              )
        self.pres_PID_fromtable: Parameter = self.add_parameter('pres_PID_fromtable',
                                                                label='PID from table',
                                                                get_cmd='READ:' + self.pressure_addr + ':LOOP:PIDT?',
                                                                get_parser=self._str_parser,
                                                                set_cmd=lambda x: self.ask(
                                                                    'SET:' + self.pressure_addr + ':LOOP:PIDT:' + str(
                                                                        x))
                                                                )

        self.connect_message()

        # set default ramp rates (K/min)
        self.probe_ramp_rate(5.0)
        self.vti_ramp_rate(5.0)

    # set pid as a whole property
    @property
    def temp_PID(self):
        return self.temp_loop_P(), self.temp_loop_I(), self.temp_loop_D()

    @temp_PID.setter
    def temp_PID(self, value: tuple):
        self.temp_loop_P(value[0])
        self.temp_loop_I(value[1])
        self.temp_loop_D(value[2])

    @property
    def vti_temp_PID(self):
        return self.vti_temp_loop_P(), self.vti_temp_loop_I(), self.vti_temp_loop_D()

    @vti_temp_PID.setter
    def vti_temp_PID(self, value: tuple):
        self.vti_temp_loop_P(value[0])
        self.vti_temp_loop_I(value[1])
        self.vti_temp_loop_D(value[2])

    @property
    def pres_PID(self):
        return self.pres_loop_P(), self.pres_loop_I(), self.pres_loop_D()

    @pres_PID.setter
    def pres_PID(self, value: tuple):
        self.pres_loop_P(value[0])
        self.pres_loop_I(value[1])
        self.pres_loop_D(value[2])

    # Parsers
    @staticmethod
    def _float_parser_nounits(value: str):
        return float(value.split(':')[-1])  # Return the number after the equals as a float

    @staticmethod
    def _str_parser(value: str):
        return value.split(':')[-1]  # Return the number after the : as a string

    @staticmethod
    def _pressure_parser(value: str):
        return float(value.split(':')[-1][:-2])  # Return the number after the : as a float

    @staticmethod
    def _rate_parser(value: str):
        return float(value.split(':')[-1][:-3])  # Return the number after the : as a float

    @staticmethod
    def _temp_parser(value: str):
        return float(value.split(':')[-1][:-1])  # Return the number after the : as a float

    @staticmethod
    def _powr_parser(value: str):
        return float(value.split(':')[-1][:-1])  # Return the number after the : as a float

    @staticmethod
    def _perc_parser(value: str):
        return float(value.split(':')[-1][:-1])  # Return the number after the : as a float

    # methods
    def restore_default_pid(self):
        self.temp_PID = (5.0, 1.0, 0.0)
        self.vti_temp_PID = (10.0, 1.0, 0.0)
        self.pres_PID = (0.5, 0.5, 0.0)

    def calculate_vti_temp(self, probe_temp):
        """
        Function to calculate the optimum VTI temperature set point as a function of the probe temperature setpoint
        """
        self.vti_list = np.array([1.3, 1.55, 5.9, 9.8, 19.5, 48.0, 97.0, 195.0, 295.0])
        self.probe_list = np.array([1.5, 1.7, 6, 10, 20, 50, 100, 200, 300])
        vti_temp_target = np.interp(probe_temp, self.probe_list, self.vti_list)
        return vti_temp_target

    def rapid_cooldown_to_base(self):
        self.vti_temp_setpoint(1.3)
        self.temp_setpoint(1.5)
        self.vti_temp_ramp_mode('OFF')
        self.probe_temp_ramp_mode('OFF')
