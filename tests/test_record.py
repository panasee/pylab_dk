#!/usr/bin/env python
import os
import pandas as pd
# make sure environment variables are set before importing pylab_dk
# MeasureManager module will need the NIDAQmx module to work,
from pylab_dk.measure_manager import MeasureManager

project_name = "Date-Material" # Name used only for test
measurement = MeasureManager(project_name)

#=======test initialization of record=======
filepath, col_no, df_record = measurement.record_init(
                                        ("V_source_sweep_ac","V_source_sweep_ac","V_sense","V_sense","T_vary"),
                                        1, 1E-2, 13.221, 1,1,1,1E-2,123.21,1,1,"",1,1,"",1,1,300,5,
                                        return_df=True)

print(f"filepath: {filepath}")
print(f"no of columns(with time column): {col_no}")
print(f"dataframe: {df_record}")

# Expected output:
# filepath: ...\VV-VV-T\Vmax1V-step0.01V-freq13.221Hz-1-1-Vmax1V-step0.01V-freq123.21Hz-1-1_V-1-1-V-1-1_Temp300-5K
# no of columns(with time column): 12
# dataframe: Empty DataFrame
# Columns: [time, V_source, V_source2, X, Y, R, Theta, X2, Y2, R2, Theta2, T]
# Index: []

#========test record update and force_write=======
measurement.record_update(filepath, col_no, [1]*(col_no-1), force_write=True)
print(pd.read_csv(filepath, sep="\t"))

# Expected output:
#                time  V_source  V_source2  X  Y  R  Theta  X2  Y2  R2  Theta2  T
# 0  29-10-01_16:35:09         1          1  1  1  1      1   1   1   1       1  1
#(first 0 is the default index column)

#========test record auto write=======
for i in range(7):# the auto write period is 7
    measurement.record_update(filepath, col_no, [i]*(col_no-1))
print(pd.read_csv(filepath, sep="\t"))

# Expected output:
#                time  V_source  V_source2  X  Y  R  Theta  X2  Y2  R2  Theta2  T
#0  27-11-20_16:45:02         1          1  1  1  1      1   1   1   1       1  1
#1  27-11-20_16:45:02         0          0  0  0  0      0   0   0   0       0  0
#2  27-11-20_16:45:02         1          1  1  1  1      1   1   1   1       1  1
#3  27-11-20_16:45:02         2          2  2  2  2      2   2   2   2       2  2
#4  27-11-20_16:45:02         3          3  3  3  3      3   3   3   3       3  3
#5  27-11-20_16:45:02         4          4  4  4  4      4   4   4   4       4  4
#6  27-11-20_16:45:02         5          5  5  5  5      5   5   5   5       5  5
#7  27-11-20_16:45:02         6          6  6  6  6      6   6   6   6       6  6