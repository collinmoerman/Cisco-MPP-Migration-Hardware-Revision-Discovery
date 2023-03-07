# MPP Migration Hardware Revision Discovery

1. Gather CUCM version using UDS API, parse to major version
2. Use major version to inform WSDL file for AXL
3. Gather all SEP phones from CUCM using AXL listPhone API
4. Filter results to 7821, 7861, and 7841 models that are hardware revision restricted from MPP migration
5. Chunk into blocks of 900 for RISPort70 API query to avoid hitting the 1000 result max
6. Process each chunk, gathering the registration status, load information, and first IPv4 address
7. Gather the Device's hardware UDI info from DeviceInformationX. This is the timeconsuming part, so provide a progress bar for each chunk
8. Write the results as found to CSV
9. Also write any AXL only phones that may be inactive in RIS data