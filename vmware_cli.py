#!/usr/bin/env jython

import getpass, sys, socket, os, math
from xmlrpclib import ServerProxy
from java.net import URL
from java.util import Calendar
from java.text import DateFormat
from optparse import OptionParser, OptionGroup, SUPPRESS_HELP
from com.vmware.vim25 import VirtualMachineCapability
from com.vmware.vim25 import VirtualMachineConfigInfo
from com.vmware.vim25 import VirtualMachineConfigSpec
from com.vmware.vim25 import VirtualMachineFileInfo
from com.vmware.vim25 import VirtualDeviceConfigSpec
from com.vmware.vim25 import VirtualDeviceConfigSpecOperation
from com.vmware.vim25 import VirtualDeviceConfigSpecFileOperation
from com.vmware.vim25 import VirtualLsiLogicSASController
from com.vmware.vim25 import VirtualLsiLogicController
from com.vmware.vim25 import ParaVirtualSCSIController
from com.vmware.vim25 import VirtualBusLogicController
from com.vmware.vim25 import VirtualSCSISharing
from com.vmware.vim25 import VirtualDisk
from com.vmware.vim25 import VirtualDiskFlatVer2BackingInfo
from com.vmware.vim25 import VirtualE1000
from com.vmware.vim25 import VirtualVmxnet2
from com.vmware.vim25 import VirtualVmxnet3
from com.vmware.vim25 import VirtualEthernetCardNetworkBackingInfo
from com.vmware.vim25 import AutoStartDefaults
from com.vmware.vim25 import HostAutoStartManagerConfig
from com.vmware.vim25 import Description
from com.vmware.vim25 import OptionValue
from com.vmware.vim25 import InvalidDatastore
from com.vmware.vim25 import InvalidArgument
from com.vmware.vim25 import LicenseManagerLicenseInfo
from com.vmware.vim25.mo import LicenseManager
from com.vmware.vim25.mo import Folder
from com.vmware.vim25.mo import InventoryNavigator
from com.vmware.vim25.mo import ManagedEntity
from com.vmware.vim25.mo import ServiceInstance
from com.vmware.vim25.mo import VirtualMachine
from com.vmware.vim25.mo import HostSystem
from com.vmware.vim25.mo import HostAutoStartManager
from com.vmware.vim25.mo import Datacenter
from com.vmware.vim25.mo import ResourcePool
from com.vmware.vim25.mo.util import MorUtil

def getServiceInstance(svr,user,passwd,skipSSL):
    """ 
    Connect to ESX and return service instance
    """
    url = URL("https://%s/sdk" % svr)
    si = ServiceInstance(url,user,passwd,skipSSL)
    return si

def getExpirationDate(license_props):
    """
    Iterates through a property list and returns the expirationDate
    """
    if license_props:
        df = DateFormat.getInstance()
        for p in license_props:
            if p.getKey() == "expirationDate":
                val = p.getValue()
                if val.getClass().getName() == "java.util.GregorianCalendar":
                    return df.format(val.getTime())
    return None

def getLicenseManager(si):
    """
    Get an LM object from the service instance   
    """
    lm = si.getLicenseManager()
    if not lm: return None
    return lm

def dumpPropertyList(pList):
    """
    Iterates through a property list and prints the key/value pairs
    Primarily for debugging
    """
    FORMAT = "%16s %s"
    for p in pList:
        k = p.getKey()
        if p.getValue().__class__ is unicode or \
                p.getValue().__class__ is long:
            v = p.getValue()

        elif p.getValue().getClass().getName() == "com.vmware.vim25.KeyValue":
            v = p.getValue().getValue()
        elif p.getValue().getClass().getName() == "java.util.GregorianCalendar":
            df = DateFormat.getInstance()
            v = df.format(p.getValue().getTime())
        else:
            v = "Val: UNABLE TO PRINT; " + p.getValue().getClass().getName()

        print FORMAT % (k.capitalize()+":", v)
        

def printLicenseDetails(licenseProp):
    """
    Given a service instance print as
    many properties as possible
    """

    # For now we just do a dump of all the properties
    dumpPropertyList(licenseProp)

def decodeLicenseString(si, licStr):
    FORMAT = "%16s %s"
    lm = getLicenseManager(si)
    if type(licStr) is str and lm:
        ## Decode the license string passed to us
        licInfo = lm.decodeLicense(licStr)
        prop = licInfo.getProperties()
        print FORMAT % ("Cost Unit: ", licInfo.getCostUnit())
        print FORMAT % ("Name: ", licInfo.getName())
        dumpPropertyList(prop)
 
