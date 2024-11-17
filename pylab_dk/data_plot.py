#!/usr/bin/env python
"""This module is responsible for processing and plotting the data"""

import importlib
import copy
import json
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Optional, Literal

from matplotlib.axes import Axes
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd

import pylab_dk.pltconfig.color_preset as colors
from pylab_dk.constants import cm_to_inch, factor, default_plot_dict, is_notebook, hex_to_rgb
from pylab_dk.data_process import DataProcess


class DataPlot(DataProcess):
    """
    This class is responsible for processing and plotting the data.
    Two series of functions will be provided, one is for automatic plotting, the other will provide dataframe or other data structures for manual plotting
    """
    # define static variables
    legend_font: dict
    """A constant dict used to set the font of the legend in the plot"""

    class PlotParam:
        """
        This class is used to store the parameters for the plot
        """

        def __init__(self, *dims: int) -> None:
            """
            initialize the PlotParam

            Args:
            - no_of_figs: the number of figures to be plotted
            """
            self.shape = dims
            self.params_list = self._create_params_list(dims)
            # define a tmp params used for temporary storage, especially in class methods for convenience
            self.tmp = copy.deepcopy(default_plot_dict)

        def _create_params_list(self, dims: tuple[int, ...]) -> list[dict] | list[any]:
            """
            create the list of parameters for the plot

            Args:
            - dims: the dimensions of the parameters
            """
            if len(dims) == 1:
                return [copy.deepcopy(default_plot_dict) for _ in range(dims[0])]
            else:
                return [self._create_params_list(dims[1:]) for _ in range(dims[0])]

        def _get_subarray(self, array, index: tuple[int, ...]) -> list[dict]:
            """
            get the subarray of the parameters for the plot assigned by the index
            """
            if len(index) == 1:
                return array[index[0]]
            else:
                return self._get_subarray(array[index[0]], index[1:])

        def _set_subarray(self, array, index: tuple[int, ...], target_dict: dict) -> None:
            """
            set the subarray of the parameters for the plot assignated by the index
            """
            if len(index) == 1:
                array[index[0]] = copy.deepcopy(target_dict)
            else:
                self._set_subarray(array[index[0]], index[1:], target_dict)

        def _flatten(self, lst):
            """
            Flatten a multi-dimensional list using recursion
            """
            return [item for sublist in lst for item in
                    (self._flatten(sublist) if isinstance(sublist, list) else [sublist])]

        def __getitem__(self, index: tuple[int, ...] | int) -> dict:
            """
            get the parameters for the plot assignated by the index

            Args:
            - index: the index of the figure to be get
            """
            if isinstance(index, int):
                flat_list = self._flatten(self.params_list)
                return flat_list[index]
            result = self._get_subarray(self.params_list, index)
            while isinstance(result, list) and len(result) == 1:
                result = result[0]
            return result

        def __setitem__(self, index: tuple[int, ...] | int, value):
            if isinstance(index, int):
                index = (index,)
            self._set_subarray(self.params_list, index, value)

    def __init__(self, proj_name: str, *, no_params: tuple[int] | int = 4, usetex: bool = False, usepgf: bool = False,
                 if_folder_create=True) -> None:
        """
        Initialize the FileOrganizer and load the settings for matplotlib saved in another file
        
        Args:
        - proj_name: the name of the project
        - no_params: the number of params to be initiated (default:4) 
        - usetex: whether to use the TeX engine to render text
        - usepgf: whether to use the pgf backend
        - if_folder_create: whether to create the folder for all the measurements in project
        """
        super().__init__(proj_name)
        self.plot_types: list[list[str]] = []
        DataPlot.load_settings(usetex, usepgf)
        self.create_folder("plot")
        self.unit = {"I": "A", "V": "V", "R": "Ohm", "T": "K", "B": "T", "f": "Hz"}
        # params here are mainly used for internal methods
        self.params = DataPlot.PlotParam(no_params)
        self.live_dfs: list[list[list[go.Scatter]]] = []
        self.go_f: Optional[go.FigureWidget] = None
        if if_folder_create:
            self.assign_folder()

        self._stop_event = threading.Event()
        self._thread = None

    def assign_folder(self, folder_name: str = None) -> None:
        """ Assign the folder for the measurements """
        if folder_name is not None:
            self.create_folder(f"plot/{folder_name}")
        else:
            for i in self.query_proj()["measurements"]:
                self.create_folder(f"plot/{i}")

    @staticmethod
    def get_unit_factor_and_texname(unit: str) -> tuple[float, str]:
        """
        Used in plotting, to get the factor and the TeX name of the unit
        
        Args:
        - unit: the unit name string (like: uA)
        """
        _factor = factor(unit)
        if unit[0] == "u":
            namestr = rf"$\mathrm{{\mu {unit[1:]}}}$".replace("Ohm", r"\Omega").replace("Omega", r"\Omega")
        else:
            namestr = rf"$\mathrm{{{unit}}}$".replace("Ohm", r"\Omega").replace("Omega", r"\Omega")
        return _factor, namestr

    def set_unit(self, unit_new: dict = None) -> None:
        """
        Set the unit for the plot, default to SI

        Args:
        - unit: the unit dictionary, the format is {"I":"uA", "V":"V", "R":"Ohm"}
        """
        self.unit.update(unit_new)

    def df_plot_VT(self, *, ax: Axes = None, xylog=(False, False)) -> None:
        """
        plot the RT curve

        Args:
        - params: PlotParam class containing the parameters for the plot, if None, the default parameters will be used.
        - ax: the axes to plot the figure (require scalar)
        - custom_unit: defined if the unit is not the default one(uA, V), the format is {"I":"uA", "V":"mV", "R":"mOhm"}
        """
        self.params.tmp.update(label="VT")

        rt_df = self.dfs["VT"]
        if ax is None:
            fig, ax, param = DataPlot.init_canvas(1, 1, 10, 6)
        factor_r, unit_r_print = DataPlot.get_unit_factor_and_texname(self.unit["V"])
        factor_T, unit_T_print = DataPlot.get_unit_factor_and_texname(self.unit["K"])

        ax.plot(rt_df["T"] * factor_T, rt_df["V"] * factor_r, **self.params.params_list[0])
        ax.set_ylabel("$\\mathrm{R}$" + f"({unit_r_print})")
        ax.set_xlabel(f"$\\mathrm{{T}}$ ({unit_T_print})")
        ax.legend(edgecolor='black', prop=DataPlot.legend_font)
        if xylog[1]:
            ax.set_yscale("log")
        if xylog[0]:
            ax.set_xscale("log")

    def df_plot_nonlinear(self, *,
                          handlers: tuple[Axes, ...] = None,
                          plot_order: tuple[bool] = (True, True),
                          reverse_V: tuple[bool] = (False, False),
                          in_ohm: bool = False,
                          xylog1=(False, False), xylog2=(False, False)) \
            -> Axes | tuple[Axes, ...] | None:
        """
        plot the nonlinear signals of a 1-2 omega measurement

        Args:
        handlers: tuple[matplotlib.axes.Axes]
            the handlers for the plot, the content should be (ax_1w, ax_1w_phi,ax_2w, ax_2w)
        params: PlotParam class containing the parameters for the 1st 
            signal plot, if None, the default parameters will be used.         
        params2: the PlotParam class for the 2nd harmonic signal
        plot_order : list of booleans
            [Vw, V2w]
        reverse_V : list of booleans
            if the voltage is reversed by adding a negative sign
        custom_unit : dict
            defined if the unit is not the default one(uA, V), the format is {"I":"uA", "V":"mV", "R":"mOhm"}
        """
        nonlinear = self.dfs["nonlinear"].copy()
        if_indep = False
        return_handlers = False

        if reverse_V[0]:
            nonlinear["V1w"] = -nonlinear["V1w"]
        if reverse_V[1]:
            nonlinear["V2w"] = -nonlinear["V2w"]

        factor_i, unit_i_print = DataPlot.get_unit_factor_and_texname(self.unit["I"])
        factor_v, unit_v_print = DataPlot.get_unit_factor_and_texname(self.unit["V"])
        factor_r, unit_r_print = DataPlot.get_unit_factor_and_texname(self.unit["R"])

        if handlers is None:
            if_indep = True
            fig, ax, params = DataPlot.init_canvas(2, 1, 10, 12)
            ax_1w, ax_2w = ax
            ax_1w_phi = ax_1w.twinx()
            ax_2w_phi = ax_2w.twinx()
            return_handlers = True
        else:
            ax_1w, ax_1w_phi, ax_2w, ax_2w_phi = handlers
            params = DataPlot.PlotParam(2, 1)

        # assign and merge the plotting parameters
        params[0, 0, 0].update(label=r"$V_w$")
        params[1, 0, 0].update(label=r"$V_{2w}$")
        params[0, 0, 1].update(label=r"$\phi_w$", color="c", linestyle="--", marker="", alpha=0.37)
        params[1, 0, 1].update(label=r"$\phi_{2w}$", color="m", linestyle="--", marker="", alpha=0.37)

        # plot the 2nd harmonic signal
        if plot_order[1]:
            if in_ohm:
                line_v2w = ax_2w.plot(nonlinear["curr"] * factor_i, nonlinear["V2w"] * factor_r / nonlinear["curr"],
                                      **params[1, 0, 0])
                ax_2w.set_ylabel("$\\mathrm{R^{2\\omega}}$" + f"({unit_r_print})")
            else:
                line_v2w = ax_2w.plot(nonlinear["curr"] * factor_i, nonlinear["V2w"] * factor_v, **params[1, 0, 0])
                ax_2w.set_ylabel("$\\mathrm{V^{2\\omega}}$" + f"({unit_v_print})")

            line_v2w_phi = ax_2w_phi.plot(nonlinear["curr"] * factor_i, nonlinear["phi_2w"], **params[1, 0, 1])
            ax_2w_phi.set_ylabel(r"$\phi(\mathrm{^\circ})$")
            ax_2w.legend(handles=line_v2w + line_v2w_phi, labels=[line_v2w[0].get_label(), line_v2w_phi[0].get_label()],
                         edgecolor='black', prop=DataPlot.legend_font)
            ax_2w.set_xlabel(f"I ({unit_i_print})")
            if xylog2[1]:
                ax_2w.set_yscale("log")
            if xylog2[0]:
                ax_2w.set_xscale("log")
            #ax.set_xlim(-0.00003,None)
        if plot_order[0]:
            if in_ohm:
                line_v1w = ax_1w.plot(nonlinear["curr"] * factor_i, nonlinear["V1w"] * factor_r / nonlinear["curr"],
                                      **params[0, 0, 0])
                ax_1w.set_ylabel("$\\mathrm{R^\\omega}$" + f"({unit_r_print})")
            else:
                line_v1w = ax_1w.plot(nonlinear["curr"] * factor_i, nonlinear["V1w"] * factor_v, **params[0, 0, 0])
                ax_1w.set_ylabel("$\\mathrm{V^\\omega}$" + f"({unit_v_print})")

            line_v1w_phi = ax_1w_phi.plot(nonlinear["curr"] * factor_i, nonlinear["phi_1w"], **params[0, 0, 1])
            ax_1w_phi.set_ylabel(r"$\phi(\mathrm{^\circ})$")
            ax_1w.legend(handles=line_v1w + line_v1w_phi, labels=[line_v1w[0].get_label(), line_v1w_phi[0].get_label()],
                         edgecolor='black', prop=DataPlot.legend_font)
            if xylog1[1]:
                ax_1w.set_yscale("log")
            if xylog1[0]:
                ax_1w.set_xscale("log")
        if if_indep:
            fig.tight_layout()
            plt.show()
        if return_handlers:
            return ax_1w, ax_1w_phi, ax_2w, ax_2w_phi

    def plot_df_cols(self, measure_mods: tuple[str], *var_tuple: float | str,
                     data_df: pd.DataFrame = None) -> Optional[tuple[Figure, Axes]]:
        """
        plot all columns w.r.t. the first column in the dataframe
        either (measurement modules and info) or data_df should be provided

        Args:
        - measure_mods: the measurement modules
        - var_tuple: info for measurement modules
        - data_df: the dataframe containing the data
        """
        if data_df is not None:
            plot_path = None
        else:
            if measure_mods is None:
                print("no info and no dataframe")
                return None
            else:
                plot_path = self.get_filepath(measure_mods, *var_tuple, plot=True)
                data_path = self.get_filepath(measure_mods, *var_tuple)
                try:
                    data_df = pd.read_csv(data_path, sep=r",|\s+", index_col=False)
                except Exception:
                    print("no data found")
                    return None

        fig, ax, param = DataPlot.init_canvas(1, 1, 14, 20)
        for col in data_df.columns[1:]:
            ax.plot(data_df.iloc[:, 0], data_df[col], label=col)
        ax.set_xlabel(data_df.columns[0])  # Set the label of the x-axis to the name of the first column
        ax.legend(edgecolor='black', prop=DataPlot.legend_font)
        if plot_path is not None and not plot_path.exists():
            print(f"plot saved to {plot_path}")
            fig.savefig(plot_path)
        plt.show()
        return fig, ax

    @staticmethod
    def plot_mapping(data_df: pd.DataFrame, mapping_x: any, mapping_y: any, mapping_val: any, *,
                     fig: Figure = None, ax: Axes = None, cmap: str = "viridis") -> tuple[Figure, Axes]:
        """
        plot the mapping of the data

        Args:
        - data_df: the dataframe containing the data
        - mapping_x: the column name for the x-axis
        - mapping_y: the column name for the y-axis
        - mapping_val: the column name for the mapping value
        - ax: the axes to plot the figure
        """
        grid_df = data_df.pivot(index=mapping_x, columns=mapping_y, values=mapping_val)
        x_arr, y_arr = np.meshgrid(grid_df.columns, grid_df.index)

        if fig is None or ax is None:
            fig, ax, param = DataPlot.init_canvas(1, 1, 10, 8)

        contour = ax.contourf(x_arr, y_arr, grid_df, cmap=cmap)
        fig.colorbar(contour)
        return fig, ax

    @staticmethod
    def load_settings(usetex: bool = False, usepgf: bool = False) -> None:
        """load the settings for matplotlib saved in another file"""
        file_name = "pylab_dk.pltconfig.plot_config"
        if usetex:
            file_name += "_tex"
            if usepgf:
                file_name += "_pgf"
        else:
            file_name += "_notex"

        config_module = importlib.import_module(file_name)
        DataPlot.legend_font = getattr(config_module, 'legend_font')

    @staticmethod
    def paint_colors_twin_axes(*, ax_left: Axes, color_left: str, ax_right: Axes,
                               color_right: str) -> None:
        """
        paint the colors for the twin y axes

        Args:
        - ax: the axes to paint the colors
        - left: the color for the left y-axis
        - right: the color for the right y-axis
        """
        ax_left.tick_params("y", colors=color_left)
        ax_left.spines["left"].set_color(color_left)
        ax_right.tick_params("y", colors=color_right)
        ax_right.spines["right"].set_color(color_right)

    @staticmethod
    def init_canvas(n_row: int, n_col: int, figsize_x: float, figsize_y: float,
                    sub_adj: tuple[float] = (0.19, 0.13, 0.97, 0.97, 0.2, 0.2), **kwargs) \
            -> tuple[Figure, Axes, PlotParam]:
        """
        initialize the canvas for the plot, return the fig and ax variables and params(n_row, n_col, 2)

        Args:
        - n_row: the fig no. of rows
        - n_col: the fig no. of columns
        - figsize_x: the width of the whole figure in cm
        - figsize_y: the height of the whole figure in cm
        - sub_adj: the adjustment of the subplots (left, bottom, right, top, wspace, hspace)
        - **kwargs: keyword arguments for the plt.subplots function
        """
        fig, ax = plt.subplots(n_row, n_col, figsize=(figsize_x * cm_to_inch, figsize_y * cm_to_inch), **kwargs)
        fig.subplots_adjust(left=sub_adj[0], bottom=sub_adj[1], right=sub_adj[2], top=sub_adj[3], wspace=sub_adj[4],
                            hspace=sub_adj[5])
        return fig, ax, DataPlot.PlotParam(n_row, n_col, 2)

    def live_plot_init(self, n_rows: int, n_cols: int, lines_per_fig: int = 2, pixel_height: float = 600,
                       pixel_width: float = 1200, *, titles: Sequence[Sequence[str]] = None,
                       axes_labels: Sequence[Sequence[Sequence[str]]] = None,
                       line_labels: Sequence[Sequence[Sequence[str]]] = None,
                       plot_types: Sequence[Sequence[Literal["scatter", "contour"]]] = None) -> None:
        """
        initialize the real-time plotter using plotly

        Args:
        - n_rows: the number of rows of the subplots
        - n_cols: the number of columns of the subplots
        - lines_per_fig: the number of lines per figure
        - pixel_height: the height of the figure in pixels
        - pixel_width: the width of the figure in pixels
        - titles: the titles of the subplots, shape should be (n_rows, n_cols), note the type notation
        - axes_labels: the labels of the axes, note the type notation, shape should be (n_rows, n_cols, 2[x and y axes labels])
        - line_labels: the labels of the lines, note the type notation, shape should be (n_rows, n_cols, lines_per_fig)
        - plot_types: the plot types for the lines, the type of plot for each subplot,
                options include 'scatter' and 'contour', shape should be (n_rows, n_cols)
        """
        if plot_types is None:
            plot_types = [['scatter' for _ in range(n_cols)] for _ in range(n_rows)]
        self.plot_types = plot_types
        # for contour plot, only one "line" is allowed
        traces_per_subplot = [[lines_per_fig if plot_types[i][j] == 'scatter' else 1 for j in range(n_cols)] for i
                              in range(n_rows)]
        if titles is None:
            titles = [["" for _ in range(n_cols)] for _ in range(n_rows)]
        flat_titles = [item for sublist in titles for item in sublist]
        if axes_labels is None:
            axes_labels = [[["" for _ in range(2)] for _ in range(n_cols)] for _ in range(n_rows)]
        if line_labels is None:
            line_labels = [[["" for _ in range(2)] for _ in range(n_cols)] for _ in range(n_rows)]

        # initial all the data arrays, not needed for just empty lists
        #x_arr = [[[] for _ in range(n_cols)] for _ in range(n_rows)]
        #y_arr = [[[[] for _ in range(lines_per_fig)] for _ in range(n_cols)] for _ in range(n_rows)]

        fig = make_subplots(rows=n_rows, cols=n_cols, subplot_titles=flat_titles)
        data_idx = 0
        self.live_dfs = [[[] for _ in range(n_cols)] for _ in range(n_rows)]
        for i in range(n_rows):
            for j in range(n_cols):
                plot_type = plot_types[i][j]
                num_traces = traces_per_subplot[i][j]
                if plot_type == 'scatter':
                    for k in range(num_traces):
                        fig.add_trace(go.Scatter(x=[], y=[], mode='lines+markers', name=line_labels[i][j][k]),
                                      row=i + 1, col=j + 1)
                        data_idx += 1
                elif plot_type == 'contour':
                    fig.add_trace(go.Contour(z=[], x=[], y=[], name=line_labels[i][j][0]), row=i + 1, col=j + 1)
                    data_idx += 1
                else:
                    raise ValueError(f"Unsupported plot type '{plot_type}' at subplot ({i},{j})")
                fig.update_xaxes(title_text=axes_labels[i][j][0], row=i + 1, col=j + 1)
                fig.update_yaxes(title_text=axes_labels[i][j][1], row=i + 1, col=j + 1)

        fig.update_layout(height=pixel_height, width=pixel_width)
        if is_notebook():
            from IPython.display import display
            self.go_f = go.FigureWidget(fig)
