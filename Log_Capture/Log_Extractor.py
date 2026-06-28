import netmiko
import traceback
import time
import os
import logging
from datetime import date
import credentials  # This is a custom python file which has a dictionary of device with jump-host details and necessary credentials [Can be a JSON]
from Alive_Checks import alive 
from Connection import net_connect

# Configure logging with date-based filename
os.makedirs('./Logs', exist_ok=True)
today = date.today().strftime('%Y-%m-%d')
log_file = f'./Logs/{today}_log_extraction.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

tacas = credentials.Credentials

# To save the output in the file
def save_data(filename, output):
    logger.info(f"Saving data to file: {filename}.log")
    try:
        with open(f'{filename}.log', 'a+') as f:
            f.write(output)
        logger.info(f"Successfully saved data to {filename}.log ({len(output)} characters)")
    except Exception as e:
        logger.error(f"Failed to save data to {filename}.log: {e}", exc_info=True)

# Gathering device details
def exec_command(ip_address, commands):
    logger.info(f"Starting command execution for device: {ip_address}")
    logger.debug(f"Commands to execute: {commands}")
    
    counter = 1
    while counter < 11:  # Max retries for one IP to retry log capture.
        logger.info(f"Connection attempt {counter}/10 for device {ip_address}")
        
        try:
            flag = False
            while not flag:
                logger.debug(f"Attempting SSH connection to {ip_address}")
                net_connect.write_channel(f"ssh -l {tacas['TACAS Username']} {ip_address}\n")  # Logging into the switch
                output = net_connect.read_channel_timing(read_timeout=1500.0, max_loops=3, last_read=2.0)
                
                if 'RSA key' in output:  # Logging into a device for the first time.
                    logger.warning(f"New RSA key detected for {ip_address}, accepting...")
                    net_connect.write_channel("yes\n")  # Saving new RSA Key
                    new_output = net_connect.read_channel_timing(read_timeout=1500.0, max_loops=3, last_read=2.0)
                    
                    if 'password' in new_output:
                        logger.debug(f"Password prompt received after RSA key acceptance for {ip_address}")
                        net_connect.write_channel(f"{tacas['TACAS Password']}\n")
                        flag = True
                        logger.info(f"Successfully authenticated to {ip_address} (new RSA key)")
                
                elif 'password' in output:  # Checking if the string is present in the output displayed
                    logger.debug(f"Password prompt received for {ip_address}")
                    net_connect.write_channel(f"{tacas['TACAS Password']}\n")  # Entering password
                    
                    auth_check = net_connect.read_channel_timing(read_timeout=1500.0, max_loops=3, last_read=2.0)
                    if 'password' in auth_check:
                        logger.error(f"Authentication failed for {ip_address} - wrong credentials")
                        net_connect.disconnect()  # Disconnecting due to wrong password entry
                        print(f'Error occurred while trying to log into device, wrong credentials entered for device with IP Address {ip_address}!')
                        flag = False
                        counter += 1
                    else:
                        flag = True
                        logger.info(f"Successfully authenticated to {ip_address}")
                
                elif 'NASTY!' in output:
                    logger.warning(f"RSA key conflict detected for {ip_address}, regenerating...")
                    # This is such that, if the RSA key of that device or from the current PC is changed, then it has to be regenerated.
                    net_connect.write_channel(f'ssh-keygen -R {ip_address}\n')
                    counter += 1
                    flag = False
                    logger.debug(f"RSA key regenerated for {ip_address}")
                
                else:
                    logger.error(f"Unknown response received while connecting to {ip_address}")
                    logger.debug(f"Unexpected output: {output}")
                    net_connect.write_channel("\x03\n\x03")
                    print(f'Unknown occurred while trying to log into device {ip_address}!')
                    print(traceback.format_exc())
                    time.sleep(2)
                    flag = False
                    counter += 1
            
            logger.info(f"Connection established to {ip_address}, switching to Cisco IOS mode")
            netmiko.redispatch(net_connect, device_type='cisco_ios')  # Necessary to communicate with Cisco IOS devices.
            
            logger.debug(f"Executing commands on {ip_address}: {len(commands)} commands")
            output = net_connect.send_multiline(commands)
            
            switch_hostname = str(net_connect.find_prompt())[:-1]  # Obtaining the device hostname.
            logger.info(f"Device hostname obtained: {switch_hostname}")
            
            logger.debug(f"Logging out from {switch_hostname}")
            net_connect.write_channel('logout\n')
            
            save_data(switch_hostname, output)
            logger.info(f'Command execution completed successfully for {switch_hostname}')
            print(f'Logs collected for - {switch_hostname}')
            time.sleep(2)
            return
        
        except Exception as e:
            logger.error(f'Exception occurred during command execution for {ip_address} (attempt {counter}): {e}', exc_info=True)
            print(f'Error occurred!\n{e}')
            print(traceback.format_exc())
        
        counter += 1
    
    logger.error(f"All connection attempts failed for {ip_address} after {counter-1} attempts")
    print(f"Gathering log for {ip_address} unsuccessful after {counter-1} attempts, proceeding further...\n")
    return

