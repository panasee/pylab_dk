# pylab_dk

This is a preliminary tool written for collecting 
and dealing with experimental data. **This project has not been fully
developed**

# check and correct it before usage!
## these scripts are not designed to fit extensive cases!

# About modules
## IMPORTANT VARIABLES and FUNCTIONS
- base_dir: Path (exp_measure/common/file_organize.py): the base workpath Path object
- today: str (exp_measure/common/file_organize.py): the date indicating when the organize.py is imported
- FileOrganizer.out_database_dir: Path (exp_measure/common/file_organize.py): the out_database Path, defined by static method FileOrganizer.out_database_init(path: str)

## Usage notes
- measurename string contains two parts connected by "__", first part is the measurename, second part is the subcategory(if no subcategory, just don't contain this part)

## Arrangement
- several modules are written in the **common** folder.
- These modules are independent and should not interfere with each other.
- For the convenience of daily usage, jupyter files are created in each directory for short use. **do not write huge blocks in jupyter notebooks, if so, then pack them as module py files outside**

## About stored datas
- Small local databases are stored directly in **data_files** folder as csv and json files(or just normal text file)
- Large experimental or other data is stored separately (not in this git directory, so **specify the other data directory path if needed**)
### Json Structure of project_record.json
```json
{
    "project_name":{
        "created_date": "2024-11-20",
        "last_modified": "2025-02-29",
        "measurements":[
            "Nonlinear","RT","Contact"
        ],
        "plan":{
            "Nonlinear":["Angular dependence"],
            "RT":["SC transition", "peak current"]
        }
    }
}

```

### Json Structure of measure_types.json
Naming rules: use `_var_` to represent variables need to be replaced when naming
```json
{
    "Nonlinear":{
        "IV_one":"Max{maxv}V-R{res}-{npts}points-freq{freq}-I-{iin}-{iout}-V-{vhigh}-{vlow}-{tempstr}{fileappen}",
        "IV_two":"Max{maxv}V-R{res}-{npts}points-freq{freq}-I-{iin}-{iout}-Vup-{v1high}-{v1low}-Vdown-{v2high}-{v2low}-{tempstr}{fileappen}",
    },
    "RT":"I-{iin}-{iout}-{currstr}-Vup-{v1high}-{v1low}-Vdown-{v2high}-{v2low}-{temp1str}-{temp2str}{fileappen}",
    "Contact":"I-{iin}-{iout}-Vmax-{vmax}-Vstep-{vstep}-{sweeptype}-{tempstr}{fileappen}"
}
```

## NOTE while constructing the modules
- Comment is **always necessary**, unless very straightforward and short codes
- Look up global variables here before defining a new one or even a local similar one
- Use `##TODO##` to highlight the uncompleted functions or desired functionalities
- take note about the version of python itself and the modules used

# In Schedule
- filemanage module (create, (re)name, find and read, load and return file object)
    - able to establish a small local file to record projects and files
- measurement module
- plot module
- calculation module (long-term)

# dependency
- python >= 3.11 (earlier version is not tested)
- jupyter
- matplotlib
- numpy
- scipy
- pymeasure
- pyvisa
- qcodes
