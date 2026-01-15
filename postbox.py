'''
Scheduler for PoWR models for keeping organized when running large grids,
or managing a fitting process. Keeps human work low by helping with small
repetetive actions. Human input changes from actively setting up models from
run to run, to simply confirming the job submission.

Author: Joris Josiek (joris.josiek@uni-heidelberg.de)
Date: 2025-12-16

'''

import numpy as np
import subprocess
import re
import os
import stat
import shutil

###########################################################################

#### CHAIN HANDLING ####

class Chain:
    def __init__(self, number=9999, host='', wrstart='', wruniq='', formal='', path='', comment=''):
        self.number = number
        self.host = host
        self.wrstart = wrstart
        self.wruniq = wruniq
        self.formal = formal
        self.comment = comment
        self.path = path
        self.currentSID = self.get_SID()
    
    def get_SID(self):
        pattern = r'\[SID ([0-9]{6})\]'
        match = re.search(pattern, self.comment)
        if match:
            self.currentSID = int(match.group(1))
        else:
            self.currentSID = None
        return self.currentSID
    
    def change_comment(self, comment:str):
        '''
        Change comment to display in the stat command
        '''
        self.comment = comment

    def remove_SID(self):
        new_comment = ""
        self.change_comment(new_comment)
        self.currentSID = None
    
    def assign_SID(self, newSID:int):
        new_comment = "[SID {:06}]".format(newSID)
        self.change_comment(new_comment)
        self.currentSID = self.get_SID()

    
class ChainManager:
    def __init__(self, settings):
        self.chains : dict[int, Chain] = {}
        self.powr_proc = settings['powr_proc']
        self.wrdata_path = settings['wrdata_path']
        self.usable_numbers = settings['chain_range']
        self.load_chains()

    def get_free_chains(self):
        return [chain for chain in self.chains.values() if chain.currentSID == None]
    
    def get_converged_chains(self):
        return [chain for chain in self.chains.values() if chain.currentSID != None and 
                chain.wrstart.strip() == 'done' and chain.wruniq.strip() == 'Conv' and chain.formal.strip() == 'done']
    
    def get_crashed_chains(self):
        return [chain for chain in self.chains.values() if chain.currentSID != None and
                ('AB' in chain.wrstart or 'AB' in chain.wruniq or 'AB' in chain.formal)]
    
    def get_active_chains(self):
        return [chain for chain in self.chains.values() if chain.currentSID != None and
                ('ACTIVE' in chain.wrstart or 'ACTIVE' in chain.wruniq or 'ACTIVE' in chain.formal)]

    def write_chain_comment(self, chain:Chain):
        subprocess.run([self.powr_proc+'status.com', 'name', 'wruniq{}'.format(chain.number), chain.comment], capture_output=True)


    def load_chains(self):
        '''
        Run the stat command, pipe the output, return list of chain objects.
        '''
        stat_output = subprocess.run(self.powr_proc+'status.com', capture_output=True, text=True).stdout.split('\n')
        stat_full = [l.split('\t') for l in stat_output if l[:4] == 'Ket.']
        stat_cut = [l for l in stat_full if int(l[0][4:]) in range(*self.usable_numbers)] 

        for ket in stat_cut:
            chain_number = int(ket[0][4:])
            chain = Chain(chain_number, 
                          ket[1], 
                          ket[2], 
                          ket[3], 
                          ket[5], 
                          self.wrdata_path.format(chain_number), 
                          ket[6])
            self.chains[chain.number] = chain

#### JOB HANDLING ####

class Job:
    def __init__(self, sid, status, currentChain, dependent_sid, params_string, comment):
        self.SID = sid
        self.model_path = None
        self.currentChain = currentChain
        self.dependent_SID = dependent_sid
        self.params_string = params_string
        self.comment = comment
        self.status = None
        self.change_status(status)

    def change_chain(self, currentChain):
        self.currentChain = currentChain

    def remove_chain(self):
        self.currentChain = None

    def change_status(self, new_status):
        self.status = new_status
        

