#!/usr/bin/env python
"""
 .SYNOPSIS
    MPP Migration Hardware Revision Discovery

    1. Gather CUCM version using UDS API, parse to major version
    2. Use major version to inform WSDL file for AXL
    3. Gather all SEP phones from CUCM using AXL listPhone API
    4. Filter results to 7821, 7861, and 7841 models that are hardware revision restricted from MPP migration
    5. Chunk into blocks of 900 for RISPort70 API query to avoid hitting the 1000 result max
    6. Process each chunk, gathering the registration status, load information, and first IPv4 address
    7. Gather the Device's hardware UDI info from DeviceInformationX. This is the timeconsuming part, Threaded to increase speed
    8. Write the results as found to CSV
    9. Also write any AXL only phones that may be inactive in RIS data

 .NOTES
    Author:        Collin Moerman
    Date:          2023-03-13
    Version:       1.3.29
"""
import csv
import os
import sys
import re
import errno
import importlib.resources
from multiprocessing import Pool
import tempfile
import requests
from lxml import etree
from zeep import Client
from zeep.cache import SqliteCache
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
from requests import Session
from requests.auth import HTTPBasicAuth
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
from tqdm import tqdm


def getFirstZeepItem(resp):
    """Take Zeep's AXL response format and grab the first item from it, AXL result is in a list with one item

    Args:
        resp (object): Zeep response object from WSDL request

    Returns:
        object: The nested obeject from the return
    """
    return resp['return'][next(iter(resp['return']))]
#def

def getChunks(fullList:list, chunksize:int=900) -> list:
    """Take a list and chunk it into multiple lists with a maximum size per list

    Args:
        fullList (list): Full list of arbitrary length
        chunksize (int, optional): The maximum size of each list chunk. Defaults to 900.

    Returns:
        list: List of lists with chunksize limit imposed
    """
    chunkList = []
    tempList = []
    for phone in fullList:
        tempList.append(phone['Name'])
        #Size reached, chunk now
        if len(tempList) > (chunksize - 1):
            chunkList.append(tempList)
            tempList = []
        #if
    #for
    chunkList.append(tempList)
    return chunkList
#def

def getDeviceInformationWorker(phone:dict) -> dict:
    """Access phone Webpage for hardware device information

    Args:
        phone (dict): Single phone dict

    Returns:
        dict: Modified dict
    """
    try:
        devInfo = requests.get(f"http://{phone['IPAddress']}/DeviceInformationX", timeout=5)
    except requests.exceptions.Timeout:
        phone['Error'] = "Request Timeout: ensure phone IP is reachable"
        return phone
    except requests.exceptions.ConnectionError:
        phone['Error'] = "Connection Error: ensure phone WebAccess is enabled"
        return phone
    except requests.exceptions.RequestException:
        phone['Error'] = "Request Exception: request was not properly understood"
        return phone
    #try
    devXML = etree.fromstring(bytes(devInfo.text, encoding='utf8'))
    udi = devXML.xpath('//udi/text()')[0]
    match = re.search(r'.*(CP-.+).(V\d+).(.+).', udi, re.DOTALL)
    if match:
        phone['ModelNumber'] = match.group(1)
        phone['HardwareRevision'] = match.group(2)
        phone['SerialNumber'] = match.group(3)
    #if
    return phone
#def

