# pylab_dk

This is a preliminary tool based on [pymeasure](https://github.com/pymeasure/pymeasure) and [qcodes](https://github.com/microsoft/Qcodes) written for collecting 
and dealing with experimental data. **This project has not been fully
developed**

# About modules
## IMPORTANT ENVIRONMENTAL VARIABLES
- PYLAB_DB_LOCAL: the path to the local database, storing the rarely changing data like measure_type.json
- PYLAB_DB_OUT: the path to the out database, storing the experimental data and record

## Usage notes
- the measure_type.json need to be created according to experimental needs. As to its format, please refer to the following section
- jupyter notebook works as the platform for now. Put a template named `assist.ipynb` into local database directory

### Json Structure of project_record.json
```json
{
    "project_name":{
        "created_date": "2024-11-20",
        "last_modified": "2025-02-29",
        "measurements":[
            "IV","IV-T"
        ],
        "plan":{
            "IV":["IV Curve"],
            "IV-T":["Temperature Dependence"]
        }
    }
}

```

### Json Structure of measure_types.json
Naming rules: use `_var_` to represent variables need to be replaced when naming
```json
{        
  "V": {
        "sense": "V{note}-{vhigh}-{vlow}",
        "source": {
            "fixed":{
                "dc": "Vfix{fixv}V-{vhigh}-{vlow}",
                "ac": "Vfix{fixv}V-freq{freq}Hz-{vhigh}-{vlow}"
            },
            "sweep": {
                "dc": "Vmax{maxv}V-step{stepv}V-{vhigh}-{vlow}-swpmode{mode}",
                "ac": "Vmax{maxv}V-step{stepv}V-freq{freq}Hz-{vhigh}-{vlow}"
            }
        }
    },
  "T": {
        "fixed": "Temp{fixT}K",
        "sweep": "Temp{Tstart}-{Tstop}K-step{stepT}K-swpmode{mode}",
        "vary": "Temp{Tstart}-{Tstop}K"
    }
}
```

# In Schedule
- reconstruct the measurement class so that measurements can be easily assembled
- add rotator support either by calling dll or using SDK
- [long term]clean old codes (measurement, plot and process)
- [long term]add interface by dash or PyQt6

# dependency
- python >= 3.11 (earlier version is not tested)
- jupyter[optional]
- matplotlib
- numpy
- plotly
- pyvisa
- pymeasure >= 0.14.0
- qcodes >= 0.47.0
- PyQt6[optional]
