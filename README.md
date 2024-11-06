# pylab_dk

**pylab_dk** is an integrated package based on [PyMeasure](https://github.com/pymeasure/pymeasure) and [QCoDeS](https://github.com/microsoft/Qcodes),
designed for collecting, processing, and plotting experimental data.
(**why not use QCoDeS directly:** allow for more flexible measurements and plotting in the lower level)

## Table of Contents

- [Installation](#installation)
- [Usage Notes](#usage-notes)
    - [Json Structure of `project_record.json`](#json-structure-of-project_recordjson)
    - [Json Structure of `measure_types.json`](#json-structure-of-measure_typesjson)
- [Roadmap](#Roadmap)
- [Dependencies](#dependencies)

## Installation

Ensure you have Python 3.11 or higher installed. You can install the required packages using pip:
```bash
cd $path_to_pylab_dk
pip install .
```
### set environmental variables
- PYLAB_DB_LOCAL: the path to the local database, storing rarely changing data like measure_type.json
- PYLAB_DB_OUT: the path to the out database, storing the experimental data and records

(set them via `os.environ` or directly in the system setting)

# About modules

## Usage notes
- **Measure Types:** A file named measure_types.json is used for automatically naming data files. 
Refer to the JSON Structure of measure_types.json section for formatting details.
- **Jupyter Notebook:** Use Jupyter Notebook as the platform for now. Place a template named assist.ipynb 
into the local database directory for quick setup. The template will be copied to every project directory.

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
**Naming rules:** use `{variable}` to represent variables that need to be replaced when naming.
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

# Roadmap
- Short-term Goals:
  - fix rotator DLL API-calling bugs
  - optimize memory occupation of plotly real-time plotting
- Long-term Goals:
  - add interface by dash or PyQt6

# dependencies
- python >= 3.11 (earlier version is not tested)
- Required packages:
  - numpy
  - pandas
  - matplotlib
  - plotly
  - kaleido == 0.1.0.post1
  - pyvisa
  - pymeasure >= 0.14.0
  - qcodes >= 0.47.0
- Optional packages:
  - jupyter
  - PyQt6