def addLicense(si, licStr):
    lm = getLicenseManager(si)
    if type(licStr) is str and lm:
        ## Decode the license string passed to us
        lm.addLicense(licStr, None)


def rmLicense(si, licStr):
    lm = getLicenseManager(si)
    if type(licStr) is str and lm:
        ## Decode the license string passed to us
        lm.removeLicense(licStr)

def getLicenses(si):
    """
    Return a list of licenses from the current service instance
    """
    lm = getLicenseManager(si)
    licList = lm.getLicenses()
    return licList

def listLicenses(si):
    props = None
    FORMAT = "%16s %s"
    for l in getLicenses(si):
        print FORMAT % ("Type: ", l.getEditionKey().capitalize())
        if "eval" == l.getEditionKey():
            lm = getLicenseManager(si)
            props = lm.getEvaluation().getProperties()
            expires = getExpirationDate(props)
        else:
            props = l.getProperties()
            expires =  getExpirationDate(props)
        print FORMAT % ("Expires: ", expires)
        printLicenseDetails(props)

def printHostHardwareSummary(si):
    host = InventoryNavigator(si.getRootFolder()).searchManagedEntities("HostSystem")
    df = DateFormat.getInstance()
    for h in host:
        hinfo = h.getHardware()
        print "Hypervisor Name: " + h.getName()
        print hinfo.getSystemInfo().getVendor(),
        print hinfo.getSystemInfo().getModel()
        print "Bios: ", hinfo.getBiosInfo().getBiosVersion(),
        print df.format(hinfo.getBiosInfo().getReleaseDate().getTime())
        print "Overall Status: ", 
        print h.getOverallStatus().toString().capitalize()
        print "CPU Info: ", hinfo.getCpuPkg()[0].getDescription()
        print "\tCPU's: ", hinfo.getCpuInfo().getNumCpuPackages()
        print "\tCores: ", hinfo.getCpuInfo().getNumCpuCores()
        print "Memory Info: %.2f GB" % (hinfo.getMemorySize() * pow(10.0, -9))

def getDatacenters(si):
    """
    Return a list of datacenter managed objects
    """
    dcList = InventoryNavigator(si.getRootFolder()).searchManagedEntities("Datacenter")
    return dcList

def getHostSystems(si):
    """
    Return a list of all host systems in the inventory
    """
    hsList = InventoryNavigator(si.getRootFolder()).searchManagedEntities("HostSystem")
    return hsList

def getResourcePools(si):
    """
    Return a list of resource pool managed objects
    """
    rpList = InventoryNavigator(si.getRootFolder()).searchManagedEntities("ResourcePool")
    return rpList

def getVirtualMachines(si):
    """
    Return a list of all virtual machines in the inventory
    """
    vmList = InventoryNavigator(si.getRootFolder()).searchManagedEntities("VirtualMachine")
    return vmList

def getVirtualMachineByName(si,vmname):
    """
    Return virtual machine with a given name
    """
    vmList = []
    for vm in getVirtualMachines(si):
        if vmname == vm.getName():
            vmList.append(vm)

    if len(vmList) > 1:
        print "Multiple virtual machines named %s.  Please lookup by UUID." % vmname
        return None
    else:
        return vmList[0]

def getVirtualMachineByUUID(si,vmuuid):
    """
    Return virtual machine with a given uuid
    """
    for vm in getVirtualMachines(si):
        if vmuuid == vm.getConfig().uuid:
            return vm
    return None

def getPortgroups(hss):
    """
    Return each portgroup configuration
    """
    pgList = []
    for pg in hss.hostNetworkSystem.getNetworkConfig().getPortgroup():
        pgList.append([pg.getSpec().vswitchName,pg.getSpec().name,pg.getSpec().vlanId])
    return pgList

def listPortgroups(hss):
    """
    Print each portgroup and associated virtual switch and vlan info
    """
    FORMAT = '%-15s %-20s %-10s'
    print FORMAT % ('Virtual Switch', 'Portgroup', 'VLan ID')
    print FORMAT % ('=' * 15, '=' * 9, '=' * 7)
    pgs = getPortgroups(hss)
    for pg in pgs:
        print FORMAT % (pg[0], pg[1], pg[2])

