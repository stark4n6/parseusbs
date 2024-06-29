# parseusbs
Parses USB connection artifacts from offline Registry hives


Registry parser, to extract USB connection artifacts from SYSTEM, SOFTWARE, and NTUSER.dat hives  
Author: Kathryn Hedley, khedley@khyrenz.com  
Copyright 2024 Kathryn Hedley, Khyrenz Ltd  


Runs in Python3  
Uses regipy offline hive parser library from Martin G. Korman: https://github.com/mkorman90/regipy/tree/master/regipy  


**Extracts from the following keys/values:**  
  SYSTEM\Select\Current -> to get CurrentControlSet  
  SYSTEM\CurrentControlSet\Enum\USB  
  SYSTEM\CurrentControlSet\Enum\USBSTOR  
  SYSTEM\CurrentControlSet\Enum\SCSI  
  SYSTEM\MountedDevices  
  SOFTWARE\Microsoft\Windows Portable Devices\Devices  
  SOFTWARE\Microsoft\Windows Search\VolumeInfoCache  
  NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders\Desktop  
  NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2  

**Bypasses Windows permission errors on a mounted volume using chmod**  
  This only works if you're running the Terminal window as Administrator

**Dependencies:**  
  pip3 install regipy  


**Limitations:**  
  Only parses provided Registry hives; does not parse any other artefacts  
  Will only replay transaction logs if they're in the same folder as the provided Hive 


**Usage:**  
  parseUSBs.py <options>  
	
  Options:  
	-h 		          	- Print this help message  
	-s    <SYSTEM hive>  		- Parse this SYSTEM hive    
	-u    <NTUSER.dat hive> 	- Parse this NTUSER.DAT hive. This argument is optional & multiple can be provided. If omitted, connections to user accounts won\'t be made   
 	-v    <drive letter>		- Parse this mounted volume. Use either this "-v" option or the individual hive options. If this option is provided, "-s|-u|-w" options will be ignored    
 	-w    <SOFTWARE hive>	 	- Parse this SOFTWARE hive. This argument is optional. If omitted, some drive letters and volumes names may be missing in the output  
	-o    <csv|keyval>		Output to either CSV or key-value pair format. Default is key-value pairs  

**Example Usage:**  
    python3 parseUSBs.py -s SYSTEM -w SOFTWARE -u NTUSER1.DAT -u NTUSER2.DAT  
    python3 parseUSBs.py -s C:/Windows/System32/config/SYSTEM -w C:/Windows/System32/config/SOFTWARE -u C:/Users/user1/NTUSER.DAT -o csv  
    (In Windows CMD as Administrator:) python3 parseUSBs.py -v F:  
    (on WSL as Administrator:) python3 parseUSBs.py -v /mnt/f  
