from setuptools import setup, find_packages

with open('requirements.txt') as fr:
    requirements = fr.readlines()

setup(
    name='lazyplex',
    version='0.0.1',
    author_email='chewba34@gmail.com',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'lazyplex = lazyplex.run:main',
        ]
    },
)