def listVirtualMachines(vms):
    """
    Print each virtual machine's configuration
    """
    FORMAT = '%-22s %-36s %-38s %-3s %-10s %-20s %-4s'
    print FORMAT % ('VM Name', 'UUID', 'OS Full Name', 'CPU', 'MEM', 'Annotation', 'Power')
    print FORMAT % ('=' * 22, '=' * 36, '=' * 38, '=' * 3, '=' * 10, '=' * 20, '=' * 4) 

    if isinstance(vms, VirtualMachine):
        if "PowerOnVM_Task" in vms.getDisabledMethod():
            state = "ON"
        else:
            state = "OFF"
        print FORMAT % (vms.getName(),vms.getConfig().uuid,vms.getConfig().getGuestFullName(),
                        vms.getConfig().hardware.numCPU,vms.getConfig().hardware.memoryMB,
                        vms.getConfig().annotation,state)
    else:
        for vm in vms:
            if "PowerOnVM_Task" in vm.getDisabledMethod():
                state = "ON"
            else:
                state = "OFF"
            print FORMAT % (vm.getName(),vm.getConfig().uuid,vm.getConfig().getGuestFullName(),
                            vm.getConfig().hardware.numCPU,vm.getConfig().hardware.memoryMB,
                            vm.getConfig().annotation,state)

def listHostSystems(si,hss):
    """
    Print each esx(i) instance's configuration
    """   
    FORMAT = '%-22s %-9s %-10s %-9s %-10s %-18s'
    print FORMAT % ('ESX Name','AutoStart','StartDelay','StopDelay','StopAction','Wait For Heartbeat')
    print FORMAT % ('=' * 22, '=' * 9, '=' * 10, '=' * 9, '=' * 10, '=' * 18)

    if isinstance(hss, HostSystem):
        enabled,startDelay,stopDelay,stopAction,waitForHeartbeat = getHostAutoStartOptionDefaults(hss)
        if enabled:
            autostatus = "ON"
        else:
            autostatus = "OFF"
        if waitForHeartbeat:
            hbstatus = "ON"
        else:
            hbstatus = "OFF"
        print FORMAT % (hss.getName(),autostatus,startDelay,stopDelay,stopAction,hbstatus)
        print
        listHostVmAutoStartOption(si,hss)
        listPortgroups(hss)
    else:
        for hs in hss:
            enabled,startDelay,stopDelay,stopAction,waitForHeartbeat = getHostAutoStartOptionDefaults(hs)
            if enabled:
                autostatus = "ON"
            else:
                autostatus = "OFF"
            if waitForHeartbeat:
                hbstatus = "ON"
            else:
                hbstatus = "OFF"
            print FORMAT % (hs.getName(),autostatus,startDelay,stopDelay,stopAction,hbstatus)
            print
            listHostVmAutoStartOption(si,hs)
            listPortgroups(hs)

def listDatacenters(dcs):
    """
    Print each virtual datacenter's configuration
    """
    FORMAT = '%-22s'
    print FORMAT % ('Datacenter')
    print FORMAT % ('=' * 22) 

    if isinstance(dcs, Datacenter):
        print dcs.getName()
    else:
        for dc in dcs:
            print dc.getName()

def listResourcePools(rps):
    """
    Print each resource pool's configuration
    """
    FORMAT = '%-22s'
    print FORMAT % ('Resource Pool')
    print FORMAT % ('=' * 22)

    if isinstance(rps, ResourcePool):
        print rps.getName()
    else:
        for rp in rps:
            print rp.getName()

def deleteVm(vm):
    """
    Delete given virtual machine
    """
    vmname = vm.getName()
    if "PowerOnVM_Task" in vm.getDisabledMethod():
        powerOffVm(vm)
        
    task = vm.destroy_Task()
    if task.waitForMe() == "success":
        print "%s has been deleted" % (vmname)
    else:
        print "%s could not be deleted" % (vmname)

def powerOnVm(vm):
    """ 
    Power on virtual machine
    """
    if "PowerOnVM_Task" in vm.getDisabledMethod():
        print "%s is already powered ON" % vm.getName()
    else:
        task = vm.powerOnVM_Task(None)
        if task.waitForMe() == "success":
            print "%s is being powered ON" % vm.getName()
        else:
            print "%s could not be powered ON" % vm.getName()

def powerOffVm(vm):
    """
    Power off virtual machine
    """
    if "PowerOffVM_Task" in vm.getDisabledMethod():
        print "%s is already powered OFF" % vm.getName()
    else:
        task = vm.powerOffVM_Task()
        if task.waitForMe() == "success":
            print "%s is being powered OFF" % vm.getName()
        else:
            print "%s could not be powered OFF" % vm.getName()