class JobManager:
    def __init__(self, settings):
        self.jobs_file = settings['jobs_file']
        self.schedule_file = settings['schedule_file']
        self.wrdata_path = settings['wrdata_path']
        self.powr_proc = settings['powr_proc']
        self.save_path = settings['save_path']
        self.file_header = None
        self.jobs : dict[int, Job] = {}
        self.load_jobs_file()

    def load_jobs_file(self):
        '''
        Loads job data file.
        '''
        with open(self.jobs_file) as f:
            full_file = f.readlines()
        
        self.file_header = full_file[:2]
        file_body = [line for line in full_file[2:] if line != '\n']
        for line in file_body:
            line_data = line.strip().split('|')
            sid = int(line_data[0])
            try:
                currentChain = int(line_data[2])
            except ValueError:
                currentChain = None
            try:
                dependent_SID = int(line_data[3])
            except ValueError:
                dependent_SID = None
            job = Job(sid, line_data[1], currentChain,
                      dependent_SID, line_data[4], line_data[5])
            self.jobs[sid] = job
            self.update_model_path(job)

    def update_model_path(self, job:Job):
        if job.status == 'Complete':
            job.model_path = self.save_path + "{:06}/".format(job.SID)
        else:
            job.model_path = None


    def save_jobs_file(self):
        save_string = ""
        save_string += self.file_header[0] + self.file_header[1]
        for sid in self.jobs:
            j = self.jobs[sid]
            chainstr = j.currentChain
            if chainstr == None:
                chainstr = ''
            dSIDstr = j.dependent_SID
            if dSIDstr == None:
                dSIDstr = ''
            else:
                dSIDstr = '{:06}'.format(dSIDstr)
            save_string = save_string + '{:06}|{}|{}|{}|{}|{}\n'.format(
                j.SID, j.status, chainstr, dSIDstr, j.params_string, j.comment
            )
        save_string.strip()
        
        with open(self.jobs_file, 'w') as f:
            f.write(save_string)

    def new_sid(self):
        used_sids = [sid for sid in self.jobs]
        available_sids = [sid for sid in np.arange(1, 900000) if sid not in used_sids]
        return np.min(available_sids)

    def create_job(self, from_sid, job_params, comment):
        '''
        Creates a Job object and prepends it to the jobs list.
        '''
        new_job = Job(self.new_sid(), 'Waiting', None, from_sid, job_params, comment)
        self.jobs[new_job.SID] = new_job
        return new_job.SID
    
    def filter_by_status(self, status):
        return [job for job in self.jobs.values() if job.status == status]
    
    def ready_to_stage(self, job:Job):
        return ( job.dependent_SID in self.jobs and self.jobs[job.dependent_SID].status == 'Complete' )
    
    def prioritize_jobs(self, jobs_list):
        # Add code to change the order of the jobs and return in a new list
        ordered_jobs_list = jobs_list
        return ordered_jobs_list
    
    def submit_job(self, job:Job, host):
        '''
        Submits the wrstart to PoWR for a job.
        '''
        subprocess.run([self.powr_proc+'submit.com', 
                        'wrstart{}'.format(job.currentChain), 
                        'to-{}'.format(host)], capture_output=True)
        
    def get_dependency_chain(self, job:Job):
        '''
        Returns ordered list of models following the chain of dependencies.
        '''
        model_list = [job]
        while model_list[-1].dependent_SID != None:
            model_list.append(self.jobs[model_list[-1].dependent_SID])
        return model_list


    def view_jobs(self, jobs_list:list[Job]):
        for job in jobs_list:
            print_str = "SID {:06} {:>8}".format(job.SID, job.status)
            if job.params_string != "":
                print_str = print_str +  " ({:<20})".format(job.params_string)
            if job.currentChain != None:
                print_str = print_str + " [Chain {:<4}]".format(job.currentChain)
            if job.dependent_SID != None:
                print_str = print_str + " from SID {:06}".format(job.dependent_SID)
            print_str = print_str + " | {}".format(job.comment)
            print(print_str)

    def generateCARDS(self, old_cards_path, new_cards_path, params_string, sid=999999):
        '''
        Generates CARDS file.
        '''

        if '=' in params_string:
            params_dict = {p.split('=')[0].strip():p.split('=')[1].strip() 
                    for p in params_string.split(',')}
        else:
            # Happens when user does not pass any parameters.
            # (e.g. to rerun a model, or make manual changes only)
            params_dict = {}
        params_dict['HEADLINE'] = 'SID {:06}'.format(sid)

        if not os.path.exists(old_cards_path):
            raise RuntimeError("Could not generate CARDS. Old CARDS missing from path\n{}".format(old_cards_path))

        with open(old_cards_path) as f:
            cards_str = f.read()

        new_cards_str = cards_str
        for key, val in params_dict.items():
            if key == 'HEADLINE':
                pattern = rf"(^[^-]?.*\s{re.escape(key)}\s*[:=]?\s*)(\S+.*$)"
            else:
                pattern = rf"(^[^-]?.*\s{re.escape(key)}\s*[:=]?\s*)(\S+)"
            new_cards_str = re.sub(
                pattern,
                rf"\g<1>{val}",
                new_cards_str,
                flags=re.MULTILINE
            )
        
        with open(new_cards_path, 'w') as f:
            f.write(new_cards_str)



