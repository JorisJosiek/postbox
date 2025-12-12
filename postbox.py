'''
Scheduler for PoWR models for keeping organized when running large grids,
or managing a fitting process. Keeps human work low by helping with small
repetetive actions. Human input changes from actively setting up models from
run to run, to simply confirming the job submission.

Author: Joris Josiek (joris.josiek@uni-heidelberg.de)
Date: 2025-12-01

'''

import numpy as np
import subprocess
import re
import os
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
    
    def change_comment(self, comment):
        '''
        Change comment to display in the stat command
        '''
        self.comment = comment

    def remove_SID(self):
        new_comment = ""
        self.change_comment(new_comment)
        self.currentSID = None
    
    def assign_SID(self, newSID):
        new_comment = "[SID {:06}]".format(newSID)
        self.change_comment(new_comment)
        self.currentSID = self.get_SID()

    
class ChainManager:
    def __init__(self, powr_proc, wrdata_path, use_chains):
        self.chains = {}
        self.powr_proc = powr_proc
        self.wrdata_path = wrdata_path
        self.usable_numbers = use_chains
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


    def load_chains(self):
        '''
        Run the stat command, pipe the output, return list of chain objects.
        '''
        stat_output = subprocess.run(self.powr_proc+'status.com', capture_output=True, text=True).stdout.split('\n')
        stat_full = [l.split('\t') for l in stat_output if l[:4] == 'Ket.']
        stat_cut = [l for l in stat_full if int(l[0][4:]) in self.usable_numbers] 
        
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
    def __init__(self, 
                 jobs_file, 
                 schedule_file, 
                 wrdata_path, 
                 powr_proc,
                 save_path):
        self.jobs_file = jobs_file
        self.schedule_file = schedule_file
        self.wrdata_path = wrdata_path
        self.powr_proc = powr_proc
        self.save_path = save_path
        self.file_header = None
        self.jobs = {}
        self.load_jobs_file()

    def load_jobs_file(self):
        '''
        Loads data file and returns a list of Job objects, in order
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

    def update_model_path(self, job):
        if job.status == 'Complete':
            job.model_path = self.save_path + str(job.SID) + '/'
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
    
    def ready_to_stage(self, job):
        return ( job.dependent_SID in self.jobs and self.jobs[job.dependent_SID].status == 'Complete' )
    
    def load_job_to_chain(self, job, chain):
        '''
        Loads a model into a chain. WARNING: handles file operations incl. copying and deleting, modify with care.
        '''
        # Check if old model files are all there.
        old_model_path = self.jobs[job.dependent_SID].model_path
        required_files = ['CARDS', 
                          'DATOM', 
                          'FEDAT', 
                          'FEDAT_FORMAL', 
                          'FGRID', 
                          'FORMAL_CARDS', 
                          'MODEL', 
                          'NEWDATOM_INPUT', 
                          'NEWFORMAL_CARDS_INPUT']
        
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
        
        self.generateCARDS(old_cards_path, new_cards_path, job.params_string, job.SID)

        # Fill the chain
        for file in required_files:
            if file != 'CARDS':
                shutil.copy2(old_model_path + file, chain.path + file, follow_symlinks=False)
        shutil.copy2(old_model_path + 'MODEL', chain.path + 'MODEL_OLD')


        # Bookkeeping
        job.change_chain(chain.number)
        chain.assign_SID(job.SID)
        subprocess.run([self.powr_proc+'status.com', 'name', 'wruniq{}'.format(chain.number), chain.comment], capture_output=True)


    def generateCARDS(self, old_cards_path, new_cards_path, params_string, sid=999999):
        '''
        Generates CARDS file.
        '''

        params_dict = {p.split('=')[0].strip():p.split('=')[1].strip() 
                   for p in params_string.split(',')}
        params_dict['HEADLINE'] = 'SID{}'.format(sid)

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

    def submit_job(self, job, host):
        '''
        Submits the wrstart to PoWR for a job.
        '''
        subprocess.run([self.powr_proc+'submit.com', 
                        'wrstart{}'.format(job.currentChain), 
                        'to-{}'.format(host)], capture_output=True)




class Scheduler:
    def __init__(self, config_file=None):
        self.settings = self.read_config_file(config_file)
        self.schedule_file = self.settings['schedule_file']
        self.powr_proc = self.settings['powr_proc']
        self.machine_priority = self.settings['machine_priority']
        self.CM = ChainManager(self.settings['powr_proc'],
                               self.settings['wrdata_path'],
                               self.settings['chain_range'])
        self.JM = JobManager(self.settings['jobs_file'],
                             self.settings['schedule_file'],
                             self.settings['wrdata_path'],
                             self.settings['powr_proc'],
                             self.settings['save_path'])
        self.ready_job_consistency_check()
        self.job_chain_crossmatch_check()
        self.active_job_consistency_check()

    def read_config_file(self, config_file):
        '''
        Make settings dictionary
        '''
        settings_dict = {}
        with open(config_file) as f:
            raw_config = f.readlines()
        split_config = [line.split(':') for line in raw_config if line[0] not in ['#',' ','\n']]
        settings_dict = {k[0].strip():k[1].strip() for k in split_config}
        chain_range_str = settings_dict['chain_range'].split('-')
        settings_dict['chain_range'] = (int(chain_range_str[0]),
                                        int(chain_range_str[1])+1)
        settings_dict['machine_priority'] = [host.strip() for host in settings_dict['machine_priority'].split(',')]
        return settings_dict

        
    def job_chain_crossmatch_check(self):
        '''
        Checks that chain-to-sid and sid-to-chain assignment is consistent and raises warnings if it is not so.
        '''
        chains_to_sid = {number : self.CM.chains[number].currentSID for number in self.CM.chains}
        sid_to_chains = {sid : self.JM.jobs[sid].currentChain for sid in self.JM.jobs}
        for number, sid in chains_to_sid.items():
            if sid and (sid not in sid_to_chains or sid_to_chains[sid] != number):
                print("[SCHEDULER] Warning! Chain {} blocked by wrong label SID {:06}. Check manually.".format(number, sid))
        for sid, number in sid_to_chains.items():
            if number and (number not in chains_to_sid or chains_to_sid[number] != sid):
                print("[SCHEDULER] Warning! SID {:06} assigned to unlabeled Chain {}. Check manually.".format(sid, number))

    def ready_job_consistency_check(self):
        '''
        Checks to make sure that Ready indeed have a chain number assigned.
        '''
        for job in self.JM.filter_by_status('Ready'):
            if job.currentChain == None:
                print("[SCHEDULER] Looks like job SID {:06} with status 'Ready' does not have a chain assignment.".format(job.SID))
                job.change_status('Waiting')
                print("[SCHEDULER] --> Job SID {:06} changed to status 'Waiting'.".format(job.SID))

    def active_job_consistency_check(self):
        '''
        Checks to make sure that active PoWR models are also marked as active. Helps to keep track of manual launches.
        '''
        for chain in self.CM.get_active_chains():
            job = self.JM.jobs[chain.currentSID]
            if job.status == 'Ready':
                print("[SCHEDULER] Looks like job SID {:06} with status 'Ready', currently on chain {}, has already been submitted.".format(job.SID, chain.number))
                job.change_status('Active')
                print("[SCHEDULER] --> Job SID {:06} changed to status 'Active'.".format(job.SID))
            

    def prioritize_jobs(self, jobs_list):
        # Add code to change the order of the jobs and return in a new list
        ordered_jobs_list = jobs_list
        return ordered_jobs_list
    
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
        prioritized = [host for host in ordered_hosts if host in self.machine_priority] # Important because only ordered_hosts are available

        machine_order = []
        for host in prioritized:
            for _ in range(free_cores_dict[host]-1):
                machine_order.append(host)
        for host in non_prioritized:
            for _ in range(free_cores_dict[host]-1):
                machine_order.append(host)

        return machine_order

    def Queue(self):
        '''
        Queues all the jobs in the scheduler file.
        '''
        with open(self.schedule_file) as f:
            schedule_raw = f.readlines()

        schedule_headstr = schedule_raw[0] + schedule_raw[1]
        schedule_list = schedule_raw[2:]

        for line in schedule_list:
            params = line.split('|')
            new_SID = self.JM.create_job(int(params[0][9:15]), params[1].strip().upper(), params[2].strip())
            print('[QUEUE] New job with SID {:06} created.'.format(new_SID))

        self.JM.save_jobs_file()
        with open(self.schedule_file, 'w') as f:
            f.write(schedule_headstr)

    def Stage(self):
        '''
        Takes all waiting jobs and loads them into chains if possible
        '''
        free_chains = self.CM.get_free_chains()
        waiting_jobs = self.JM.filter_by_status('Waiting')

        loadable_jobs = [j for j in waiting_jobs if self.JM.ready_to_stage(j)]
        
        jobs_list = self.prioritize_jobs(loadable_jobs)

        chain_counter = 0
        for job in jobs_list:
            try:
                chain_to_use = free_chains[chain_counter]
                self.JM.load_job_to_chain(job, chain_to_use)
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
        Submits all jobs in the queue.
        '''
        ready_jobs = self.JM.filter_by_status('Ready')

        machine_occupancy = self.get_machine_occupancy()
        machine_order = self.make_machine_order(machine_occupancy)

        for job, host in zip(ready_jobs, machine_order):
            self.JM.submit_job(job, host)
            print('[SUBMIT] Job SID {:06} : wrstart chain {} submitted to {}.'.format(
                job.SID, job.currentChain, host
            ))
            job.change_status('Active')

        self.JM.save_jobs_file()

    def Retrieve(self):
        '''
        Takes converged models and saves them
        '''

        # Remember to run JM.update_model_path() *after* status set to Complete.

    def Clean(self, sid=None):
        '''
        Cleans up crashed jobs. Marks the job as "Aborted" and removes the sid from the chain.
        SID parameter can target a specific job, otherwise all crashed jobs are aborted.
        '''
        if not sid:
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
            chain_number = self.JM.jobs[sid].currentChain
            if chain_number != None:
                chain = self.CM.chains[chain_number]
                chain.remove_SID()
                subprocess.run([self.powr_proc+'status.com', 'name', 'wruniq{}'.format(chain.number), chain.comment], capture_output=True)

            self.JM.jobs[sid].remove_chain()
            self.JM.jobs[sid].change_status("Aborted")
            print("[CLEAN] Aborted SID {:06}.".format(sid))
        
        self.JM.save_jobs_file()


configfile = '/home/Tux/jjosiek/tools/postbox/config'
SC = Scheduler(configfile)
SC.JM.save_jobs_file()

#SC.Stage()
#SC.Submit()

#SC.Submit()
#SC.Queue()
#SC.JM.generateCARDS('/home/Tux/jjosiek/tools/powr-scheduler/cards/CARDS_sid900002',
#                   '/home/Tux/jjosiek/tools/powr-scheduler/cards/CARDS_test',
#                   "HYDROGEN=0.6710, BETA=1.2, TEFF=22000.")
#print(SC.get_machine_occupancy())



def view_dashboard():
    '''
    Dashboard viewer to display all active and scheduled jobs
    '''

def upon_startup():
    '''
    What is shown when starting the scheduler.
    '''
    # X total jobs
    # X active
    # X ready to submit
    # X waiting
    # X ready to schedule

    # X chains total
    # X running
    # X converged
    # X crashed
    # X free