def resetVm(vm):
    """
    Reset virtual machine power
    """
    if "ResetVM_Task" in vm.getDisabledMethod():
        print "%s can not be reset" % vm.getName()
    else:
        task = vm.resetVM_Task()
        if task.waitForMe() == "success":
            print "%s is being reset" % vm.getName()
        else:
            print "%s could not be reset" % vm.getName()

def powerOnAllVms(vms):
    """
    Power on all virtual machines in a given sequence
    """
    for vm in vms:
        powerOnVm(vm)

def powerOffAllVms(vms):
    """
    Power off all virtual machines in a given sequence
    """
    for vm in vms:
        powerOffVm(vm)

def resetAllVms(vms):
    """
    Reset virtual machine power and return success
    """
    for vm in vms:
        resetVm(vm)

def getHostAutoStartOptionDefaults(host):
    """
    Return autostart configuration for a host
    """
    enabled = host.getHostAutoStartManager().config.defaults.getEnabled()
    startDelay = host.getHostAutoStartManager().config.defaults.getStartDelay()
    stopDelay = host.getHostAutoStartManager().config.defaults.getStopDelay()
    stopAction = host.getHostAutoStartManager().config.defaults.getStopAction()
    waitForHeartbeat = host.getHostAutoStartManager().config.defaults.getWaitForHeartbeat()
    return ([enabled,startDelay,stopDelay,stopAction,waitForHeartbeat])

def setHostAutoStartOptionDefaults(host,isEnabled,startDelay,stopDelay,stopAction,waitForHeartbeat):
    """
    Configure the automatic start/stop of virtual machines on a host
    """
    asd = AutoStartDefaults()
    asd.setEnabled(isEnabled)
    asd.setWaitForHeartbeat(waitForHeartbeat)
    if isEnabled and startDelay:
        # Defaults to 120 Seconds
        asd.setStartDelay(int(startDelay))
    if isEnabled and stopDelay:
        # Defaults to 120 Seconds
        asd.setStopDelay(int(stopDelay))
    if isEnabled and stopAction:
        asd.setStopAction(stopAction)
    asSpec = HostAutoStartManagerConfig()
    asSpec.setDefaults(asd)
    hasm = host.getHostAutoStartManager()
    hasm.reconfigureAutostart(asSpec)

def listHostVmAutoStartOption(si,host):
    """
    Return autostart configuration for a virutal machine
    """
    if host.getHostAutoStartManager().config.powerInfo:
        FORMAT = '%-22s %-11s %-11s %-11s %-13s %-11s %-11s'
        print FORMAT % ('VM Name','StartAction','StartDelay','StartOrder','StopAction','StopDelay','WaitForHeartBeat')
        print FORMAT % ('=' * 22, '=' * 11, '=' * 11, '=' * 11, '=' * 13, '=' * 11,'=' * 11)
        config = []
        for mor in host.getHostAutoStartManager().config.powerInfo:
            vm = MorUtil.createExactManagedObject(si.getServerConnection(),mor.getKey())
            print FORMAT % (vm.name,mor.startAction,mor.startDelay,mor.startOrder,mor.stopAction,mor.stopDelay,mor.waitForHeartbeat)

def setHostVmAutoStartOption(vm):
    """ 
    Configure the automatic start/stop of a virtual machine
    """
    pass

def createScsiSpec(scsiKey,busNumber,scsiType):
    """
    Define a virtual scsi ctrl spec
    """
    scsiSpec = VirtualDeviceConfigSpec()
    scsiSpec.setOperation(VirtualDeviceConfigSpecOperation.add)
    if scsiType == "sas":
        scsiCtrl = VirtualLsiLogicSASController()
    elif scsiType == "parallel":
        scsiCtrl = VirtualLsiLogicController()
    elif scsiType == "buslogic":
        scsiCtrl = VirtualBusLogicController()
    elif scsiType == "paravirt":
        scsiCtrl = ParaVirtualSCSIController()
    scsiCtrl.setKey(scsiKey)
    scsiCtrl.setBusNumber(busNumber)
    scsiCtrl.setSharedBus(VirtualSCSISharing.noSharing)
    scsiSpec.setDevice(scsiCtrl)

    return scsiSpec

