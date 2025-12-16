cd $HOME
mkdir -p .postbox
cd .postbox

read -p "Config name: " config_name

if [[ -e "configs/config_${config_name}" ]]; then
    echo "⚠️  This config already exists. Continuing will reset the jobs database irreversibly. ⚠️"
    read -p "Type OVERWRITE (in all caps) to confirm. " overwrite
    if [[ "${overwrite}" != "OVERWRITE" ]]; then
        echo "Setup aborted."
        exit 1
    fi
fi
echo

# Jobs file
mkdir -p jobs_files
cd jobs_files
echo "SID|STATUS|CHAIN|dSID|PARAMS|COMMENT" > jobs_${config_name}
echo "===== JOBS: =====" >> jobs_${config_name}
cd ..
echo "Created jobs file."

# Schedule file
mkdir -p schedule_files
cd schedule_files
echo "from SID 000000 | Teff=23001., log ggrav=4.15, Mdot=-3.55 | comment" > schedule_${config_name}
echo "===== SCHEDULED JOBS: =====" >> schedule_${config_name}
cd ..
echo "Created schedule file."

# Config File
mkdir -p configs
cd configs
echo "jobs_file : $HOME/.postbox/jobs_files/jobs_${config_name}" > config_${config_name}
echo "schedule_file : $HOME/.postbox/schedule_files/schedule_${config_name}" >> config_${config_name}
echo "wrdata_path : $HOME/powr/wrdata{}/" >> config_${config_name}
echo "powr_out_path : $HOME/powr/output/" >> config_${config_name}
echo "powr_proc : $HOME/powr/proc.dir/" >> config_${config_name}
echo "save_path : /some/path/to/saved/models/directory/" >> config_${config_name}
echo >> config_${config_name}
echo "chain_range : 1000-1020" >> config_${config_name}
echo >> config_${config_name}
echo "machine_priority : " >> config_${config_name}
echo
read -p "Opening config file, please edit the chain_range and save_path. [ENTER to continue]" dummy
nano config_${config_name}
echo
echo "Saved config file at $HOME/.postbox/configs/config_${config_name}"
echo

# Ask to make default
if [[ -L default ]]; then
    read -p "Make config_${config_name} your default postbox config? (y/[n]): " make_default
else
    make_default="y"
fi

if [[ "${make_default}" == "y" || "${make_default}" == "Y" ]]; then
    ln -sfn config_${config_name} default
    echo
    echo "config_${config_name} is now default and will be used by postbox.py if no other config is specified."
    echo
fi

echo "Setup complete."