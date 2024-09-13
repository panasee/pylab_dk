#!/usr/bin/env python

"""
This file contains the quick post-processing functions for the lab view data, which are contained in two subclasses of the DataProcess and DataPlot classes

NOTE: if flexible handler is needed, the DataProcess and DataPlot classes should be used directly
"""

import pandas as pd
from typing import Tuple
import matplotlib

from common.data_process import DataProcess
from common.data_plot import DataPlot
import common.pltconfig.color_preset as colors


class LabViewPost(DataPlot):
    """This class is responsible for the quick post-processing of the lab view data"""
    def __init__(self, proj_name: str) -> None:
        super().__init__(proj_name)
    
    def nonlinear_df_labview(self,measurename_sub: str = "1-pair", *var_tuple, tmpfolder: str = None,  lin_antisym: bool = False, harmo_sym: bool = False, position_I: int = 4) -> pd.DataFrame:
        """
        Process the nonlinear data, both modify the self.dfs inplace and return it as well for convenience. Could also do anti-symmetrization to 1w signal and symmetrization to 2w signal (choosable)
        
        Args:
        - measurename_sub: the sub measurement name used to appoint the detailed configuration
        - *vars: the arguments for the pd.read_csv function
        - tmpfolder: the temporary folder
        - lin_antisym: bool
            do the anti-symmetrization to 1w signal
        - harmo_sym: bool
            do the symmetrization to 2w signal
        - position_I: int
            the position of the current in the var_tuple(start from 0), used in combination with sym/antisym labels
        """
        self.load_dfs(f"nonlinear__{measurename_sub}", *var_tuple, tmpfolder=tmpfolder, header=None, skiprows=1)
        if lin_antisym or harmo_sym:
            if position_I is None:
                raise ValueError("position_I should be specified when lin_antisym or harmo_sym is True")
            var_reversed = list(var_tuple)
            var_reversed[position_I], var_reversed[position_I+1] = var_reversed[position_I+1], var_reversed[position_I]
            self.load_dfs(f"nonlinear__{measurename_sub}", *var_reversed, tmpfolder=tmpfolder, cached=True, header=None, skiprows=1)

        # rename_columns will rename the "cache" as well
        self.rename_columns("nonlinear", {0: "curr", 2:"V2w", 4:"phi_2w", 5:"V1w", 6: "phi_1w"})
        if lin_antisym:
            self.dfs["nonlinear"]["V1w"] = (self.dfs["nonlinear"]["V1w"] - self.dfs["cache"]["V1w"])/2
        if harmo_sym:
            self.dfs["nonlinear"]["V2w"] = (self.dfs["nonlinear"]["V2w"] + self.dfs["cache"]["V2w"])/2
        # here the self.dfs has already been updated, the return is just for possible other usage
        return self.dfs["nonlinear"]

    def nonlinear_plot_labview(self, *var_tuple, tmpfolder:str = None, measurename_sub: str = "1-pair", handlers: Tuple[matplotlib.axes.Axes] = None, units: dict = None, lin_antisym: bool =False, harmo_sym:bool = False, position_I: int = None, **kwargs) -> matplotlib.axes.Axes | None:
        """
        Plot the nonlinear data
        
        Args:
        handlers: the handlers for the plot
        """
        return_handlers = False
        if handlers is None:
            fig, ax = self.init_canvas(2,1,7,13)
            handlers = (ax[0],ax[0].twinx(), ax[1], ax[1].twinx())
            return_handlers = True
        if units is not None:
            self.set_unit(units)

        self.nonlinear_df_labview(*var_tuple, tmpfolder=tmpfolder, measurename_sub=measurename_sub, lin_antisym=lin_antisym, harmo_sym=harmo_sym, position_I=position_I)
        self.df_plot_nonlinear(handlers = handlers, **kwargs)

        if return_handlers:
            return handlers

    @staticmethod
    def gen_iter_appen(num: int) -> iter:
        """
        generate the iterator for file appendix, from ""(means 1) till num itself 
        
        Args:
        - num: the number of the iteration
        """
        for i in range(1,num+1):
            if i == 1:
                yield ""
            else:
                yield f"-{i}"