def createDiskSpec(scsiKey,diskKey,unitNumber,diskSize,diskMode,datastore):
    """
    Define a virtual disk spec
    """
    diskSpec = VirtualDeviceConfigSpec()
    diskSpec.setOperation(VirtualDeviceConfigSpecOperation.add)
    diskSpec.setFileOperation(VirtualDeviceConfigSpecFileOperation.create)
    vd = VirtualDisk()
    vd.setKey(diskKey)
    vd.setCapacityInKB(diskSize)
    vd.setUnitNumber(unitNumber)
    vd.setControllerKey(scsiKey)
    diskfileBacking = VirtualDiskFlatVer2BackingInfo()
    fileName = "["+datastore+"]"
    diskfileBacking.setFileName(fileName)
    diskfileBacking.setDiskMode(diskMode)
    diskfileBacking.setThinProvisioned(True)
    vd.setBacking(diskfileBacking)
    diskSpec.setDevice(vd)

    return diskSpec

def createNicSpec(nicKey,netName,macAddress,nicType):
    """
    Define a virtual nic spec
    """
    nicSpec = VirtualDeviceConfigSpec()
    nicSpec.setOperation(VirtualDeviceConfigSpecOperation.add)
    nicBacking = VirtualEthernetCardNetworkBackingInfo()
    # Assign Portgroup
    nicBacking.setDeviceName(netName)
    if nicType == "e1000":
        nic = VirtualE1000()
    elif nicType == "vmxnet2":
        nic = VirtualVmxnet2()
    elif nicType == "vmxnet3":
        nic = VirtualVmxnet3()
    nic.setKey(nicKey)
    nic.setBacking(nicBacking)
    # Address type is one of the following "generated", "manual", "assigned" by VC
    if macAddress:
        nic.setAddressType("manual")
        # MacAddress format is not validated here.
        nic.setMacAddress(macAddress)
    else:
        nic.setAddressType("generated")
    nicSpec.setDevice(nic)

    return nicSpec

def createVmSpec(name,cpucount,memorysize,guestos,annotation,datastore,configSpecs):
    """
    Create virtual machine from specs
    """
    # Create vm spec
    vmSpec = VirtualMachineConfigSpec()
    vmSpec.setName(name)
    vmSpec.setNumCPUs(cpucount)
    vmSpec.setMemoryMB(memorysize)
    vmSpec.setGuestId(guestos)
    vmSpec.setAnnotation(annotation)
    bootOrder = OptionValue()
    bootOrder.setKey("bios.bootDeviceClasses")
    bootOrder.setValue("allow:net,cd,hd")
    vmSpec.extraConfig = [bootOrder]
    vmSpec.setDeviceChange(configSpecs)

    # Create file info for the vmx file
    vmfi = VirtualMachineFileInfo()
    vmfi.setVmPathName("["+datastore+"]")
    vmSpec.setFiles(vmfi)

    return vmSpec

def ipAddressToVMwareMac(ipaddress):
    """
    Generate a mac address based on a given ip address.
    This takes the last 3 octets of an ip, turns them into hex,
    appends that to the vmware vm range 00:05:56, and returns it
    """
    p1,p2,p3,p4 = ipaddress.split('.')
    return "00:50:56:%x:%x:%x" % (int(p2),int(p3),int(p4))

