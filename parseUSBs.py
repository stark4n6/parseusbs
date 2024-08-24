#!/bin/python

# Registry parser, to extract USB connection artifacts from SYSTEM, SOFTWARE, and NTUSER.dat hives
# Author: Kathryn Hedley, khedley@khyrenz.com
# Copyright 2024 Kathryn Hedley, Khyrenz Ltd

# Uses regipy offline hive parser library from Martin G. Korman: https://github.com/mkorman90/regipy/tree/master/regipy
# Uses python-evtx parser from Willi Ballenthin: https://pypi.org/project/python-evtx/

# Extracts from the following Registry keys/values:
## SYSTEM\Select\Current -> to get kcurrentcontrolset
## SYSTEM\kcurrentcontrolset\Enum\USB
## SYSTEM\kcurrentcontrolset\Enum\USBSTOR
## SYSTEM\kcurrentcontrolset\Enum\SCSI
## SYSTEM\MountedDevices
## SOFTWARE\Microsoft\Windows Portable Devices\Devices
## SOFTWARE\Microsoft\Windows Search\VolumeInfoCache
## NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders\Desktop
## NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2

#Parses the following Event Logs:
## Event ID 1006 in Microsoft-Windows-Partition%4Diagnostic.evtx

# Bypasses Windows permission errors on a mounted volume using chmod
## This only works if you're running the Terminal window as Administrator

# Dependencies:
## pip3 install regipy python-evtx

# Limitations:
## Only parses Registry hives & Event Logs; does not parse any other artefacts
## Will only replay Registry transaction logs if they're in the same folder as the provided hive
## Does not detect or clean dirty event logs

# Importing libraries
import sys, os, stat, ctypes, platform, base64
import Evtx.Evtx as evtx
from xml.dom import minidom
from datetime import datetime,timedelta,timezone
from regipy.registry import RegistryHive
from regipy.recovery import apply_transaction_logs
from regipy.utils import calculate_xor32_checksum
from binascii import hexlify

#Defining object for a USB device
class ExternalDevice:
	# initialising new object to empty values
	def __init__(self):
		self.name = ""
		self.iSerialNumber = ""
		self.firstConnected = ""
		self.lastConnected = ""
		self.lastRemoved = ""
		self.otherConnection = []
		self.lastDriveLetter = ""
		self.volumeName = ""
		self.diskId = ""
		self.userAccounts = []
		self.volumeSerials = []

	# method to set other connection time
	def addOtherConnection(self, khyoc):
		self.otherConnection.append(khyoc)
	# method to get other connection timestamps
	def getOtherConnections(self):
		return self.otherConnection
	# method to set last drive letter
	def setLastDriveLetter(self, khydl):
		self.lastDriveLetter = khydl
	# method to set volume name
	def setVolumeName(self, khyvn):
		self.volumeName = khyvn
	# method to set disk ID
	def setDiskId(self, khydi):
		self.diskId = khydi
	# method to get disk ID
	def getDiskId(self):
		return self.diskId
	# method to add user account
	def addUser(self, khyu):
		self.userAccounts.append(khyu)
	# method to get user accounts
	def getUsers(self):
		return self.userAccounts
	# method to add volume serial number
	def addVsn(self, khyvsn):
		self.volumeSerials.append(khyvsn)
	# method to get volume serial numbers
	def getVsns(self):
		return self.volumeSerials

		
