from ciscompphwdiscovery import CiscoMPPHWDiscovery

import argparse
from os import path

def main():
    """Validate arguments as needed, pass to applciation, and run

    Raises:
        FileNotFoundError: If Schema path is not valid
        FileExistsError: if the output file already exists
    """
    argp = argparse.ArgumentParser(description='Discover Enterprise phone hardware revisions where restricted for migration to MPP Firmware')
    argp.add_argument('--server', dest='host', metavar='cucm.example.com', type=str, required=True, help='Server FQDN or IP address')
    argp.add_argument('--username', dest='username', metavar='axladmin', type=str, required=True, help='Application user with AXL, RIS, and Phone API access')
    argp.add_argument('--password', dest='password', metavar='"@xL!sC00l"', type=str, required=True, help='Application user password')
    argp.add_argument('--output', dest='outFile', metavar=path.join('path','to','file.csv'),  required=True,  type=str, help='CSV output document')
    argp.add_argument('--schema', dest='schemaPath', default=None, metavar=path.join('path','to','schema'), type=str, help='Path to AXL Schema files')
    argp.add_argument('--processes', dest='procs', default=8, metavar='8',  type=int, help='Number of processes for requesting Phone DeviceInformationX pages')
    args = argp.parse_args()
 
    app = CiscoMPPHWDiscovery(hostname=args.host, 
                      username=args.username, 
                      password=args.password,
                      outFile = args.outFile,
                      schemaPath=args.schemaPath,
                      processes=args.procs)
    app.run()
#def

if __name__ == '__main__':
    main()
#if