def getCommandLineOpts():
    """
    Parses command line options

    @returns: 3-tuple of (parser, options, args)
    """
    parser = OptionParser(version="%prog 1.0", description='VMware Command Line Interface', prog='vmware-cli.py')

    # Virtual Machine Config Defaults
    parser.set_defaults(skipSSL=True)
    parser.set_defaults(autostart=True)
    parser.set_defaults(heartbeat=False)
    parser.set_defaults(scsiType='sas')
    parser.set_defaults(nicType='e1000')
    parser.set_defaults(cpucount=2)
    parser.set_defaults(memorysize=2048)
    parser.set_defaults(guestos='rhel5_64Guest')
    parser.set_defaults(annotation='')
    parser.set_defaults(datastore='datastore1')

    # Hypervisor Config Options

    # Required Options
    parser.add_option('-s', '--server',   dest='server',        action='store',       help='VMware hypervisor')
    parser.add_option('-u', '--username', dest='username',      action='store',       help='VMware hypervisor username')
    parser.add_option('-p', '--password', dest='password',      action='store',       help='VMware hypervisor password')

    # Managed Objects
    parser.add_option('-D',               dest='datacenter',    action='store_true',  help='Datacenter managed object')
    parser.add_option('-H',               dest='host',          action='store_true',  help='Host managed object')
    parser.add_option('-V',               dest='vm',            action='store_true',  help='Virtual machine managed object')
    parser.add_option('-R',               dest='resource',      action='store_true',  help='Resource Pool managed object')
    parser.add_option('-P',               dest='power',         action='store_true',  help='Power state')
    parser.add_option('-T',               dest='time',          action='store_true',  help='Time state')
    parser.add_option('-L',               dest='license',       action='store_true',  help='License state')

    # Actions
    parser.add_option('-q', '--query',    dest='query',         action='store_true',  help='Query')
    parser.add_option('-d', '--delete',   dest='delete',        action='store_true',  help='Delete')
    parser.add_option('-c', '--create',   dest='create',        action='store_true',  help='Create')
    parser.add_option('-m', '--modify',   dest='modify',        action='store_true',  help='Modify')
    parser.add_option('--prune',          dest='prune',         action='store_true',  help='Prune')

    # Filters
    parser.add_option('--all',            dest='all',           action='store_true',  help='Select all')
    parser.add_option('--name',           dest='name',          action='store',       help='Select by name')
    parser.add_option('--uuid',           dest='uuid',          action='store',       help='Select by uuid')
    
    # Power Settings
    parser.add_option('--on',             dest='on',            action='store_true',  help='Set Power On')
    parser.add_option('--off',            dest='off',           action='store_true',  help='Set Power Off')
    parser.add_option('--reset',          dest='reset',         action='store_true',  help='Set Power Reset')

    # Cobbler Options
    parser.add_option('--master',         dest='cblr_master',   action='store',       help='Cobbler master')
    parser.add_option('--genmac',         dest='genmac',        action='store_true',  help='Generate VMware MAC based on ip address')

    # Hypervisor Config Options
    parser.add_option('--auto-start',     dest='autostart',     action='store_true',  help='Enable Auto Start')
    parser.add_option('--no-auto-start',  dest='autostart',     action='store_false', help='Disable Auto Start')
    parser.add_option('--start-delay',    dest='start_delay',   action='store',       help='System default auto start in seconds')
    parser.add_option('--stop-delay',     dest='stop_delay',    action='store',       help='System default auto stop in seconds')
    parser.add_option('--stop-action',    dest='stop_action',   action='store',       help='System default power-off action')
    parser.add_option('--heartbeat',      dest='heartbeat',     action='store_true',  help='Enable swaitForHeartbeat setting')
    parser.add_option('--no-heartbeat',   dest='heartbeat',     action='store_false', help='Disable waitForHeartbeat setting')

    # Virtual Machine Config Options
    parser.add_option('--cpu-count',      dest='cpucount',      action='store',       help="Number of virtual CPU's (default: 2)", type="int")
    parser.add_option('--memory-size',    dest='memorysize',    action='store',       help='Amount of RAM in MB (default: 2048)',  type="int")
    parser.add_option('--guest-os',       dest='guestos',       action='store',       help='Guest OS short name rhel5_64Guest, freebsd64Guest, solaris10_64Guest (default: rhel5_64Guest)')
    parser.add_option('--scsi-type',      dest='scsiType',      action='store',       help='Chose one of the following scsi controller types (Default: sas, paravirt, buslogic, parallel)', choices=('sas','paravirt','buslogic','parallel'))
    parser.add_option('--nic-type',       dest='nicType',       action='store',       help='Chose one of the following nic types (Default: e1000, vmxnet2, vmxnet3)', choices=('e1000','vmxnet2','vmxnet3'))
    parser.add_option('--notes',          dest='annotation',    action='store',       help='Virtual Machine annotations (default: blank)')
    parser.add_option('--disk',           dest='disk',          action='append',      help='Virtual disk size in Gb.',                                   metavar="<size>", nargs=1)
    parser.add_option('--nic',            dest='nic',           action='append',      help='MAC address (manually assigned or blank for esx generated)', metavar="<port group>,<mac address>")
    parser.add_option('--datastore',      dest='datastore',     action='store',       help='Datastore name (default: Storage1)')

    options, args = parser.parse_args()
    
    return parser, options, args