# Function to display help info
def printHelp():
	print('Usage: python3 parseUSBs.py <options>')
	print('Options:')
	print('	-h 			Print this help message')
	print('	-s <SYSTEM hive>	Parse this SYSTEM hive')
	print('	-u <NTUSER.dat hive> 	Parse this NTUSER.DAT hive. This argument is optional & multiple can be provided.')
	print('				If omitted, connections to user accounts won\'t be made')
	print('	-v <drive letter>	Parse this mounted volume')
	print('				Use either this "-v" option or the individual hive options.')
	print('				Using this option means the Windows Partition Diagnostic Event Log will also be parsed.')
	print('				If this option is provided, "-s|-u|-w" options will be ignored')
	print('				*IMPORTANT*: Please make sure you are running this script in a terminal window that is running')
	print('				as Administrator to auto-bypass Windows permission issues')
	print('	-w <SOFTWARE hive>	Parse this SOFTWARE HIVE. This argument is optional.')
	print('				If omitted, some drive letters and volume names may be missing in the output')
	print('	-o <csv|keyval>		Output to either CSV or key-value pair format. Default is key-value pairs')
	print()
	print('Example commands:')
	print('python3 parseUSBs.py -s C:/Windows/System32/config/SYSTEM -w C:/Windows/System32/config/SOFTWARE')
	print('-u C:/Users/user1/NTUSER.DAT -o csv')
	print('python3 parseUSBs.py -s SYSTEM -w SOFTWARE -u NTUSER.DAT_user1 -u NTUSER.DAT_user2')
	print('(In Windows CMD as Administrator:) python3 parseUSBs.py -v F:')
	print('(On WSL as Administrator:) python3 parseUSBs.py -v /mnt/f')
	print()
	print('Copyright 2024 Kathryn Hedley, Khyrenz Ltd')
	print()

