# AWS Automation Scripts
A collection of scripts to automate some basc AWS tasks.

## aws.py
You use different flags to select instances and the subcommand controls the action performed.

There are 4 subcommands:
 - info
 Prints out information about selected instances to the console.
 - connect
 Connects over SSH to selected instances.
 - terminate
 Terminates selected instances
 - cpu
 Displays CPU information about selected instances.
 
There are 4 ways to select instances. The default selection is everything:
 - `--iid [IID ..]`
 This selects instances based on their id. You can select multiple instances by passing in multiple ids to this argument.
 for example
 ```bash
 ./aws.py connect --iid i-0966c2c919b772051 i-0912c3d382b444210
 ./aws.py info --iid i-0966c2c919b772051
 ```
 - `--nametag [NAME ..]`
 This selects instances based on a tag called 'Name'. You can set this from the GUI.
 For example
 ```bash
 ./aws.py connect --nametag scheduler
 ./aws.py cpu --nametag scheduler
 ```
 - `-i, --inverse`
 This inverts the nametag and iid selectors. For example, you can select all machines
 that don't have the name `scheduler` with:
 ```bash
 ./aws.py connect --nametag scheduler -i
 ```
 - `--select m:n` 
 
 You can select a range from the current selection. For example, suppose you had 10 machines.
 If you want to connect to the first 3 machines that don't have the nametag `scheduler` use:
 ```bash
 ./aws.py connect --nametag scheduler -i --select 0:3
 ```
 
There are 4 ways to modify what's printed out with info:
 - `--pub-ip`
 Displays the public ip address for an instance.
 - `--priv-ip`
 Displays the private ip address for an instance.
 - `--tags` 
 Displays the tags for an instance.
 - `--state` 
 Displays the state for an instance.
 
There are a few ways to modify the CPU command:
 - `--watch`
 This starts a loop that continously gathers CPU information.
 - `--graph`
 Display CPU information as a graph rather than printing it to the terminal.
 - `--drop`
 Drop any instances that go below a certain CPU threshold. (This value is currently hardcoded to 55%).

## aws-spot.py
This provides a simple way to launch spot fleets specified in `config.json`.
Simply use `./aws-spot.py start-spot`.
