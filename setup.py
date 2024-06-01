#!/usr/bin/env python3
#
# Copyright (c) 2024 Hyeshik Chang
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

from setuptools import setup

setup(
    name='papersorter',
    version='0.1',
    description='Filters RSS feeds, predicts interest, and notifies '
                'Slack with top academic articles.',
    author='Hyeshik Chang',
    author_email='hyeshik@snu.ac.kr',
    url='https://github.com/ChangLabSNU/papersorter',
    download_url='https://github.com/ChangLabSNU/papersorter/releases',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    keywords=[
        'article alerts',
        'RSS feed',
        'personalized content'
    ],
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Education',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Topic :: Office/Business :: News/Diary',
        'Topic :: Text Processing :: Linguistic',
        'Topic :: Scientific/Engineering',
    ],
    packages=['PaperSorter', 'PaperSorter.providers', 'PaperSorter.tasks',
              'PaperSorter.contrib'],
    entry_points={
        'console_scripts': [
            'papersorter = PaperSorter.__main__:main',
        ],
    },
    install_requires=[
        'click >= 8.0',
        'numpy >= 1.20',
        'openai >= 1.30',
        'openpyxl >= 3.0',
        'pandas >= 2.0',
        'plyvel >= 1.5',
        'python-dotenv >= 1.0',
        'requests >= 2.7.0',
        'scikit-learn >= 1.4',
        'scipy >= 1.10',
        'xgboost > 2.0',
    ],
)