#            self.live_dfs = [
#                [[self.go_f.data[i * n_cols * lines_per_fig + j * lines_per_fig + k] for k in range(lines_per_fig)] for
#                 j in range(n_cols)] for i in range(n_rows)]
            idx = 0
            for i in range(n_rows):
                for j in range(n_cols):
                    num_traces = traces_per_subplot[i][j]
                    for k in range(num_traces):
                        self.live_dfs[i][j].append(self.go_f.data[idx])
                        idx += 1
            display(self.go_f)
        elif not is_notebook():
            fig.show()

    def save_fig_periodically(self, plot_path: Path | str, time_interval: int = 60) -> None:
        """
        save the figure periodically
        this function will be running consistently in the background
        use threading to run this function in the background
        """
        if isinstance(plot_path, str):
            plot_path = Path(plot_path)
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        while not self._stop_event.is_set():
            time.sleep(time_interval)
            self.go_f.write_image(plot_path)

    def start_saving(self, plot_path: Path | str, time_interval: int = 60) -> None:
        """
        start the thread to save the figure periodically
        """
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.save_fig_periodically, args=(plot_path, time_interval))
        self._thread.start()

    def stop_saving(self) -> None:
        """
        stop the thread to save the figure periodically
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def live_plot_update(self, row: int | tuple[int], col: int | tuple[int], lineno: int | tuple[int],
                         x_data: Sequence[float] | Sequence[Sequence[float]] | np.ndarray[float],
                         y_data: Sequence[float] | Sequence[Sequence[float]] | np.ndarray[float],
                         z_data: Sequence[float] | Sequence[Sequence[float]] | np.ndarray[float] = (0,),
                         *, incremental=False, max_points: int = None) -> None:
        """
        update the live data in jupyter, the row, col, lineno all can be tuples to update multiple subplots at the
        same time. Note that this function is not appending datapoints, but replot the whole line, so provide the
        whole data array for each update. The row, col, lineno, x_data, y_data should be of same length (no. of lines
        plotted). Be careful about the correspondence of data and index, e.g. when given indices like (0,1), the data
        should be like [[0],[1]], instead of [0,1] (incremental case).
        Example: live_plot_update((0,1), (0,1), (0,1), [x_arr1, x_arr2], [y_arr1, y_arr2]) will
        plot the (0,0,0) line with x_arr1 and y_arr1, and (1,1,1) line with x_arr2 and y_arr2

        Args:
        - row: the row of the subplot (from 0)
        - col: the column of the subplot (from 0)
        - lineno: the line no. of the subplot (from 0)
        - x_data: the array-like x data (not support single number, use [x] or (x,) instead)
        - y_data: the array-like y data (not support single number, use [y] or (y,) instead)
        - z_data: the array-like z data (for contour plot only, be the same length as no of contour plots)
        - incremental: whether to update the data incrementally
        - max_points: the maximum number of points to be plotted, if None, no limit, only affect incremental line plots
        """
        if not incremental and max_points is not None:
            print("max_points will be ignored when incremental is False")

        def ensure_list(data) -> np.ndarray:
            if isinstance(data, (list, tuple, np.ndarray, pd.Series, pd.DataFrame)):
                return np.array(data)
            else:
                return np.array([data])

        def ensure_2d_array(data) -> np.ndarray:
            data_arr = ensure_list(data)
            if not isinstance(data_arr[0], np.ndarray):
                return np.array([data_arr], dtype=np.float32)
            else:
                return np.array(data_arr, dtype=np.float32)

        row = ensure_list(row)
        col = ensure_list(col)
        lineno = ensure_list(lineno)
        x_data = ensure_2d_array(x_data)
        y_data = ensure_2d_array(y_data)
        z_data = ensure_2d_array(z_data)

        #dim_tolift = [0, 0, 0]
        with (self.go_f.batch_update()):
            idx_z = 0
            for no, (irow, icol, ilineno) in enumerate(zip(row, col, lineno)):
                plot_type = self.plot_types[irow][icol]
                trace = self.live_dfs[irow][icol][ilineno]
                if plot_type == 'scatter':
                    if incremental:
                        trace.x = np.append(trace.x, x_data[no])[-max_points:] if max_points is not None\
                            else np.append(trace.x, x_data[no])
                        trace.y = np.append(trace.y, y_data[no])[-max_points:] if max_points is not None\
                            else np.append(trace.y, y_data[no])
                    else:
                        trace.x = x_data[no]
                        trace.y = y_data[no]
                if plot_type == 'contour':
                    if not incremental:
                        trace.x = x_data[no]
                        trace.y = y_data[no]
                        trace.z = z_data[idx_z]
                    else:
                        trace.x = np.append(trace.x, x_data[no])
                        trace.y = np.append(trace.y, y_data[no])
                        trace.z = np.append(trace.z, z_data[idx_z])
                    idx_z += 1
            assert idx_z == len(z_data) or (idx_z == 0 and z_data == (0,)), \
                "z_data should have the same length as the number of contour plots"

    @staticmethod
    def sel_pan_color(row: int = None, col: int = None) -> Optional[tuple[tuple[float | int, ...], str]]:
        """
        select the color according to the position in pan_colors method (use row and col as in 2D array)
        leave row and col as None to show the color palette
        """
        with open(DataPlot._local_database_dir / "pan-colors.json") as f:
            color_dict = json.load(f)
        full_rgbs = list(map(hex_to_rgb, color_dict["values"]))
        rgbs = full_rgbs[:2304]
        extra = full_rgbs[2304:]
        extra += [(1, 1, 1)] * (48 - len(extra))
        rgb_mat = [rgbs[i * 48:(i + 1) * 48] for i in range(48)]
        rgb_mat.append(extra)
        if row is None and col is None:
            DataPlot.load_settings(False, False)
            fig, ax, _ = DataPlot.init_canvas(1, 1, 20, 20)
            ax.imshow(rgb_mat)
            ax.set_xticks(np.arange(0, 48, 5))
            ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False)
            ax.set_yticks(np.arange(0, 48, 5))
            plt.grid()
            plt.show()
        elif row is not None and col is not None:
            return rgb_mat[row][col], color_dict["names"][row * 48 + col]
        else:
            print("x and y should be both None or both not None")

    @staticmethod
    def preview_colors(color_lst: tuple[float | int, ...] | list[tuple[float | int, ...]] |
                       list[list[tuple[float | int, ...]]]) -> None:
        """
        preview the colors in the list
        """
        DataPlot.load_settings(False, False)
        fig, ax, _ = DataPlot.init_canvas(1, 1, 13, 7)
        try:
            if isinstance(color_lst[0], float | int):
                ax.imshow([[color_lst]])
            if isinstance(color_lst[0][0], float | int):
                ax.imshow([color_lst])
            elif isinstance(color_lst[0][0][0], float | int):
                ax.imshow(color_lst)
            else:
                print("wrong format")
                return
        except Exception:
            print("wrong format")
            return
        plt.show()
