# PoWR Scheduling Toolbox (```postbox.py```) Introduction

## First-time Setup

1. Clone this repository in your desired location.
   
```git clone git@github.com:JorisJosiek/postbox.git ```

2. Run ```setup.sh```. This is an interactive tool that creates a ```.postbox``` folder in your home directory and fills it with the necessary files. When asked for the config name, type anything you like (no spaces please). You will be asked to edit the config file. Please make sure to type a useable path to save your models under ```save_path```, and perhaps select chains to use and make a machine priority list. All other paths should already be correct, assuming you are following the default PoWR directory structure.
3. Make your chains using PoWR's ```makechain```. You must make all the chains in the range defined by ```chain_range``` in the config file.
4. Insert some old models into the system. (See "Tracking external old models")

## Typical workflow

After some setup, the typical repeating workflow is designed to be minimalistic.

1. Edit schedule file to define new models in batch. (see below)
2. Run ```postbox.py```
3. Type ```auto```
4. Type ```exit```

For details on the commands, see the manual.

## Defining new jobs

New jobs are defined in the schedule file, located by default in the ```~/.postbox/schedule_files/``` directory (check the ```schedule_file``` parameter in your config for the location). In its initial state, the schedule file contains two lines as a header which can be modified by the user at will. These lines will never be used or modified by the code. To define a job (model), you add a line to the schedule file in the format 

```from SID ###### | parameters | comment```

where ```SID``` is followed by a six-digit zero-padded scheduler ID of a saved old model. The old model must be saved under ```save_path/######/``` where ```save_path``` is defined in the config file. In the ```parameters``` column, you write stellar parameters as written in the ```CARDS``` file (not case-sensitive) separated by commas. The ```comment``` column is a free string for you to make a relevant note. This comment will be carried everywhere with the job and may help you identify a job later if you want to use it as an old model. All together, an example of a valid line written in the schedule file could be:

```from SID 000001 | Teff=40000., log ggrav=3.85 | example model```

When this model is ready to be loaded into a chain, this line instructs the postbox to copy the model saved under ```save_path/000001/```, and modify the effective temperature and gravity in the ```CARDS``` file.

After the models have been loaded by the postbox, the schedule file is reset to its initial state.

## Tracking external old models

Currently, the postbox does not support running models from LTESTART, so an old model must be selected when scheduling a new model. This model must have an SID and be saved in the relevant location. This means that before you run the postbox for the first time, you must somehow inject some external old models into the postbox so that they can be tracked.

1. Open the jobs file (find the location in your config, by default it's in ```~/.postbox/jobs_files/```. This is the central database which is read and written by the Scheduler and tracks the status of all models. The entries in this list define the job and consist of six columns in the format ```SID|STATUS|CHAIN|OLD_SID|PARAMS|COMMENT```.
2. Find an unused SID and add the line ```######|||||comment```, where ```######``` is the 6-digit 0-padded SID, and ```comment``` is any string to identify your model. Save the file.
3. Take your model files and save them in ```save_path/######/```, where ```save_path``` is the path defined in your config, and ```######``` is the SID you chose in step 2. The required model files are ```CARDS```, ```DATOM```, ```FEDAT```, ```FEDAT_FORMAL```, ```FGRID```, ```FORMAL_CARDS```, ```MODEL```, ```NEWDATOM_INPUT```, and ```NEWFORMAL_CARDS_INPUT```. If any of these files are not present, the postbox will not be able to load any dependent models.

These steps ensure that your model is tracked by the postbox (it is in the jobs file), and that the postbox can find the model files when it needs them.

## Using multiple configs in parallel

You can rerun ```setup.sh``` as many times as you like to create different configs for the postbox. If you attempt to reuse a config name, a warning will be issued to you, since this will entail overwriting the jobs database and is equivalent to a full reset of a previous setup. At the end, the setup tool will ask whether you would like to use your new configuration as default. The default configuration is a symlink pointing to one of your config files and is located at ```~/.postbox/configs/default```. When not told otherwise, the postbox will always take this file for extracting configuration settings.

## Using the ```postbox``` in interactive mode

Launch the postbox.
- with default config:
  
  ```python3 postbox.py```
  
- with custom config:
  
  ```python3 postbox.py --config path/to/config```

  (the path to the config file can be absolute, or relative to the current working directory)

Once the postbox is launched, you will see a status summary showing your jobs and chains, and enter an interactive shell. This shell has different internal commands you can use, which are all displayed by typing ```help```. You can exit the shell by typing ```exit```.

## Using the ```postbox``` as a module

Make sure the ```postbox.py``` file can be imported into a Python script (e.g. by updating your Python path environment variable).

Then, you can access the full capabilities of the postbox after ```import postbox```.

You can initialize an instance of the Scheduler by passing the config file path:

```myPostbox = postbox.Scheduler('/path/to/config/')```

Note that the argument is mandatory, since there is no default config file for the modular postbox. This is to ensure that scripts behave predictably, even if the default config is changed.

Your Scheduler object owns instances of the JobManager (```myPostbox.JM```) and ChainManager (```myPostbox.CM```) objects, which you can use to handle jobs and chains, respectively. At the same time, the Scheduler has a variety of methods to perform specific sequences of tasks such as submitting and saving jobs.
