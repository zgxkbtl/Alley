from setuptools import setup, find_packages

setup(
    name='alley',
    version='0.0.1',
    packages=find_packages(),
    requires=['websockets', 'asyncio'],
    entry_points={
        'console_scripts': [
            'alley-client = src.client.client:main',
            'alley-server = src.server.server:main'
        ]
    }
)
