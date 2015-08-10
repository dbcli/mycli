import re
import ast
from setuptools import setup, find_packages

_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('mycli/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))

description = 'CLI for MySQL Database. With auto-completion and syntax highlighting.'


setup(
        name='mycli',
        author='Amjith Ramanujam',
        author_email='amjith[dot]r[at]gmail.com',
        version=version,
        license='LICENSE.txt',
        url='http://mycli.net',
        packages=find_packages(),
        package_data={'mycli': ['myclirc', '../AUTHORS', '../SPONSORS']},
        description=description,
        long_description=description,
        install_requires=[
            'click >= 4.1',
            'Pygments >= 2.0',  # Pygments has to be Capitalcased. WTF?
            'prompt_toolkit==0.45',
            'PyMySQL >= 0.6.6',
            'sqlparse == 0.1.14',
            'configobj >= 5.0.6',
            ],
        entry_points='''
            [console_scripts]
            mycli=mycli.main:cli
        ''',
        classifiers=[
            'Intended Audience :: Developers',
            'License :: OSI Approved :: BSD License',
            'Operating System :: Unix',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2.6',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.3',
            'Programming Language :: Python :: 3.4',
            'Programming Language :: SQL',
            'Topic :: Database',
            'Topic :: Database :: Front-Ends',
            'Topic :: Software Development',
            'Topic :: Software Development :: Libraries :: Python Modules',
            ],
        )