class Scheduler:
    def __init__(self, config_file=None):
        self.config_file = config_file
        self.settings = self.read_config_file(config_file)
        self.schedule_file = self.settings['schedule_file']
        self.powr_proc = self.settings['powr_proc']
        self.machine_priority = self.settings['machine_priority']
        self.powr_out_path = self.settings['powr_out_path']
        self.save_path = self.settings['save_path']
        self.CM = ChainManager(self.settings)
        self.JM = JobManager(self.settings)
        self.ready_job_consistency_check()
        self.job_chain_crossmatch_check()
        self.active_job_consistency_check()

    def read_config_file(self, config_file):
        '''
        Make settings dictionary
        '''
        settings_dict = {}
        if not os.path.exists(config_file):
            raise RuntimeError("Config file not found at path: {}".format(config_file))
        with open(config_file) as f:
            raw_config = f.readlines()
        split_config = [line.split(':') for line in raw_config if line[0] not in ['#',' ','\n']]
        settings_dict = {k[0].strip():k[1].strip() for k in split_config}
        chain_range_str = settings_dict['chain_range'].split('-')
        settings_dict['chain_range'] = (int(chain_range_str[0]),
                                        int(chain_range_str[1])+1)
        if settings_dict['machine_priority'] != '':
            settings_dict['machine_priority'] = [host.strip() for host in settings_dict['machine_priority'].split(',')]
        else:
            settings_dict['machine_priority'] = []
        return settings_dict

        
    def job_chain_crossmatch_check(self):
        '''
        Checks that chain-to-sid and sid-to-chain assignment is consistent and raises warnings if it is not so.
        '''
        chains_to_sid = {number : self.CM.chains[number].currentSID for number in self.CM.chains}
        sid_to_chains = {sid : self.JM.jobs[sid].currentChain for sid in self.JM.jobs}
        okay = True
        for number, sid in chains_to_sid.items():
            if sid and (sid not in sid_to_chains or sid_to_chains[sid] != number):
                print("[SCHEDULER] Warning! Chain {} blocked by wrong label SID {:06}. Check manually.".format(number, sid))
                okay = False
        for sid, number in sid_to_chains.items():
            if number and (number not in chains_to_sid or chains_to_sid[number] != sid):
                print("[SCHEDULER] Warning! SID {:06} assigned to unlabeled Chain {}. Check manually.".format(sid, number))
                okay = False
        if not okay:
            print("❌ Job/Chain inconsistencies detected.\n\nCheck jobs file: {}\nCheck chains with stat.".format(self.JM.jobs_file))
            print("\npostbox.py stopped.")
            exit()

    def ready_job_consistency_check(self):
        '''
        Checks to make sure that Ready indeed have a chain number assigned.
        '''
        changes_made = False
        for job in self.JM.filter_by_status('Ready'):
            if job.currentChain == None:
                print("[SCHEDULER] Looks like job SID {:06} with status 'Ready' does not have a chain assignment.".format(job.SID))
                job.change_status('Waiting')
                print("[SCHEDULER] --> Job SID {:06} changed to status 'Waiting'.".format(job.SID))
                changes_made = True
        if changes_made:
            self.JM.save_jobs_file()

    def active_job_consistency_check(self):
        '''
        Checks to make sure that active PoWR models are also marked as active. Helps to keep track of manual launches.
        '''
        changes_made = False
        for chain in self.CM.get_active_chains():
            job = self.JM.jobs[chain.currentSID]
            if job.status == 'Ready':
                print("[SCHEDULER] Looks like job SID {:06} with status 'Ready', currently on chain {}, has already been submitted.".format(job.SID, chain.number))
                job.change_status('Active')
                print("[SCHEDULER] --> Job SID {:06} changed to status 'Active'.".format(job.SID))
                changes_made = True
        if changes_made:
            self.JM.save_jobs_file()
            
    
    def get_machine_occupancy(self):
        '''
        Reads the output of psx and returns a dictionary of machine names with number of available/total cores.
        '''
        occupancy_dict = {}
        psx_output = subprocess.run([self.powr_proc+'psx.com', 'all'], capture_output=True, text=True).stdout.split('\n')
        psx_stripped = [line for line in psx_output if 'HOST' in line or 'Efficiency' in line]
        psx_filtered = []
        for line, next_line in zip(psx_stripped[:-1], psx_stripped[1:]):
            if 'HOST' in line and 'Efficiency' in next_line:
                psx_filtered.append(line)
                psx_filtered.append(next_line)
        for host_info, usage_info in zip(psx_filtered[::2], psx_filtered[1::2]):
            machine_string = host_info + ' ' + usage_info
            pattern = r"HOST = (.+) \(.+ ([0-9]+) active PoWR programs, ([0-9]+) Cores available"
            match = re.search(pattern, machine_string)
            if match:
                host_name = match.group(1).strip()
                occupied_cores = int(match.group(2))
                total_cores = int(match.group(3))
                occupancy_dict[host_name] = (occupied_cores, total_cores)
        return occupancy_dict
    
    def make_machine_order(self, occupancy):
        '''
        Generates an ordered list of machines to host models based on occupancy.
        '''
        free_cores_dict = {host : max(occupancy[host][1]-occupancy[host][0], 0) for host in occupancy}
        ordered_hosts = sorted(free_cores_dict, key=free_cores_dict.get, reverse=True)
        non_prioritized = [host for host in ordered_hosts if host not in self.machine_priority]
        prioritized = [host for host in self.machine_priority if host in ordered_hosts] # Important because only ordered_hosts are available

        machine_order = []
        for host in prioritized:
            for _ in range(free_cores_dict[host]-1):
                machine_order.append(host)
        for host in non_prioritized:
            for _ in range(free_cores_dict[host]-1):
                machine_order.append(host)

        return machine_order
    
    def load_job_to_chain(self, job:Job, chain:Chain):
        '''
        Loads a model into a chain. WARNING: handles file operations incl. copying and deleting, modify with care.
        '''
        # Check if old model files are all there.
        old_model_path = self.JM.jobs[job.dependent_SID].model_path
        required_files = ['CARDS', 
                          'DATOM', 
                          'FEDAT', 
                          'FEDAT_FORMAL', 
                          'FGRID', 
                          'FORMAL_CARDS', 
                          'MODEL']
        
        required_file_check = {}
        for file in required_files:
            if not os.path.exists(old_model_path + file):
                required_file_check[file] = False
            else:
                required_file_check[file] = True
        if False in required_file_check.values():
            raise RuntimeError("Dependencies missing!\n Path: {}\n Missing Files: {}".format(
                old_model_path, [f for f in required_files if not required_file_check[f]]))

        # Check if the chain is occupied. Should not happen here because ChainManager.get_free_chains()
        # already checks this before this chain is used for a new job, but redundancy is very important
        # here given the chain's wrdata directory is about to be wiped clean.
        if chain.currentSID != None:
            raise RuntimeError("Tried to use an occupied chain. Chain {} with SID {:06}".format(
                chain.number, chain.currentSID))

        # Clear the chain
        for entry in os.scandir(chain.path):
            full_path = entry.path
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)

        # Generate new CARDS
        old_cards_path = old_model_path + 'CARDS'
        new_cards_path = chain.path + 'CARDS'
        
        self.JM.generateCARDS(old_cards_path, new_cards_path, job.params_string, job.SID)

        # Fill the chain
        for file in required_files:
            if file != 'CARDS':
                shutil.copy2(old_model_path + file, chain.path + file, follow_symlinks=False)
                if 'FEDAT' not in file:
                    os.chmod(chain.path + file, os.stat(chain.path+file).st_mode | stat.S_IWUSR)
        shutil.copy2(old_model_path + 'MODEL', chain.path + 'MODEL_OLD')
        

        # Bookkeeping
        job.change_chain(chain.number)
        chain.assign_SID(job.SID)
        self.CM.write_chain_comment(chain)

    def archive_job_data(self, job:Job):
        '''
        Saves jobs data to its directory. Practically mimicks PoWR's own modsave.
        '''
        destination_dir = self.save_path + '{:06}/'.format(job.SID)
        powr_output = self.powr_out_path
        if not os.path.exists(destination_dir):
            os.makedirs(destination_dir)
        chain = self.CM.chains[job.currentChain]

        # Copy the whole chain except certain useless files
        for entry in os.scandir(chain.path):
            if entry.name not in ['backup', 'next_job', 'next_jobz']:
                shutil.copy2(entry.path, destination_dir+entry.name, follow_symlinks=False)

        # Copy extra output files from the PoWR output directory
        for output_file in ['formal{}.out', 'formal{}.plot', 
                            'wruniq{}.out', 'wruniq{}.plot', 'wrstart{}.out']:
            source_file = powr_output + output_file.format(chain.number)
            dest_file = destination_dir + output_file.format('')
            shutil.copy2(source_file, dest_file)

    def Queue(self):
        '''
        Queue all the jobs in the schedule file.
        '''
        with open(self.schedule_file) as f:
            schedule_raw = f.readlines()

        schedule_headstr = schedule_raw[0] + schedule_raw[1]
        schedule_list = [line for line in schedule_raw[2:] if '|' in line]

        if schedule_list == []:
            print('[QUEUE] No new jobs to queue.')
        
        for line in schedule_list:
            params = line.split('|')
            new_SID = self.JM.create_job(int(params[0][9:15]), params[1].strip().upper(), params[2].strip())
            print('[QUEUE] New job with SID {:06} created.'.format(new_SID))

        self.JM.save_jobs_file()
        with open(self.schedule_file, 'w') as f:
            f.write(schedule_headstr)

    def Stage(self):
        '''
        Load all waiting jobs into chains if possible.
        '''
        self.CM.load_chains()
        free_chains = self.CM.get_free_chains()
        waiting_jobs = self.JM.filter_by_status('Waiting')

        loadable_jobs = [j for j in waiting_jobs if self.JM.ready_to_stage(j)]
        
        jobs_list = self.JM.prioritize_jobs(loadable_jobs)

        if jobs_list == []:
            print("[STAGE] No jobs to stage.")
            return
        elif free_chains == []:
            print("[STAGE] No free chains to load jobs.")
            return

        chain_counter = 0
        for job in jobs_list:
            try:
                chain_to_use = free_chains[chain_counter]
                self.load_job_to_chain(job, chain_to_use)
                job.change_status('Ready')
                print("[STAGE] Job SID {:06} successfully loaded into Chain {}.".format(job.SID, chain_to_use.number))
                chain_counter += 1
            except RuntimeError as e:
                print("[STAGE] Warning! Job with SID {:06} could not be loaded.\n".format(job.SID) + str(e))
            if chain_counter == len(free_chains):
                break
        
        self.JM.save_jobs_file()
    

    def Submit(self):
        '''
        Submit all ready jobs.
        '''
        ready_jobs = self.JM.filter_by_status('Ready')

        change_made = False
        if ready_jobs != []:
            machine_occupancy = self.get_machine_occupancy()
            machine_order = self.make_machine_order(machine_occupancy)

            # Loop cycles through jobs and hosts in parallel and
            # stops submitting when the first list is exhausted.
            for job, host in zip(ready_jobs, machine_order):
                self.JM.submit_job(job, host)
                print('[SUBMIT] Job SID {:06} : wrstart on Chain {} submitted to {}.'.format(
                    job.SID, job.currentChain, host
                ))
                job.change_status('Active')
                change_made = True

        if change_made:
            self.JM.save_jobs_file()
        else:
            print('[SUBMIT] No jobs to submit.')

    def Retrieve(self):
        '''
        Save converged models and frees the chain.
        '''
        self.CM.load_chains()
        converged_chains = self.CM.get_converged_chains()

        change_made = False
        for chain in converged_chains:
            job = self.JM.jobs[chain.currentSID]
            # Important, because otherwise this affects Ready jobs whose chain
            # still shows previous converged status.
            if job.status != 'Active':
                continue
            self.archive_job_data(job)
            
            # Unlink job and chain attributes
            job.remove_chain()
            chain.remove_SID()

            # Update the job status
            job.change_status('Complete')
            change_made = True

            # Let the managers know the change
            self.CM.write_chain_comment(chain)
            self.JM.update_model_path(job)

            # Print user output
            print("[RETRIEVE] Saved model SID {:06} and unloaded from chain {}".format(job.SID, chain.number))
        
        self.JM.save_jobs_file()
        if not change_made:
            print("[RETRIEVE] No converged chains to retrieve.")

    def Clean(self, sid=None):
        '''
        Cleans up crashed jobs. Marks the job as "Aborted" and removes the sid from the chain.
        Pass SID as argument to target a specific job, otherwise all crashed jobs are aborted.
        '''
        if not sid:
            self.CM.load_chains()
            sid_list = [chain.currentSID for chain in self.CM.get_crashed_chains() 
                        if self.JM.jobs[chain.currentSID].status == 'Active']
            if len(sid_list) == 0:
                print("[CLEAN] No active crashed jobs to clean.")
            else:
                response = input("\n[CLEAN] Are you sure you want to abort SID(s) {} (y/[n])?".format(sid_list))
                if response == "y":
                    for s in sid_list:
                        self.Clean(s) # A bit of neat recursion here.
        
        else:
            sid = int(sid)
            try:
                chain_number = self.JM.jobs[sid].currentChain
                if chain_number == None:
                    print("[CLEAN] Requested SID {:06} is not currently loaded in a chain. No action taken.".format(sid))
            except KeyError:
                print("[CLEAN] Requested SID {:06} does not exist.".format(sid))
                chain_number = None
            if chain_number != None:
                chain = self.CM.chains[chain_number]
                chain.remove_SID()
                subprocess.run([self.powr_proc+'status.com', 'name', 'wruniq{}'.format(chain.number), chain.comment], capture_output=True)

                self.JM.jobs[sid].remove_chain()
                self.JM.jobs[sid].change_status("Aborted")
                print("[CLEAN] Aborted SID {:06}.".format(sid))

        
        self.JM.save_jobs_file()


    def view_dashboard(self):
        """View current status summary of jobs and chains."""
        complete_jobs = len(self.JM.filter_by_status('Complete'))
        aborted_jobs = len(self.JM.filter_by_status('Aborted'))
        active_jobs = len(self.JM.filter_by_status('Active'))
        ready_jobs = len(self.JM.filter_by_status('Ready'))
        waiting_jobs = len(self.JM.filter_by_status('Waiting'))
        self.CM.load_chains()
        running_chains = len(self.CM.get_active_chains())
        converged_chains = len(self.CM.get_converged_chains())
        crashed_chains = len(self.CM.get_crashed_chains())
        free_chains = len(self.CM.get_free_chains())
        print()
        print("-"*80)
        print("[ Config file: {} ]".format(self.config_file))
        print("-"*80)
        print("JOBS:")
        print("  {} In Progress ({} Waiting 😴 | {} Ready 🫡  | {} Active 😎)".format(waiting_jobs +ready_jobs +active_jobs,
                                                                            waiting_jobs, ready_jobs, active_jobs))

        print("  {} Past ({} Complete 😄 | {} Aborted 😵)".format(complete_jobs +aborted_jobs,
                                                            complete_jobs, aborted_jobs))
        print()
        print("CHAINS:")
        print("  {} Active ({} Running 🌟, {} Converged 🤩, {} Crashed 🫠 )".format(running_chains +converged_chains +crashed_chains,
                                                                          running_chains, converged_chains, crashed_chains))
        print("  {} Free".format(free_chains))
        print("-"*80)
        if crashed_chains != 0:
            print("The following crashed models require your attention:\n")
            for chain in self.CM.get_crashed_chains():
                print("  SID {:06} in Chain {}".format(chain.currentSID, chain.number))
            print("\nTreat manually, or clean.\n")