def main():
    logger.info("=== Network Automation Script Started ===")
    cmd_input, invalid_commands, commands, ip_addresses, list_of_healthy_ip, list_of_unhealthy_ip = [], [], [], [], [], []
    
    # Command input collection
    logger.info("Starting command input collection")
    print("Enter a list of show commands, hit enter key twice after final command to finish your input.\n[Only show commands]")
    var = input()
    while var != '':
        cmd_input.append(var)
        logger.debug(f"Command added: {var}")
        var = input().lower()
    
    logger.info(f"Total commands received: {len(cmd_input)}")
    
    # Command validation
    for item in cmd_input:
        if not item.startswith("show"):
            invalid_commands.append(item)
            logger.warning(f"Invalid command detected: {item}")
        else:
            commands.append(item)
            logger.debug(f"Valid command accepted: {item}")
    
    if len(invalid_commands) != 0:
        logger.warning(f"Found {len(invalid_commands)} invalid commands: {invalid_commands}")
        print(f"The following commands are invalid and will not be executed: {invalid_commands}")
    
    logger.info(f"Final command list: {len(commands)} valid commands")
    print(f"Executing the following commands: {commands}")

    # IP address collection
    logger.info("Starting IP address collection")
    print("Enter a list of IPs, hit enter key twice after final command to finish your input.")
    ip_input = input()
    while ip_input != '':
        ip_addresses.append(ip_input)
        logger.debug(f"IP address added: {ip_input}")
        ip_input = input()
    
    logger.info(f"Total IP addresses collected: {len(ip_addresses)} - {ip_addresses}")

    # Ping test option
    logger.info("Prompting user for ping test option")
    print("Do you want to perform ping test for the given IPs? [Yes/y/No/n]")
    response = input().lower()
    
    while response not in ["yes", "y", "no", "n"]:
        if response in ["yes", "y"]:
            logger.info(f"User selected ping test - testing {len(ip_addresses)} devices")
            print(f"Pinging {len(ip_addresses)} devices!\n")
            
            for item in ip_addresses:
                logger.debug(f"Pinging device: {item}")
                try:
                    boole = alive.ping_test(item)
                    if True in boole:
                        list_of_healthy_ip.append(item)
                        logger.info(f"Ping successful for {item}")
                    else:
                        list_of_unhealthy_ip.append(item)
                        logger.warning(f"Ping failed for {item}")
                except Exception as e:
                    logger.error(f"Ping test failed for {item}: {e}")
                    list_of_unhealthy_ip.append(item)

            logger.info(f"Ping test results - Healthy: {len(list_of_healthy_ip)}, Unhealthy: {len(list_of_unhealthy_ip)}")
            
            if list_of_unhealthy_ip:
                logger.warning(f'Unreachable IPs: {list_of_unhealthy_ip}')
                print(f'These IP are unreachable:\n{list_of_unhealthy_ip}')
            
            # Process healthy IPs only
            if list_of_healthy_ip:
                logger.info(f"Processing {len(list_of_healthy_ip)} healthy devices")
                counter = 1
                for item in list_of_healthy_ip:
                    logger.info(f"Processing device {counter}/{len(list_of_healthy_ip)}: {item}")
                    exec_command(item, commands)
                    print(f"[{counter}/{len(list_of_healthy_ip)}]")
                    counter += 1
            else:
                logger.warning("No healthy devices found, skipping command execution")
            break

        elif response in ["no", "n"]:
            logger.info("User skipped ping test - processing all devices")
            counter = 1
            for item in ip_addresses:
                logger.info(f"Processing device {counter}/{len(ip_addresses)}: {item}")
                exec_command(item, commands)
                print(f"[{counter}/{len(ip_addresses)}]")
                counter += 1
            break
        else:
            logger.warning(f"Invalid user input received: {response}")
            print("Please enter a valid choice from the given option which is either 'yes' or 'no'.")
            response = input().lower()
    
    logger.info("=== Network Automation Script Completed ===")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
        print("\nScript interrupted by user")
    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
        print(f"Critical error occurred: {e}")
