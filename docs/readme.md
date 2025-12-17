# PoWR Scheduling Toolbox (```postbox.py```) Introduction

## First-time Setup

1. Clone this repository in your desired location.
   
```git clone git@github.com:JorisJosiek/postbox.git ```

2. Run ```setup.sh```. This is an interactive tool that creates a ```.postbox``` folder in your home directory and fills it with the necessary files. When asked for the config name, type anything you like (no spaces please). You will be asked to edit the config file. Please make sure to type a useable path to save your models under ```save_path```, and perhaps select chains to use and make a machine priority list. All other paths should already be correct, assuming you are following the default PoWR directory structure.
3. Make your chains using PoWR's ```makechain```. You must make all the chains in the range defined by ```chain_range``` in the config file.

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