def launch_interactive_shell(config_path):

    print("\n-----")
    print(" PoWR Scheduling Toolbox [postbox.py] ")
    print("-----")

    SC = Scheduler(config_path)
    SC.view_dashboard()

    def help():
        """View this help text."""
        print()
        for com_name, com_func in command_dict.items():
            print("{} : {}".format(com_name, com_func.__doc__.strip()))
        print()

    def auto_update():
        """Automatically run through one scheduler cycle of Retrieve, Queue, Stage, Submit."""
        SC.Retrieve()
        SC.Queue()
        SC.Stage()
        SC.Submit()
    
    def edit_schedule():
        """Edit the schedule file"""
        subprocess.run(["nano", str(SC.settings['schedule_file'])])

    def show_completed():
        """List completed jobs"""
        complete_jobs = SC.JM.filter_by_status('Complete')
        SC.JM.view_jobs(complete_jobs)

    def show_current():
        """List current Waiting, Ready, and Active Jobs"""
        active_jobs = SC.JM.filter_by_status('Active')
        ready_jobs = SC.JM.filter_by_status('Ready')
        waiting_jobs = SC.JM.filter_by_status('Waiting')
        SC.JM.view_jobs(active_jobs+ready_jobs+waiting_jobs)

    def stat_chains():
        """Lists active jobs and their chain status"""
        active_jobs = SC.JM.filter_by_status('Active')

        SC.CM.load_chains()
        free_chains = [chain.number for chain in SC.CM.get_free_chains()]
        crashed_chains = [chain.number for chain in SC.CM.get_crashed_chains()]
        active_chains = [chain.number for chain in SC.CM.get_active_chains()]
        converged_chains = [chain.number for chain in SC.CM.get_converged_chains()]
        
        crashed_jobs = [job for job in active_jobs if job.currentChain in crashed_chains]
        converged_jobs = [job for job in active_jobs if job.currentChain in converged_chains]
        running_jobs = [job for job in active_jobs if job.currentChain in active_chains]

        if crashed_jobs != []:
            print("=== CRASHED JOBS ===")
            SC.JM.view_jobs(crashed_jobs)
            print()
        
        if converged_jobs != []:
            print("=== CONVERGED JOBS ===")
            SC.JM.view_jobs(converged_jobs)
            print()

        if running_jobs != []:
            print("=== RUNNING JOBS ===")
            SC.JM.view_jobs(running_jobs)
            print()

        if free_chains != []:
            print("=== FREE CHAINS ===")
            print(free_chains)
            print()


    def view_traceback(sid):
        """View dependency chain for a given SID"""
        try:
            sid = int(sid)
        except ValueError:
            print('Invalid SID.')
            return
        try:
            model_list = SC.JM.get_dependency_chain(SC.JM.jobs[sid])
            SC.JM.view_jobs(model_list)
        except KeyError:
            print('Job SID {:06} does not exist.'.format(sid))     

    def exit_scheduler():
        """Exit the postbox."""
        exit()

    command_dict = {'help':help,
                    'exit':exit_scheduler,
                    'auto':auto_update,
                    'stat':SC.view_dashboard,
                    'edit':edit_schedule,
                    'retrieve':SC.Retrieve,
                    'queue':SC.Queue,
                    'stage':SC.Stage,
                    'submit':SC.Submit,
                    'clean':SC.Clean,
                    'listc':show_completed,
                    'list':show_current,
                    'statc':stat_chains,
                    'trace':view_traceback}

    while True:
        command = input("\n>>> ").split(' ')
        args = []
        if len(command) > 1:
            args = command[1:]
        func = command_dict.get(command[0])
        if func is None:
            print("Command does not exist. Type help for list of available commands.")
            continue
        try:
            func(*args)
        except TypeError:
            print("Command syntax incorrect.")

def main():

    import argparse
    parser = argparse.ArgumentParser(description="PoWR Scheduling Toolbox")

    parser.add_argument(
        "--config",
        type=str,
        help="Path to config file (overrides default config)"
    )

    args = parser.parse_args()

    user_home = os.environ['HOME']
    if args.config:
        config_path = args.config
        if config_path[0] != '/':
            config_path = os.getcwd() + '/{}'.format(config_path)
    else:
        config_path = '{}/.postbox/configs/default'.format(user_home)

    launch_interactive_shell(config_path)

if __name__ == "__main__":
    main()


