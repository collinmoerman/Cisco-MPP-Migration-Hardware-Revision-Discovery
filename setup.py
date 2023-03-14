import setuptools

with open("README.md", "r") as fh:  # Use README for PyPI description
    long_description = fh.read()

classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
]

install_requires = [
    "lxml>=4.8.0",
    "requests>=2.25.1",
    "tqdm>=4.65.0",
    "urllib3>=1.26.5",
    "zeep>=4.2.1"
]

setuptools.setup(
    name="cisco-mpphw-discovery",
    version="3.0",
    author="Collin Moerman",
    author_email="collin@moerman.us",
    description="Cisco MPP Migration Hardware Revision Discovery",
    url="https://github.com/collinmoerman/cisco-mpphw-discovery",
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=["cisco-mpphw-discovery"],
    install_requires=install_requires,
    keywords=["Cisco", "MPP", "CUCM", "AXL", "7821", "7841", "7861"],
    classifiers=classifiers,
    entry_points={"console_scripts": ["cisco-mpphw-discovery = cisco-mpphw-discovery.cisco-mpphw-discovery:main"]},
)