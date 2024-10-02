# this file requires the API WJ_API.dll to work
# by default it will look for the dll in the local DB directory
# for detailed information on the API see the WJ_API.h declarations
# make sure to use same architecture for the dll and python(32/64 bit here)
import functools
import platform
import time
from typing import Optional

from pathlib import Path
import ctypes
from pylab_dk import LOCAL_DB_PATH
from pylab_dk.constants import print_progress_bar


def avoid_running(method):
    """
    Decorator to avoid running the function if the rotator is already running
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if self.if_running():
            print('Rotator is already running')
            return
        return method(self, *args, **kwargs)

    return wrapper


class RotatorProbe:
    dll_path = Path(LOCAL_DB_PATH / 'WJ_API.dll')

    # currently only one axis is used, so all methods are for one axis (axis_num: 1)
    def __init__(self, *, port: Optional[int] = None):
        assert platform.system().lower() == 'windows', 'This module only works on Windows'
        self._max_axes = 2  # actually only 1 axis is used
        self.axis_num = 1
        self._upper_limit = 365
        self._lower_limit = -5
        self._to_zero_spd = -15
        self.speed = 2
        self._pulse_ratio = 50000  # 360 degrees / pulses
        self.serial_port = 0  # default serial port for usb
        if not self.dll_path.exists():
            raise FileNotFoundError(f'WJ_API.dll not found at {self.dll_path}')
        self.wj_api = ctypes.WinDLL(str(self.dll_path))  # can pass Path-like after Python 3.12
        if port is not None:
            self.status = self.connect(port)
        else:
            self.status = self.connect()

        # define return type and arguments types for functions
        self.__declare_functions()

    def __del__(self):
        self.exit()

    def print_info(self):
        """print all info about the rotator"""
        print(f"Rotator is connected to serial port: {self.serial_port}")
        print(f"Rotator is running: {self.if_running()}")
        print(f"Rotator current angle: {self.curr_angle()}")
        print(f"Rotator current speed: {self.spd()}")

    def connect(self, serial_port: Optional[int] = None):
        """
        Connects to the rotator
        """
        if serial_port is not None:
            self.serial_port = serial_port
        print('Connecting Status:', status := self.wj_api.WJ_Open(self.serial_port))
        return status

    def exit(self):
        """
        Disconnects from the rotator
        """
        self.wj_api.WJ_Close()

    def if_running(self, *, axis_no: Optional[int] = None) -> bool:
        """
        Returns if the rotator is running
        """
        if axis_no is None:
            axis_no = self.axis_num
        status = ctypes.c_int()
        self.wj_api.WJ_Get_Axis_Status(ctypes.c_int(axis_no), ctypes.byref(status))
        return status.value == 1

    def curr_angle(self, *, axis_no: Optional[int] = None) -> float:
        """
        Returns the current angle of the rotator
        """
        if axis_no is None:
            axis_no = self.axis_num
        pulses = ctypes.c_int()
        self.wj_api.WJ_Get_Axis_Pulses(ctypes.c_int(axis_no), ctypes.byref(pulses))
        angle = float(pulses.value) / self._pulse_ratio * 360
        # embed angle overflow control here
        if self._lower_limit <= angle <= self._upper_limit:
            self.emergency_stop()
            print("Rotator reached its limit, emergency stop triggered")
        return angle

    def spd(self, *, axis_no: Optional[int] = None) -> int:
        """
        Returns the current speed of the rotator
        """
        if axis_no is None:
            axis_no = self.axis_num
        speed = ctypes.c_int()
        self.wj_api.WJ_Get_Axis_Vel(ctypes.c_int(axis_no), ctypes.byref(speed))
        self.speed = speed.value
        return speed.value

    @avoid_running
    def set_spd(self, value, *, axis_no: Optional[int] = None):
        """
        Sets the speed of the rotator
        """
        if axis_no is None:
            axis_no = self.axis_num
        self.wj_api.WJ_Set_Axis_Vel(ctypes.c_int(axis_no), ctypes.c_int(value))
        self.speed = value
        print("Speed set to: ", value)

    @avoid_running
    def ramp_angle(self, angle, *, progress=False, axis_no=None, wait=False) -> None:
        """
        Moves the rotator to the specified angle

        Args:
            angle (in degrees, 360): the angle to move to
            axis_no: the axis number (1)
            wait: whether to wait for the motion to finish
            progress: (overwrite wait if True)whether to continuously monitor the motion
        """
        if axis_no is None:
            axis_no = self.axis_num
        initial_angle = self.curr_angle(axis_no=axis_no)
        delta_angle = angle - initial_angle
        delta_pulse = int(delta_angle * self._pulse_ratio / 360)
        self.wj_api.WJ_Move_Axis_Pulses(ctypes.c_int(axis_no), ctypes.c_int(delta_pulse))
        if wait or progress:
            while self.if_running(axis_no=axis_no):
                time.sleep(1)
                if progress:
                    print_progress_bar(self.curr_angle(axis_no=axis_no) - initial_angle, angle - initial_angle)

    def emergency_stop(self, axis_no: int = 1):
        """
        Stops the rotator immediately
        """
        self.wj_api.WJ_Move_Axis_Emergency_Stop(ctypes.c_int(axis_no))

    def __declare_functions(self):
        """
        Declares used functions from the API
        """
        self.wj_api.WJ_Open.argtypes = [ctypes.c_int]
        self.wj_api.WJ_Open.restype = ctypes.c_int

        self.wj_api.WJ_Close.argtypes = []
        self.wj_api.WJ_Close.restype = ctypes.c_int

        # Query Commands
        self.wj_api.WJ_Get_Axis_Acc.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_Get_Axis_Acc.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axis_Dec.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_Get_Axis_Dec.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axis_Vel.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_Get_Axis_Vel.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axis_Subdivision.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_Get_Axis_Subdivision.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axis_Status.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_Get_Axis_Status.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axes_Status.argtypes = [ctypes.POINTER(ctypes.c_int * self.__max_axes)]
        self.wj_api.WJ_Get_Axes_Status.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axis_Pulses.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_Get_Axis_Pulses.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axes_Pulses.argtypes = [ctypes.POINTER(ctypes.c_int * self.__max_axes)]
        self.wj_api.WJ_Get_Axes_Pulses.restype = ctypes.c_int

        self.wj_api.WJ_Get_Axes_Num.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_Get_Axes_Num.restype = ctypes.c_int

        # Motion Commands
        self.wj_api.WJ_Move_Axis_Pulses.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Move_Axis_Pulses.restype = ctypes.c_int

        self.wj_api.WJ_Move_Axes_Pulses.argtypes = [ctypes.POINTER(ctypes.c_int * self.__max_axes)]
        self.wj_api.WJ_Move_Axes_Pulses.restype = ctypes.c_int

        self.wj_api.WJ_Move_Axis_Vel.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Move_Axis_Vel.restype = ctypes.c_int

        self.wj_api.WJ_Move_Axes_Vel.argtypes = [ctypes.POINTER(ctypes.c_int * self.__max_axes)]
        self.wj_api.WJ_Move_Axes_Vel.restype = ctypes.c_int

        self.wj_api.WJ_Move_Axis_Emergency_Stop.argtypes = [ctypes.c_int]
        self.wj_api.WJ_Move_Axis_Emergency_Stop.restype = ctypes.c_int

        self.wj_api.WJ_Move_Axis_Slow_Stop.argtypes = [ctypes.c_int]
        self.wj_api.WJ_Move_Axis_Slow_Stop.restype = ctypes.c_int

        self.wj_api.WJ_Move_Axis_Home.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Move_Axis_Home.restype = ctypes.c_int

        # Setting Commands
        self.wj_api.WJ_Set_Axis_Acc.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Set_Axis_Acc.restype = ctypes.c_int

        self.wj_api.WJ_Set_Axis_Dec.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Set_Axis_Dec.restype = ctypes.c_int

        self.wj_api.WJ_Set_Axis_Vel.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Set_Axis_Vel.restype = ctypes.c_int

        self.wj_api.WJ_Set_Axis_Subdivision.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Set_Axis_Subdivision.restype = ctypes.c_int

        self.wj_api.WJ_Set_Axis_Slow_Stop.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Set_Axis_Slow_Stop.restype = ctypes.c_int

        self.wj_api.WJ_Set_Led_Twinkle.argtypes = []
        self.wj_api.WJ_Set_Led_Twinkle.restype = ctypes.c_int

        self.wj_api.WJ_Set_Axis_Pulses_Zero.argtypes = [ctypes.c_int]
        self.wj_api.WJ_Set_Axis_Pulses_Zero.restype = ctypes.c_int

        self.wj_api.WJ_Set_Default.argtypes = []
        self.wj_api.WJ_Set_Default.restype = ctypes.c_int

        self.wj_api.WJ_Set_Move_Axis_Vel_Acc.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Set_Move_Axis_Vel_Acc.restype = ctypes.c_int

        self.wj_api.WJ_Set_Axis_Home_Pulses.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_Set_Axis_Home_Pulses.restype = ctypes.c_int

        # IO Commands
        self.wj_api.WJ_IO_Output.argtypes = [ctypes.c_int, ctypes.c_int]
        self.wj_api.WJ_IO_Output.restype = ctypes.c_int

        self.wj_api.WJ_IO_Input.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.wj_api.WJ_IO_Input.restype = ctypes.c_int
