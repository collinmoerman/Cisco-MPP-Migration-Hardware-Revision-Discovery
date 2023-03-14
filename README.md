Cisco MPP Migration Hardware Revision Discovery
=======

Data Gathering tool for determining if Cisco 7821, 7841, and 7861 phones running enterprise firmware are compatiple with multi-platform firmware.  These models are only compatible above specific hardware revisions

**Reference:** 
[Convert between Enterprise Firmware and Multiplatform Firmware for Cisco IP Phone 7800 and 8800 Series Guide](https://www.cisco.com/c/en/us/products/collateral/collaboration-endpoints/unified-ip-phone-7800-series/guide-c07-742786.html)

<br />

## Logic Flow
1. Gather CUCM version using UDS API, parse to major version
2. Use major version to inform WSDL file for AXL from schema directory.  This directory should match the axlsqltoolkit.zip schema directory from CUCM plugins
3. Gather all SEP phones from CUCM using AXL listPhone API
4. Filter results to 7821, 7861, and 7841 models that are hardware revision restricted for MPP migration
5. Chunk into blocks of 900 for RISPort70 API query to avoid hitting the 1000 result max
6. Process each chunk, gathering the registration status, load information, and first IPv4 address
7. Gather the Device's hardware UDI info from DeviceInformationX.  As this is timeconsuming depending on the device count, it is multiprocessed
8. Write the results to CSV for review

<br />

## Installation

To install ciscompphwdiscovery using pip:
``` console
$ pip install ciscompphwdiscovery
```

<br />

To install ciscompphwdiscovery from source:
``` console
$ git clone https://github.com/collinmoerman/ciscompphwdiscovery.git
$ cd ciscompphwdiscovery
$ python3 -m build --wheel
$ pip install dist/ciscompphwdiscovery-x.y.z-py3-none-any.whl
```

## Examples

### CLI Execution
Using included schema, default processes
``` console
ciscompphwdiscovery --server cucm.example.com \
                    --username axluser \
                    --password  "@xL!sC00l" \
                    --output devices.csv
```
Fully specified
``` console
ciscompphwdiscovery --server cucm.example.com \
                    --username axluser\
                    --password "@xL!sC00l" \
                    --output devices.csv \
                    --schema path/to/schema \
                    --processes 4
```
### Script Execution

``` python
from ciscompphwdiscovery import CiscoMPPHWDiscovery
app = CiscoMPPHWDiscovery(hostname="cucm.example.com", 
                          username="axluser", 
                          password="@xL!sC00l",
                          outFile = "devices.csv", 
                          schemaPath="/path/to/schema",    # optional, defaults to package directory
                          processes=4)                     # optional, defaults to 8
devices = app.discover()
```

<br />