# Function to convert Key Last Write timestamp to readable format
# Usage - convertWin64time(kusbstorkey.header.last_modified)
def convertWin64time(khyts):
	return (datetime(1601, 1, 1) + timedelta(microseconds=(khyts//10))).replace(tzinfo=timezone.utc).isoformat()

# Function to get timestamp value (if present) as readable timestamp
def getTime(reg, regkey):
	try:
		khyconn = reg.get_key(regkey).get_value('(default)').isoformat()
	except:
		khyconn = ""
	return khyconn

# Function to output parsed data as CSV
def outputCSV(dev):
	print('Value:,Device Friendly Name,iSerialNumber,FirstConnected,LastConnected,LastRemoved,OtherConnections,LastDriveLetter,VolumeName,VolumeSerials,UserAccounts')
	print('Source:,USBSTOR-FriendlyName,USBSTOR,USBSTOR-0064,USBSTOR-0066,USBSTOR-0067,SOFTWARE-VolumeInfoCache,MountedDevices/Windows Portable Devices,Windows Portable Devices,Microsoft-Windows-Partition%4Diagnostic.evtx,NTUSER-MountPoints2')
	
	for khyd in dev:
		uacc=""
		for khyu in khyd.userAccounts:
			if uacc == "":
				uacc = khyu
			else:
				uacc += "|"+khyu
		oconn=""
		for khyocn in khyd.otherConnection:
			if oconn == "":
				oconn = khyocn
			else:
				oconn += "|"+khyocn
		vsns=""
		for khyvs in khyd.volumeSerials:
			if vsns == "":
				vsns = khyvs
			else:
				vsns += "|"+khyvs
		print(','+khyd.name+','+khyd.iSerialNumber+','+khyd.firstConnected+','+khyd.lastConnected+','+khyd.lastRemoved+','+oconn+','+khyd.lastDriveLetter+','+khyd.volumeName+','+vsns+','+uacc)

# Function to output parsed data as Key/Value pairs
def outputKV(dev):
	for khyd in dev:
		print("Device Friendly Name:", khyd.name)
		print("iSerialNumber:", khyd.iSerialNumber)
		print("First Connected:", khyd.firstConnected)
		print("Last Connected:", khyd.lastConnected)
		print("Last Removed:", khyd.lastRemoved)
		for khyocn in khyd.otherConnection:
			print("Other Connection:", khyocn)
		print("Last Drive Letter:", khyd.lastDriveLetter)
		print("Volume Name:", khyd.volumeName)
		for khyvs in khyd.volumeSerials:
			print("VSN:", khyvs)
		for khyu in khyd.userAccounts:
			print("User Account:", khyu)
		print()

# Function to check if iSerialNumber in array of ExternalDevice objects
def snInDevArray(ksn, kdevarr):
	for khyd in kdevarr:
		if ksn == khyd.iSerialNumber:
			return True
	return False
	
# Function to check for dirty Registry Hive
def is_dirty(khv):	
	if khv.header.primary_sequence_num != khv.header.secondary_sequence_num:
		print(khv.name.split('\\')[-1] + " is dirty! Sequence numbers don't match; applying transaction logs...")
		return True
		
	chksum = calculate_xor32_checksum(khv._stream.read(508))
	if khv.header.checksum != chksum:
		print(khv.name.split('\\')[-1] + " is dirty! Checksum doesn't match; applying transaction logs...")
		return True
	
	print(khv.name.split('\\')[-1] + " is clean")
	return False

# Function to replay transaction logs
# Uses regipy apply_transaction_logs(hive_path, primary_log_path, secondary_log_path=None, restored_hive_path=None, verbose=False)
def replay_logs(khvpath):
	#Looking for log files in same path as hive
	print("Looking for LOG files: "+khvpath+".LOG1 & "+khvpath+".LOG2 in same location as "+khvpath)
	log1=log2=""
	logsexist=False
	if os.path.exists(khvpath+".LOG1"):
		log1=khvpath+".LOG1"
		logsexist=True
	if os.path.exists(khvpath+".LOG2"):
		log2=khvpath+".LOG2"
		logsexist=True
	
	if logsexist:
		updatedhive=None
		updatedhive, dirtypagecount = apply_transaction_logs(khvpath, log1, log2, updatedhive, False)
		print("Updated hive created: "+updatedhive)
		return RegistryHive(updatedhive)
	else:
		print("Log files not found - dirty hive is being processed")
		return RegistryHive(khvpath)

# Function to change permissions on a folder to allow Registry hives to be accessed
def pychmod(kpath):
	try:
		if os.path.exists(kpath):
			os.chmod(kpath, 0o777)
			print("Permissions modified successfully on path: "+kpath)
		else:
			print("Path not found:", kpath)
	except PermissionError:
		print("Error: Permissions could not be changed on the folder:", kpath)
		print("**Please check you are running your Terminal as an Administrator**")
		print()
		sys.exit()

# Function to check python is running in an admin terminal
def isAdmin():
	try:
		if 'wsl' in platform.platform().lower():
			# Cannot determine if running as admin, so default to True
			return True
		elif platform.platform().lower().startswith('linux'):
			return os.getuid() == 0
		elif platform.platform().lower().startswith('windows'):
			return ctypes.windll.shell32.IsUserAnAdmin() != 0
	# Default to False
	finally:
		return False

# Function to get filesystem type from hex VBR
def getFSFromVbr(khexvbr):
	fstype=hexToText(khexvbr[6:21])
	if fstype.startswith("EXFAT"):
		return "ExFAT"
	elif fstype.startswith("NTFS"):
		return "NTFS"

	fstype=hexToText(khexvbr[164:180])
	if fstype.startswith("FAT"):
		return fstype.strip()

	return ""

# Function to get VSN from VBR depending on filesystem type offset
def getVsnFromVbr(khexvbr):
	kfstype=getFSFromVbr(khexvbr)
	vbrvsnoffset=0
	vbrvsnsize=4
	#Getting VSN offset & size (where not 4)
	if kfstype.startswith("ExFAT"):
		vbrvsnoffset=100
	elif kfstype.startswith("NTFS"):
		vbrvsnoffset=72
		vbrvsnsize=8
	elif kfstype.startswith("FAT"):
		vbrvsnoffset=67
	
	if vbrvsnoffset > 0:
		khyvsn=khexvbr[(vbrvsnoffset*2):((vbrvsnoffset+vbrvsnsize)*2)]
		return(flipEndianness(khyvsn)+" (" +kfstype+")")
	else:
		return ""

# Function to change endianness of a hex string
def flipEndianness(khexstr):
	outstr=""
	try:
		for i in range(len(khexstr),0,-2):
			outstr=outstr+khexstr[i-2:i]
	finally:
		return outstr

# Function to convert hex string to ascii text
def hexToText(khyhexstr):
	outstr=""
	for i in range(0,len(khyhexstr),2):
		outstr=outstr+chr(int(khyhexstr[i : i + 2], 16))
	return outstr

# Function to strip out prepended data from S/N if UASP device
def stripUaspMarker(ksn):
	umarker="MSFT30"
	if ksn.startswith(umarker):
		return ksn[len(umarker):]
	else:
		return ksn
	

### MAIN function ###
print("Registry parser, to extract USB connection artifacts from SYSTEM, SOFTWARE, and NTUSER.dat hives")
print("Author: Kathryn Hedley, khedley@khyrenz.com")
print("Copyright 2024 Kathryn Hedley, Khyrenz Ltd")

# Check & parse passed-in arguments
next=""
sysHive=""
swHive=""
userHives=[]
kmtvol=""
ntuflag=False
swflag=False
csvout=False
kvout=True
for karg in sys.argv:
	if next == 'system':
		sysHive=karg
		next=""
	if next == 'software':
		swHive=karg
		next=""
	if next == 'ntuser':
		userHives.append(karg)
		next=""
	if next == 'output':
		if karg == "csv":
			csvout=True
			kvout=False
	if next == 'volume':
		kmtvol=karg
		next=""
	if karg == "-h":
		printHelp()
		sys.exit()
	if karg == "-s":
		next='system'
	if karg == "-w":
		next='software'
	if karg == "-u":
		next='ntuser'
	if karg == "-o":
		next='output'
	if karg == "-v":
		next='volume'

#if volume option is provided, find Registry hives
if kmtvol:
	if not kmtvol.endswith("/"):
		kmtvol = kmtvol + "/"

	sysconfdir=kmtvol+"Windows/System32/config"
	#Changing Windows permissions to allow access to each system hive
	pychmod(sysconfdir)
	
	sysHive=sysconfdir+"/SYSTEM"
	swHive=sysconfdir+"/SOFTWARE"
	userHives=[]
	
	if os.path.exists(kmtvol+"Users"):
		userfolders = [f.path for f in os.scandir(kmtvol+"Users") if f.is_dir()]
		for usrdir in userfolders:
			#Changing Windows permissions to allow access to each NTUSER hive
			pychmod(usrdir)
			#Store paths to NTUSER hives
			userHives.append(usrdir+"/NTUSER.DAT")

#Event log to parse to get USB connections
usbEvtx=kmtvol+"Windows/System32/winevt/Logs/Microsoft-Windows-Partition%4Diagnostic.evtx"
usbEvtId='1006'

# Checking hives exist & opening to extract keys & values
if os.path.isfile(sysHive):
	SYSTEM = RegistryHive(sysHive)
	#Checking if hive is dirty
	if is_dirty(SYSTEM):
		SYSTEM = replay_logs(sysHive)
else:
	print("SYSTEM Hive '"+sysHive+" ' does not exist")
	print()
	printHelp()
	sys.exit()
if os.path.isfile(swHive):
	SOFTWARE = RegistryHive(swHive)
	swflag=True
	#Checking if hive is dirty
	if is_dirty(SOFTWARE):
		SOFTWARE = replay_logs(swHive)
else:
	print("SOFTWARE Hive not being parsed")
NTUSER=[]
if not userHives:
	print("User hives not being parsed")
for kuh in userHives:
	if os.path.isfile(kuh) and not "Default" in kuh:
		nthv=RegistryHive(kuh)
		#Checking if hive is dirty
		if is_dirty(nthv):
			nthv = replay_logs(kuh)
		#Appending hive to list
		NTUSER.append(nthv)
		ntuflag=True
		#Checking if hive is dirty

#initialising empty array to store device values & removing empty value that's added
devices = []

# Getting currentcontrolset value
currentVal = SYSTEM.get_key('SYSTEM\\Select').get_value('Current')
khycurrentcontrolset = 'ControlSet00' + str(currentVal)
print("currentcontrolset identified as " + khycurrentcontrolset)

# Iterating over SYSTEM\currentcontrolset\Enum\USBSTOR key...
for kusbstorkey in SYSTEM.get_key("SYSTEM\\" + khycurrentcontrolset + "\\Enum\\USBSTOR").iter_subkeys():
	for kusbstorsnkey in SYSTEM.get_key("SYSTEM\\" + khycurrentcontrolset + "\\Enum\\USBSTOR\\" + kusbstorkey.name).iter_subkeys():	
		newDev=ExternalDevice()
		#Get device friendly name
		newDev.name = kusbstorsnkey.get_value('FriendlyName')
		
		#Get device serial number, removing all after the last '&' character, including the '&' itself
		amp = kusbstorsnkey.name.find('&', 2)
		remove = len(kusbstorsnkey.name)-amp
		
		if amp > 0:
			newDev.iSerialNumber = kusbstorsnkey.name[:-remove]
		else:
			newDev.iSerialNumber = kusbstorsnkey.name
		
		#Get device timestamps (if present)
		newDev.firstConnected = getTime(SYSTEM, "SYSTEM\\" + khycurrentcontrolset + "\\Enum\\USBSTOR\\" + kusbstorkey.name + "\\" + kusbstorsnkey.name + "\\Properties\\{83da6326-97a6-4088-9453-a1923f573b29}\\0064")
		newDev.lastConnected = getTime(SYSTEM, "SYSTEM\\" + khycurrentcontrolset + "\\Enum\\USBSTOR\\" + kusbstorkey.name + "\\" + kusbstorsnkey.name + "\\Properties\\{83da6326-97a6-4088-9453-a1923f573b29}\\0066")
		newDev.lastRemoved = getTime(SYSTEM, "SYSTEM\\" + khycurrentcontrolset + "\\Enum\\USBSTOR\\" + kusbstorkey.name + "\\" + kusbstorsnkey.name + "\\Properties\\{83da6326-97a6-4088-9453-a1923f573b29}\\0067")
		
		#Adding device to array if serial number not blank
		if newDev.iSerialNumber:
			devices.append(newDev)
		
# Iterating over SYSTEM\currentcontrolset\Enum\USB key looking for SCSI devices...
for kusbkey in SYSTEM.get_key("SYSTEM\\" + khycurrentcontrolset + "\\Enum\\USB").iter_subkeys():
	for kusbsubkey in SYSTEM.get_key("SYSTEM\\" + khycurrentcontrolset + "\\Enum\\USB\\" + kusbkey.name).iter_subkeys():
		if kusbsubkey.name.startswith('MSFT30'):
			#SCSI device!
			khyzDev=ExternalDevice()
			#Set iSerialNumber
			khyzDev.iSerialNumber = kusbsubkey.name[6:]
			
			#Get ParentIdPrefix to map to SCSI key
			kdevParentId = kusbsubkey.get_value('ParentIdPrefix')
			
			# Iterating over SYSTEM\currentcontrolset\Enum\SCSI key...
			for kscsikey in SYSTEM.get_key("SYSTEM\\" + khycurrentcontrolset + "\\Enum\\SCSI").iter_subkeys():
				for kscsisubkey in SYSTEM.get_key("SYSTEM\\" + khycurrentcontrolset + "\\Enum\\SCSI\\" + kscsikey.name).iter_subkeys():
					#Only adding if has Parent ID - e.g. vmware devices can be added here without a Parent ID - can't link to SCSI key
					if kdevParentId is not None and kscsisubkey.name.startswith(kdevParentId):
						#Get device friendly name
						khyzDev.name = kscsisubkey.get_value('FriendlyName')
						
						#Get Disk ID to map to Volume name
						khyzDev.setDiskId(SYSTEM.get_key("SYSTEM\\" + khycurrentcontrolset + "\\Enum\\SCSI\\" + kscsikey.name + "\\" + kscsisubkey.name + "\\Device Parameters\\Partmgr").get_value('DiskId'))
						
						#Get device timestamps (if present)
						khyzDev.firstConnected = getTime(SYSTEM, "SYSTEM\\" + khycurrentcontrolset + "\\Enum\\SCSI\\" + kscsikey.name + "\\" + kscsisubkey.name + "\\Properties\\{83da6326-97a6-4088-9453-a1923f573b29}\\0064")
						khyzDev.lastConnected = getTime(SYSTEM, "SYSTEM\\" + khycurrentcontrolset + "\\Enum\\SCSI\\" + kscsikey.name + "\\" + kscsisubkey.name + "\\Properties\\{83da6326-97a6-4088-9453-a1923f573b29}\\0066")
						khyzDev.lastRemoved = getTime(SYSTEM, "SYSTEM\\" + khycurrentcontrolset + "\\Enum\\SCSI\\" + kscsikey.name + "\\" + kscsisubkey.name + "\\Properties\\{83da6326-97a6-4088-9453-a1923f573b29}\\0067")
						
			#Adding device to array if serial number is not blank & not already in array
			if khyzDev.iSerialNumber and not snInDevArray(khyzDev.iSerialNumber, devices):
				devices.append(khyzDev)

# Iterating over SYSTEM\MountedDevices key to determine last mounted drive letters...
for kmdval in SYSTEM.get_key("SYSTEM\MountedDevices").get_values():
	if kmdval.name.startswith('\DosDevices\\'):		
		try:
			khexmd=hexlify(kmdval.value)
			for d in devices:
				khexsn=bytes(d.iSerialNumber.encode('utf-16le').hex(), 'utf8')
				if khexsn in khexmd: 
					#Last drive letter found - add to devices info
					d.setLastDriveLetter(kmdval.name[-2:]+'\\')
		except:
			#empty value
			continue
	
	#Extracting disk GUID values to search NTUSER hive, only if NTUSER.dat hive provided & valid
	if ntuflag:
		if kmdval.name.startswith('\??\Volume{'):
			try:
				khexmd=hexlify(kmdval.value)
				for d in devices:
					khexsn=bytes(d.iSerialNumber.encode('utf-16le').hex(), 'utf8')
					if khexsn in khexmd: 
						#Disk GUID found - compare against NTUSER hive
						diskGuid=kmdval.name[-38:]
						
						#Iterating NTUSER.DAT hives
						for NTU in NTUSER:
							#Getting user account name from NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders\Desktop
							kusername=NTU.get_key('NTUSER.DAT\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders').get_value('Desktop')
							
							#Output is of format C:\Users\<user>\Desktop -> extracting username
							kusername=kusername.split('\\')[2]
							
							#Checking NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2 for disk GUID
							for khymp in NTU.get_key('NTUSER.DAT\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\MountPoints2').iter_subkeys():
								if khymp.name == diskGuid:
									d.addUser(kusername)
									break
			except:
				#empty value
				continue

# Iterating over SOFTWARE\Microsoft\Windows Portable Devices\Devices to determine volume name or last drive letter...
for kwpdkey in SOFTWARE.get_key("SOFTWARE\\Microsoft\\Windows Portable Devices\\Devices").iter_subkeys():
	for kdev in devices:
		if kdev.iSerialNumber.lower() in kwpdkey.name.lower(): 
			#Match to USB device in array
			volName = kwpdkey.get_value('FriendlyName')
			if ":\\" in volName:
				#Drive letter, not volume name - add to devices info if not already added
				if kdev.lastDriveLetter == "":
					kdev.setLastDriveLetter(volName)
			else: #Volume name
				kdev.setVolumeName(volName)
		elif kdev.getDiskId().lower() and kdev.getDiskId().lower() in kwpdkey.name.lower():
			#Match to USB device on Disk ID (SCSI)
			volName = kwpdkey.get_value('FriendlyName')
			if ":\\" in volName:
				#Drive letter, not volume name - add to devices info if not already added
				if kdev.lastDriveLetter == "":
					kdev.setLastDriveLetter(volName)
			else: #Volume name
				kdev.setVolumeName(volName)

# Iterating over SOFTWARE\Microsoft\Windows Search\VolumeInfoCache to try & match up drive letter with known volume name...
for kvickey in SOFTWARE.get_key("SOFTWARE\\Microsoft\\Windows Search\\VolumeInfoCache").iter_subkeys():
	#Get Drive Letter & Volume name for device
	kdletter = kvickey.name + '\\'
	kvname = kvickey.get_value('VolumeLabel')
	#Getting another potential connection time for device
	klwtime = convertWin64time(kvickey.header.last_modified)
	
	#Attempt to link on volume name to assign drive letter & other connection time
	for kdv in devices:
		if kdv.volumeName == kvname:
			if kdv.lastDriveLetter == "":
				kdv.setLastDriveLetter(kdletter)
			
			#Only adding other connection time to list if not already present
			exists=False
			for c in d.getOtherConnections():
				if c == klwtime:
					exists=True
			if not exists:
				d.addOtherConnection(klwtime)
				break

# Parsing event log
print("Opening: ", usbEvtx)
with evtx.Evtx(usbEvtx) as evtxlog:
	for evtxrecord in evtxlog.records():
		#print(evtxrecord.xml())
		root = minidom.parseString(evtxrecord.xml())
		eId=""
		eTime=""
		parent=""
		sn=""
		make=""
		model=""
		vsn=""

		#Getting Event ID & time	
		sysinfo = root.getElementsByTagName('System')[0]
		eId = sysinfo.getElementsByTagName('EventID')[0].firstChild.nodeValue
		
		if eId == usbEvtId:
			eTime = sysinfo.getElementsByTagName('TimeCreated')[0].attributes['SystemTime'].value
			
			elements = root.getElementsByTagName('Data')
			for element in elements:
				if element.attributes['Name'].value == "ParentId":
					try:
						parent = element.firstChild.nodeValue
						#get Serial number in ParentId - everything after last '\'
						parent_sn = stripUaspMarker(element.firstChild.nodeValue[element.firstChild.nodeValue.rindex('\\')+1:])
					except:
						pass
				if element.attributes['Name'].value == "SerialNumber":
					try:
						sn = stripUaspMarker(element.firstChild.nodeValue)
					except:
						pass
				if element.attributes['Name'].value == "Manufacturer":
					try:
						make = element.firstChild.nodeValue
					except:
						pass
				if element.attributes['Name'].value == "Model":
					try:
						model = element.firstChild.nodeValue
					except:
						pass
				if element.attributes['Name'].value == "Vbr0":
					try:
						hexvbr = base64.b64decode(element.firstChild.nodeValue).hex()
						vsn=getVsnFromVbr(hexvbr)
					except:
						pass
			if parent.startswith("USB\\"):
				#Matching this event info with Registry info for this device
				for d in devices:
					if (sn == d.iSerialNumber) or (parent_sn == d.iSerialNumber):
						#Adding info to device record - if not already present
						exists=False
						isoETime=datetime.strptime(eTime,'%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc).isoformat()
						for c in d.getOtherConnections():
							if c == isoETime:
								exists=True
								break
						if not exists:
							d.addOtherConnection(isoETime)
						
						exists=False
						for c in d.getVsns():
							if c == vsn:
								exists=True
								break
						if (not exists) and not (vsn == "None") and not (vsn == ""):
							d.addVsn(vsn)
							
						#Checking for other info gaps from the Registry
						if d.name == "":
							d.name = make + " " + model

#Print output in CSV or key-value pair format
print()
if csvout:
	outputCSV(devices)
if kvout:
	outputKV(devices)
