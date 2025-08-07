#!/usr/bin/env python3
#
# Copyright (c) 2024-2025 Seoul National University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

from setuptools import setup, find_packages
import os

# Read the README file for long description
def read_long_description():
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        return f.read()

setup(
    name='papersorter',
    version='0.3.0',
    description='Intelligent academic paper recommendation system with ML-powered filtering and Slack notifications',
    author='Hyeshik Chang',
    author_email='hyeshik@snu.ac.kr',
    url='https://github.com/ChangLabSNU/papersorter',
    download_url='https://github.com/ChangLabSNU/papersorter/releases',
    long_description=read_long_description(),
    long_description_content_type='text/markdown',
    keywords=[
        'academic papers',
        'machine learning',
        'RSS feed',
        'research tools',
        'paper recommendation',
        'slack integration',
        'scientific literature'
    ],
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Education',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Scientific/Engineering',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Scientific/Engineering :: Information Analysis',
    ],
    packages=find_packages(exclude=['tests*', 'notebook*', 'tools*', 'old*']),
    package_data={
        'PaperSorter': [
            'templates/*.html',
            'data/*.sql',
        ],
    },
    include_package_data=True,
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'papersorter = PaperSorter.__main__:main',
        ],
    },
    install_requires=[
        'click >= 8.0',
        'feedparser >= 6.0',
        'numpy >= 1.20',
        'openai >= 1.30',
        'pandas >= 2.0',
        'psycopg2-binary >= 2.9',
        'pgvector >= 0.2.0',
        'PyYAML >= 6.0',
        'requests >= 2.7.0',
        'scikit-learn >= 1.4',
        'scipy >= 1.10',
        'xgboost > 2.0',
        'Flask >= 2.0',
        'Flask-Login >= 0.6.0',
        'Authlib >= 1.2.0',
        'markdown2 >= 2.4.0',
    ],
)
