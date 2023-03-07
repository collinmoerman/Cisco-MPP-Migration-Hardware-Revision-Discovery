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
    7. Gather the Device's hardware UDI info from DeviceInformationX. This is the timeconsuming part, so provide a progress bar for each chunk
    8. Write the results as found to CSV
    9. Also write any AXL only phones that may be inactive in RIS data
 
 .NOTES
    Author:        Collin Moerman
    Date:          2023-03-07
    Version:       1.0
 
"""
import csv, os, sys, re, argparse
from zeep import Client
from zeep.cache import SqliteCache
from zeep.transports import Transport
from zeep.exceptions import Fault
from zeep.plugins import HistoryPlugin
from requests import Session
from requests.auth import HTTPBasicAuth
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
from lxml import etree
import requests

import pprint
pp = pprint.PrettyPrinter(indent=4)

def progress(count, total, status=''):
    if total == 0: return
    bar_len = 30
    filled_len = int(round(bar_len * count / float(total)))
    percents = round(100.0 * count / float(total), 1)
    bar = '=' * filled_len + ' ' * (bar_len - filled_len)
    sys.stdout.write('\r[%s] %06.2f%%\t%s\r' % (bar, percents, status))
    sys.stdout.flush()
#def

def UniqueKeys(arr):
    return list(set(val for dic in arr for val in dic.keys()))
#def

def show_history():
    for item in [history.last_sent, history.last_received]:
        print(etree.tostring(item["envelope"], encoding="unicode", pretty_print=True))
    #for
#def

def getFirstZeepItem(resp):
    return resp['return'][next(iter(resp['return']))]
#def

hw_models = [
    "Cisco 7821",
    "Cisco 7861",
    "Cisco 7841"
]

if __name__=="__main__":
    argp = argparse.ArgumentParser(description='Discover Phone Hardware revisions for migration to Webex Calling')
    argp.add_argument('-s', dest='host', metavar='cucm.example.com', type=str, required=True, help='Server FQDN or IP address')
    argp.add_argument('-u', dest='username', metavar='axladmin', type=str, required=True, help='Application user with AXL, RIS, and Phone API access')
    argp.add_argument('-p', dest='password', metavar='@xL!sC00l', type=str, required=True, help='Application user password')
    argp.add_argument('-o', dest='f_out', default='', metavar='c:\\path\\to\\file.csv',  type=argparse.FileType('w'), help='CSV output document')
    args = argp.parse_args()

    columns = [
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
    output = csv.DictWriter(args.f_out, fieldnames=columns, lineterminator='\n', quoting=csv.QUOTE_ALL)
    output.writeheader()

    disable_warnings(InsecureRequestWarning)

    #determine CUCM major version using UDS API
    udslocation = 'https://{host}/cucm-uds/version'.format(host=args.host)
    udssession = Session()
    udssession.verify = False
    udsResp = udssession.get(udslocation)
    udsXML = etree.fromstring(bytes(udsResp.text, encoding='utf8'))
    version = udsXML.xpath('//version/text()')[0]
    major_ver = re.sub(r'(\d+\.\d+).*', r'\1', version, 0)

    axlwsdl = 'schema\\{ver}\\AXLAPI.wsdl'.format(ver=major_ver)
    axllocation = 'https://{host}:8443/axl/'.format(host=args.host)
    axlbinding = "{http://www.cisco.com/AXLAPIService/}AXLAPIBinding"
    axlsession = Session()
    axlsession.verify = False
    axlsession.auth = HTTPBasicAuth(args.username, args.password)
    axltransport = Transport(cache=SqliteCache(), session=axlsession, timeout=20)
    axlhistory = HistoryPlugin()
    axlclient = Client(wsdl=axlwsdl, transport=axltransport, plugins=[axlhistory])
    axl = axlclient.create_service(axlbinding, axllocation)

    PhoneListRes = getFirstZeepItem(axl.listPhone(searchCriteria={'name':'SEP%'}, returnedTags={'name':'','model':'','description':''}))
    hw_phones = {}
    #chunk of up to 900 phones
    ris_phones_split = []
    ris_phones = []
    for phone in PhoneListRes:
        if phone.model in hw_models:
            hw_phones[phone.name] = {
                'Name': phone.name, 
                'Model': phone.model, 
                'Description': phone.description,
                'Status':'',
                'ActiveLoadID':'',
                'InactiveLoadID':'',
                'IPAddress':'',
                'SerialNumber':'',
                'ModelNumber':'',
                'HardwareRevision':'',
                'Error':''
            }
            ris_phones.append(phone.name)
            #add to the split list after 900 phones
            if len(ris_phones) > 899:
                ris_phones_split.append(wxc_phones)
                ris_phones = []
            #if
        #if
    #for
    ris_phones_split.append(ris_phones)
    print('Count of Devices for Hardware Revision Validation: {dev}'.format(dev=len(hw_phones))) 

    riswsdl = 'https://{host}:8443/realtimeservice2/services/RISService70?wsdl'.format(host=args.host)
    rislocation = 'https://{host}:8443/realtimeservice2/services/RISService70'.format(host=args.host)
    risbinding = '{http://schemas.cisco.com/ast/soap}RisBinding'
    rissession = Session()
    rissession.verify = False
    rissession.auth = HTTPBasicAuth(args.username, args.password)
    ristransport = Transport(cache=SqliteCache(), session=rissession, timeout=20)
    rishistory = HistoryPlugin()
    risclient = Client(wsdl=riswsdl, transport=ristransport, plugins=[rishistory])
    ris = risclient.create_service(risbinding, rislocation)
    for ris_phones in ris_phones_split:
        criteria = {
            'MaxReturnedDevices': '900',
            'DeviceClass': 'Phone',
            'Model': '255',
            'Status': 'Any',
            'NodeName': '',
            'SelectBy': 'Name',
            'SelectItems': {
                'item': ris_phones
            },
            'Protocol': 'Any',
            'DownloadStatus': 'Any'
        }
        risDevices = ris.selectCmDeviceExt(CmSelectionCriteria=criteria, StateInfo='')['SelectCmDeviceResult']
        print('AXL Devices: {axl}\tRIS Devices: {ris}'.format(axl=len(ris_phones), ris=risDevices['TotalDevicesFound']))
        dev_count = 0
        for node in risDevices['CmNodes']['item']:
            for device in node['CmDevices']['item']:
                progress(count=dev_count, total=risDevices['TotalDevicesFound'], status=device.Name)
                dev_count += 1
                hw_phones[device.Name]['Status'] = device.Status
                hw_phones[device.Name]['ActiveLoadID'] = device.ActiveLoadID
                hw_phones[device.Name]['InactiveLoadID'] = device.InactiveLoadID
                hw_phones[device.Name]['IPAddress'] = next((IP for IP in device.IPAddress['item'] if IP['IPAddrType'] == 'ipv4'), None)
                if hw_phones[device.Name]['IPAddress'] != None:
                    hw_phones[device.Name]['IPAddress'] = hw_phones[device.Name]['IPAddress']['IP']
                    try:
                        devInfo = requests.get('http://{ip}/DeviceInformationX'.format(ip=hw_phones[device.Name]['IPAddress']), timeout=5)
                        devXML = etree.fromstring(bytes(devInfo.text, encoding='utf8'))
                        udi = devXML.xpath('//udi/text()')[0]
                        match = re.search(r'.*(CP-.+).(V\d+).(.+).', udi, re.DOTALL)
                        if match:
                            hw_phones[device.Name]['ModelNumber'] = match.group(1)
                            hw_phones[device.Name]['HardwareRevision'] = match.group(2)
                            hw_phones[device.Name]['SerialNumber'] = match.group(3)
                        #if
                    except requests.exceptions.Timeout:
                        hw_phones[device.Name]['Error'] = "Request Timeout: ensure phone IP is reachable"
                    except requests.exceptions.ConnectionError:
                        hw_phones[device.Name]['Error'] = "Connection Error: ensure phone WebAccess is enabled"
                    except requests.exceptions.RequestException as e:
                        hw_phones[device.Name]['Error'] = "Request Exception: request was not properly understood"
                    #try
                #if

                #write out the result as complete, removing it
                output.writerow(hw_phones.pop(device.Name))
            #for
        #for
    #for
    #write out the phones where RIS data was not found
    for phone in hw_phones.values():
        output.writerow(phone)
    #for
#main