class CiscoMPPHWDiscovery:
    """ Applicaton logic """
    __HW_MODELS = [
        "Cisco 7821",
        "Cisco 7861",
        "Cisco 7841"
    ]
    __DATA_COLUMNS = [
        'Name',
        'Model',
        'Description',
        'Status',
        'ActiveLoadID',
        'InactiveLoadID',
        'IPAddress',
        'SerialNumber',
        'ModelNumber',
        'HardwareRevision',
        'Error'
    ]
    def __init__(self, hostname, username, password, outFile, schemaPath=None, processes=8):
        self._hostname = hostname
        self._username = username
        self._password = password

        if schemaPath is None:
            with importlib.resources.path("ciscompphwdiscovery", "schema") as schemaPath:
                self._schemaPath  = str(schemaPath)
            #with
        else:
            self._schemaPath = schemaPath
        #if
        
        #fail upfront on initialization if the file already exists so we dont do all our processing before being unable to create the file
        if os.path.isfile(outFile):
            raise FileExistsError(errno.EEXIST,os.strerror(errno.EEXIST), outFile)
        #if

        self._outFile = outFile
        self._processes = processes
        self._phoneData = {}
        self._axlVersion = "10.0"  # Default to AXL 10.0 as a minimum version supported
        self.__cli = False # Run from CLI or module
    #def

    def __getAxlVersion(self):
        """Determine CUCM AXL version using UDS API's version string
        """
        disable_warnings(InsecureRequestWarning)
        udsLocation = f'https://{self._hostname}/cucm-uds/version'
        udsSession = Session()
        udsSession.verify = False
        udsResp = udsSession.get(udsLocation)
        udsXML = etree.fromstring(bytes(udsResp.text, encoding='utf8'))
        version = udsXML.xpath('//version/text()')[0]
        if re.search(r'(\d+\.\d+).*', version):
            self._axlVersion = re.sub(r'(\d+\.\d+).*', r'\1', version, 0)
        #if
    #def

    def __getAxlHwPhones(self):
        """Query AXL for physical (SEP) phones, filter to models with HW revision requirements
        """
        disable_warnings(InsecureRequestWarning)
        axlWSDL = os.path.join(self._schemaPath, self._axlVersion, 'AXLAPI.wsdl')
        if not os.path.isfile(axlWSDL):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), axlWSDL)
        #if
        axlLocation = f'https://{self._hostname}:8443/axl/'
        axlBinding = "{http://www.cisco.com/AXLAPIService/}AXLAPIBinding"
        axlSession = Session()
        axlSession.verify = False
        axlSession.auth = HTTPBasicAuth(self._username, self._password)
        axlTransport = Transport(cache=SqliteCache(), session=axlSession, timeout=20)
        axlHistory = HistoryPlugin()
        axlclient = Client(wsdl=axlWSDL, transport=axlTransport, plugins=[axlHistory])
        axl = axlclient.create_service(axlBinding, axlLocation)

        axlPhones = getFirstZeepItem(axl.listPhone(searchCriteria={'name':'SEP%'}, returnedTags={'name':'','model':'','description':''}))
        for phone in axlPhones:
            if phone.model in self.__HW_MODELS:
                # Initialize dictionary based on data columns
                self._phoneData[phone.name] = {column: None for column in self.__DATA_COLUMNS}
                self._phoneData[phone.name]['Name'] =  phone.name
                self._phoneData[phone.name]['Model'] = phone.model
                self._phoneData[phone.name]['Description'] = phone.description
            #if
        #for
    #def

    def __getRISDeviceStatus(self, phones:list):
        """Query RIS API for device status information

        Args:
            phones (list): An RIS chunk to process
        """
        disable_warnings(InsecureRequestWarning)
        risWSDL = f'https://{self._hostname}:8443/realtimeservice2/services/RISService70?wsdl'
        risLocation = f'https://{self._hostname}:8443/realtimeservice2/services/RISService70'
        risBinding = '{http://schemas.cisco.com/ast/soap}RisBinding'
        risSession = Session()
        risSession.verify = False
        risSession.auth = HTTPBasicAuth(self._username, self._password)
        risTransport = Transport(cache=SqliteCache(), session=risSession, timeout=20)
        risHistory = HistoryPlugin()
        risClient = Client(wsdl=risWSDL, transport=risTransport, plugins=[risHistory])
        ris = risClient.create_service(risBinding, risLocation)
        criteria = {
            'MaxReturnedDevices': f'{len(phones)}',
            'DeviceClass': 'Phone',
            'Model': '255',
            'Status': 'Any',
            'NodeName': '',
            'SelectBy': 'Name',
            'SelectItems': {
                'item': phones
            },
            'Protocol': 'Any',
            'DownloadStatus': 'Any'
        }
        risDevices = ris.selectCmDeviceExt(CmSelectionCriteria=criteria, StateInfo='')['SelectCmDeviceResult']
        for node in risDevices['CmNodes']['item']:
            for device in node['CmDevices']['item']:
                self._phoneData[device.Name]['Status'] = device.Status
                self._phoneData[device.Name]['ActiveLoadID'] = device.ActiveLoadID
                self._phoneData[device.Name]['InactiveLoadID'] = device.InactiveLoadID
                #grab the item's first IPv4 address, or None
                self._phoneData[device.Name]['IPAddress'] = next((IP for IP in device.IPAddress['item'] if IP['IPAddrType'] == 'ipv4'), None)
                if self._phoneData[device.Name]['IPAddress'] is not None:
                    self._phoneData[device.Name]['IPAddress'] = self._phoneData[device.Name]['IPAddress']['IP']
                #if
            #for
        #for
    #def

    def __getDeviceInformation(self, ipPhones:list):
        """Take a list of phones with IP addresses and check Hardware data. Threaded for speed increase.
           Calls global function for pickling

        Args:
            ipPhones (list): List of Phone data with IP addresses
        """
        with Pool(processes=self._processes) as procPool:
            if(self.__cli):
                results = list(tqdm(procPool.imap_unordered(getDeviceInformationWorker, ipPhones), total=len(ipPhones)))
            else:
                results = list(procPool.imap_unordered(getDeviceInformationWorker, ipPhones))
            #if
            procPool.close()
            procPool.join()
        #with
        for result in results:
            self._phoneData[result['Name']] = result
        #for
    #def

    def __getModelCount(self, model:str) -> int:
        """Get count of deivces with the given model

        Args:
            model (str): Model to check against

        Returns:
            int: Count of Model
        """
        return len([phone for phone in self._phoneData.values() if phone['Model'] == model])
    #def

    def __getKeyCount(self, key:str) -> int:
        """Get count of non-None values for given key

        Args:
            key (str): Key to check against

        Returns:
            int: Count of non-None values
        """
        return len([phone for phone in self._phoneData.values() if phone[key] is not None])
    #def

    def __console(self, data:str, term:str=None):
        """Print to console only during CLI operation

        Args:
            data (str): data tp print
            term (str, optional): Optional terminator string, if None, print will send newline
        """        
        if self.__cli:
            print(data, end=term)
    #def

    def __export(self):
        """Export data to CSV
        """
        with open(self._outFile, 'w', encoding='utf8') as ouput:
            csvOut = csv.DictWriter(ouput, fieldnames=self.__DATA_COLUMNS, lineterminator='\n', quoting=csv.QUOTE_ALL)
            csvOut.writeheader()
            csvOut.writerows(self._phoneData.values())
        #with
        self.__console(f"Wrote data to {self._outFile}")
    #def

    def discover(self) ->list:
        """Execute discovery and return results

        Returns:
            list: the discovered results as a list of dict
        """
        self.__console('Gathering AXL Version...', term='')
        self.__getAxlVersion()
        self.__console(f" {self._axlVersion}")

        self.__console('Gathering phones with hardware revision requirements...')
        self.__getAxlHwPhones()
        for model in self.__HW_MODELS:
            self.__console(f"{model}: {self.__getModelCount(model)}", term ='    ')
        #for
        self.__console('')

        #return empty list
        if len(self._phoneData.keys()) == 0:
            return self._phoneData.values()
                
        self.__console('Gathering phone RIS data...')
        risChunks = getChunks(self._phoneData.values())
        if self.__cli:
            for chunk in tqdm(risChunks):
                self.__getRISDeviceStatus(chunk)
            #for
        else:
            for chunk in risChunks:
                self.__getRISDeviceStatus(chunk)
            #for
        #if

        #filter to only phones where IP Address was discovered
        ipPhones = [ipPhone for ipPhone in self._phoneData.values() if ipPhone['IPAddress'] is not None]
        self.__console(f"Count of devices with IP address discovered: {len(ipPhones)}")
        self.__console('Gathering phone hardware data...')
        self.__getDeviceInformation(ipPhones)
        self.__console(f"Count of devices fully discovered: {self.__getKeyCount('HardwareRevision')}")
        self.__console(f"Count of devices with errors: {self.__getKeyCount('Error')}")
        self.__console('Discovery Complete')

        return list(self._phoneData.values())
    #def

    def run(self):
        """CLI mode: run discovery and save to file
        """        
        # self.__cli = True
        self.discover()
        self.__export()
    #def
#class