def main():

    parser, options, args = getCommandLineOpts()

    # Check command line options
    if options.server is None:
        parser.error("You must provide a server")

    username = options.username or os.getenv('VMWARE_USERNAME')
   
    if username is None:
        parser.error("You must provide a username")

    password = options.password or os.getenv('VMWARE_PASSWORD')

    if password is None:
        password = getpass.getpass('Enter password for %s: ' % username)

    if (options.name and options.uuid):
        parser.error("A single filter must be specified at a time")
        
    if options.query and (options.delete or options.create or options.modify):
        parser.error("A single action must be specified at a time")
    if options.delete and (options.query or options.create or options.modify):
        parser.error("A single action must be specified at a time")
    if options.create and (options.query or options.delete or options.modify):
        parser.error("A single action must be specified at a time")
    if options.modify and (options.query or options.create or options.delete):
        parser.error("A single action must be specified at a time")
    
    # Get esx service instance
    si = getServiceInstance(options.server,username,password,options.skipSSL)

    # Query Datacenter
    if options.query and options.datacenter:
        dcs = getDatacenters(si)
        if dcs:
            listDatacenters(dcs)

    # Query Host Systems
    if options.query and options.host:
        hss = getHostSystems(si)
        if hss:
            listHostSystems(si,hss)

    # Modify Host Systems
    if options.modify and options.host:
        hss = getHostSystems(si)
        if (len(hss) > 1):
            for hs in hss:
                setHostAutoStartOptionDefaults(hs,options.autostart,options.start_delay,options.stop_delay,
                                               options.stop_action,options.heartbeat)
        else:
            setHostAutoStartOptionDefaults(hss[0],options.autostart,options.start_delay,options.stop_delay,
                                           options.stop_action,options.heartbeat)
                                   
    # Query Resource Pools
    if options.query and options.resource:
        rps = getResourcePools(si)
        if rps:
            listResourcePools(rps)

    if options.query and options.license:
        listLicenses(si)

    # Query Virtual Machine by name
    if options.query and options.name and options.vm:
        vm = getVirtualMachineByName(si,options.name)
        if vm:
            listVirtualMachines(vm)
    # Query Virtual Machine by uuid
    elif options.query and options.uuid and options.vm:
        vm = getVirtualMachineByUUID(si,options.uuid)
        if vm:
            listVirtualMachines(vm)
    # Query all Virtual Machines
    elif options.query and options.vm:
        vms = getVirtualMachines(si)
        if vms:
            listVirtualMachines(vms)

    # Modify Virtual Machine power state by name
    if options.name and options.power and options.modify:
        vm = getVirtualMachineByName(si,options.name)
        if vm and options.reset:
            resetVm(vm)
        elif vm and options.off:
            powerOffVm(vm)
        elif vm and options.on:
            powerOnVm(vm)
    # Modify Virtual Machine power state by uuid
    elif options.uuid and options.power and options.modify:
        vm = getVirtualMachineByUUID(si,options.uuid)
        if vm and options.reset:
            resetVm(vm)
        elif vm and options.off:
            powerOffVm(vm)
        elif vm and options.on:
            powerOnVm(vm)
    # Modify power state for all Virual Machines on a host
    elif options.all and options.power and options.modify:
        vms = getVirtualMachines(si)
        if vms and options.reset:
            resetAllVms(vms)
        elif vms and options.off:
            powerOffAllVms(vms)
        elif vms and options.on:
            powerOnAllVms(vms)

    # Delete VMs
    if options.name and options.delete and options.vm:
        vm = getVirtualMachineByName(si,options.name)
        if vm:
            deleteVm(vm)
    elif options.uuid and options.delete and options.vm:
        vm = getVirtualMachineByUUID(si,options.uuid)
        if vm:
            deleteVm(vm)

    # Create VMs
    if options.create and options.vm:
        resourcePool = getResourcePools(si)[0]
        datacenter = getDatacenters(si)[0]
        vmFolder = datacenter.getVmFolder()

        # Create virtual devices
        configSpecs = []
        scsiBusKey = 0
        scsiBusNum = 0      # Limited to 3 ScsiControllers (i think)
        diskKey = 0
        diskUnitNum = 0
        diskMode = "persistent" # Changes are immediately and permanently written to the virtual disk.
        nicKey = 0
        RESERVED_UNITNUM = 7
        SUPPORTED_HYPERVISORS = ['vmware']

        # If prune is selected delete the vm prior to creating it
        if options.create and options.vm and options.prune:
            try:
                vm = getVirtualMachineByName(si,options.name)
                deleteVm(vm)
            except IndexError:
                pass

        # Pull the Virtual hardware info from Cobbler
        if options.cblr_master:

            # Standard XML-RPC proxy
            conn = ServerProxy("http://%s/cobbler_api" % options.cblr_master)
            try:
                # Get the system from Cobbler
                server = conn.get_system_for_koan(options.name)
            except (socket.gaierror, ProtocolError), reason:
                print "Unable to connect to %s (%s) " % (options.cblr_master, reason)
                sys.exit(1)

            if not server:
                print "Unable to get system information for %s (exiting) " % (options.name)
                sys.exit(1)

            virt_type = server.get("virt_type")
            if virt_type not in SUPPORTED_HYPERVISORS:
                print "Unsupported virt type %s (exiting)" % virt_type
                sys.exit(1)

            virt_bridge = server.get("virt_bridge",None)
            virt_cpus = server.get("virt_cpus",None)
            virt_ram = server.get("virt_ram",None)
            virt_type = server.get("virt_type",None)
            comment = server.get("comment",None)

            virt_path = server.get("virt_path",None)
            virt_file_size = str(server.get("virt_file_size",None))

            if virt_file_size and virt_path:
                scsiSpec = createScsiSpec(scsiBusKey,scsiBusNum,options.scsiType)
                configSpecs.append(scsiSpec)

                for disk in virt_file_size.split(','):
                    # Convert gigabytes to kilobytes
                    size = (int(disk) * 1024 * 1024)
                    diskSpec = createDiskSpec(scsiBusKey,diskKey,diskUnitNum,size,diskMode,virt_path)
                    configSpecs.append(diskSpec)
                    diskKey = diskKey + 1
                    diskUnitNum = diskUnitNum + 1
                    # Skip the unit number assigned to the scsi controller (7)
                    if diskUnitNum == RESERVED_UNITNUM:
                        diskUnitNum = diskUnitNum + 1

            interfaces = server.get("interfaces", None)
            if interfaces:
                for k in sorted(interfaces.iterkeys()):
                    if k.find(":") == -1 and k.find(".") == -1:

                        # Generate VMware MAC based on IP
                        if (options.genmac and k == "eth1"):
                            interfaces[k]["mac_address"] = ipAddressToVMwareMac(interfaces[k]["ip_address"])

                        netName = interfaces[k]["virt_bridge"]
                        macAddress = interfaces[k]["mac_address"]
                        nicSpec = createNicSpec(nicKey,netName,macAddress,options.nicType)
                        configSpecs.append(nicSpec)
                        nicKey = nicKey + 1

            vmSpec = createVmSpec(options.name,virt_cpus,virt_ram,options.guestos,comment,virt_path,configSpecs)

        # Use Command line options for Virtual Hardware options
        else: 

            if options.disk:
                scsiSpec = createScsiSpec(scsiBusKey,scsiBusNum,options.scsiType)
                configSpecs.append(scsiSpec)

                # Limited to 15 virtual disks per ScsiController
                for disk in options.disk:
                    size = (int(disk) * 1024 * 1024)
                    diskSpec = createDiskSpec(scsiBusKey,diskKey,diskUnitNum,size,diskMode,options.datastore)
                    configSpecs.append(diskSpec)
                    diskKey = diskKey + 1
                    diskUnitNum = diskUnitNum + 1
                    # Skip the unit number assigned to the scsi controller (7)
                    if diskUnitNum == RESERVED_UNITNUM:
                        diskUnitNum = diskUnitNum + 1

            if options.nic:
                for nic in options.nic:
                    try:
                        netName, macAddress = nic.split(',',1)
                    except ValueError:
                        netName = nic
                        macAddress = None
                    nicSpec = createNicSpec(nicKey,netName,macAddress,options.nicType)
                    configSpecs.append(nicSpec)
                    nicKey = nicKey + 1

            vmSpec = createVmSpec(options.name,options.cpucount,options.memorysize,options.guestos,options.annotation,options.datastore,configSpecs)

        try:
            # Call the createVM_Task method on the vm folder
            task = vmFolder.createVM_Task(vmSpec, resourcePool, None)
        except InvalidDatastore, reason:
            print "Unable to create to vm %s (%s) " % (options.name, reason)
            sys.exit(1)

        try:
            if task.waitForMe() == "success":
                print "%s is being created" % options.name
            else:
                print "%s was not created" % options.name
        except (InvalidArgument, InvalidDatastore), reason:
            print "Unable to create to vm %s (%s) " % (options.name, reason)
            sys.exit(1)

            
    si.getServerConnection().logout()

if __name__ == "__main__":
    main()

