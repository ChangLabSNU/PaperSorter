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

"""
Sync and parse PubMed update files.

This module provides functions to:
1. Download PubMed update files from NCBI FTP
2. Parse XML files and yield article data in DataFrame chunks
"""

import requests
from html.parser import HTMLParser
from datetime import datetime
import re
import os
from pathlib import Path
import gzip
import xml.etree.ElementTree as ET
from typing import Optional, Generator, Union
import pandas as pd
from ..log import log


# ============================================================================
# Download functionality
# ============================================================================

class ApacheIndexParser(HTMLParser):
    """Parse Apache autoindex HTML to extract file information."""

    def __init__(self):
        super().__init__()
        self.files = []
        self.in_pre = False
        self.in_link = False
        self.current_file = None
        self.text_after_link = []

    def handle_starttag(self, tag, attrs):
        if tag == 'pre':
            self.in_pre = True
        elif tag == 'a' and self.in_pre:
            self.in_link = True
            for attr, value in attrs:
                if attr == 'href':
                    # Skip parent directory and query parameters
                    if not value.startswith('?') and not value.startswith('/'):
                        self.current_file = {'name': value, 'href': value}

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.in_pre = False
        elif tag == 'a' and self.in_pre:
            self.in_link = False
            # Start collecting text after the link
            self.text_after_link = []

    def handle_data(self, data):
        if self.in_pre and not self.in_link and self.current_file:
            # Collect text after the link ends
            self.text_after_link.append(data)

            # Check if we have a complete line (ends with newline or next link starts)
            full_text = ''.join(self.text_after_link)
            if '\n' in full_text or '<a' in data:
                # Parse the metadata from the text
                line = full_text.split('\n')[0].strip()

                # Apache format: "YYYY-MM-DD HH:MM  size"
                match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(\S+)', line)
                if match:
                    self.current_file['modified'] = match.group(1)
                    size_str = match.group(2)
                    if size_str != '-':
                        self.current_file['size'] = size_str

                self.files.append(self.current_file)
                self.current_file = None
                self.text_after_link = []


def fetch_pubmed_file_list(url="https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/", suffix=None):
    """
    Fetch and parse the file list from NCBI PubMed update files directory.

    Args:
        url: URL of the directory to list
        suffix: Optional file suffix to filter by (e.g., '.xml.gz', '.gz')

    Returns:
        List of file info dictionaries matching the suffix filter
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        parser = ApacheIndexParser()
        parser.feed(response.text)

        # Filter by suffix if specified
        if suffix:
            filtered_files = [f for f in parser.files if f['name'].endswith(suffix)]
        else:
            filtered_files = parser.files

        return filtered_files

    except requests.RequestException as e:
        log.error(f"Error fetching file list: {e}")
        return []


def download_pubmed_files(n=10, base_url="https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/",
                         tmpdir=None, suffix='.xml.gz', verbose=True):
    """
    Download the N most recent PubMed files to the temporary directory.

    Args:
        n: Number of most recent files to download
        base_url: Base URL of the PubMed update files directory
        tmpdir: Target directory (defaults to $TMPDIR from environment or ./tmp)
        suffix: File suffix to filter (default: '.xml.gz')
        verbose: Print progress messages

    Returns:
        List of tuples (filename, local_path, success) for each download attempt
    """
    # Get target directory from parameter or environment
    if tmpdir is None:
        tmpdir = os.environ.get('TMPDIR', './tmp')

    target_dir = Path(tmpdir)
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    # Fetch file list with suffix filter
    files = fetch_pubmed_file_list(base_url, suffix=suffix)
    if not files:
        if verbose:
            log.info(f"No files with suffix '{suffix}' found to sync")
        return []

    # Sort by modification date (most recent first)
    # Parse dates and sort
    for f in files:
        if 'modified' in f:
            try:
                # Parse "YYYY-MM-DD HH:MM" format
                f['modified_dt'] = datetime.strptime(f['modified'], '%Y-%m-%d %H:%M')
            except ValueError:
                f['modified_dt'] = datetime.min
        else:
            f['modified_dt'] = datetime.min

    sorted_files = sorted(files, key=lambda x: x['modified_dt'], reverse=True)

    # Take the N most recent files
    files_to_sync = sorted_files[:n]

    sync_results = []
    if verbose:
        log.info(f"Downloading {len(files_to_sync)} most recent files to {target_dir}")

    for file_info in files_to_sync:
        filename = file_info['name']
        file_url = base_url + filename
        local_path = target_dir / filename

        # Check if file already exists and has the same size
        if local_path.exists():
            local_size = local_path.stat().st_size
            # Parse remote size (e.g., "83M", "6.8M", "578K")
            remote_size_str = file_info.get('size', '0')
            try:
                if remote_size_str.endswith('M'):
                    remote_size = float(remote_size_str[:-1]) * 1024 * 1024
                elif remote_size_str.endswith('K'):
                    remote_size = float(remote_size_str[:-1]) * 1024
                elif remote_size_str.endswith('G'):
                    remote_size = float(remote_size_str[:-1]) * 1024 * 1024 * 1024
                else:
                    remote_size = float(remote_size_str)

                # Allow 5% difference in size (due to rounding in display)
                if abs(local_size - remote_size) / remote_size < 0.05:
                    if verbose:
                        log.debug(f"Skipping {filename} (already exists with same size)")
                    sync_results.append((filename, str(local_path), True))
                    continue
            except (ValueError, ZeroDivisionError):
                pass  # If we can't parse size, download anyway

        # Download the file
        if verbose:
            log.info(f"Downloading {filename} ({file_info.get('size', 'unknown size')})...")
        try:
            response = requests.get(file_url, stream=True, timeout=60)
            response.raise_for_status()

            # Write to file in chunks
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if verbose:
                log.info(f"Saved to {local_path}")
            sync_results.append((filename, str(local_path), True))

        except requests.RequestException as e:
            if verbose:
                log.error(f"Error downloading {filename}: {e}")
            sync_results.append((filename, str(local_path), False))

    return sync_results


# ============================================================================
# Parse functionality
# ============================================================================

def extract_article_info(article_element):
    """Extract article information from a PubMedArticle XML element."""
    info = {
        'pmid': '',
        'title': '',
        'authors': '',
        'journal': '',
        'abstract': '',
        'url': '',
        'pub_date': '',
        'issns': []  # List of ISSNs (can have print and electronic)
    }

    try:
        # Extract PMID
        pmid_elem = article_element.find('.//PMID')
        if pmid_elem is not None:
            info['pmid'] = pmid_elem.text.strip()
            # Default to PubMed URL
            info['url'] = f"https://pubmed.ncbi.nlm.nih.gov/{info['pmid']}/"

        # Look for DOI and prefer DOI-based URL if available
        article_id_list = article_element.find('.//ArticleIdList')
        if article_id_list is not None:
            for article_id in article_id_list.findall('ArticleId'):
                if article_id.get('IdType') == 'doi' and article_id.text:
                    info['url'] = f"https://dx.doi.org/{article_id.text.strip()}"
                    break

        # Extract Article Title
        title_elem = article_element.find('.//ArticleTitle')
        if title_elem is not None:
            # Clean title text, removing XML tags if present
            title_text = ''.join(title_elem.itertext()).strip()
            # Remove extra whitespace
            title_text = re.sub(r'\s+', ' ', title_text)
            # Remove trailing period if exists
            if title_text.endswith('.'):
                title_text = title_text[:-1]
            info['title'] = title_text

        # Extract Authors
        authors = []
        author_list = article_element.find('.//AuthorList')
        if author_list is not None:
            for author in author_list.findall('Author'):
                lastname = author.find('LastName')
                forename = author.find('ForeName')
                initials = author.find('Initials')

                if lastname is not None:
                    author_name = lastname.text
                    if forename is not None:
                        author_name = f"{lastname.text}, {forename.text}"
                    elif initials is not None:
                        author_name = f"{lastname.text}, {initials.text}"
                    authors.append(author_name)

        info['authors'] = '; '.join(authors)

        # Extract Journal Name
        # First try ISOAbbreviation (preferred)
        journal_elem = article_element.find('.//Journal/ISOAbbreviation')
        if journal_elem is not None and journal_elem.text:
            info['journal'] = journal_elem.text.strip()
        else:
            # Fall back to full journal title
            journal_elem = article_element.find('.//Journal/Title')
            if journal_elem is not None:
                info['journal'] = journal_elem.text.strip()
            else:
                # Try alternate location
                journal_elem = article_element.find('.//MedlineJournalInfo/MedlineTA')
                if journal_elem is not None:
                    info['journal'] = journal_elem.text.strip()

        # Extract ISSNs (both print and electronic)
        issns = []
        journal = article_element.find('.//Journal')
        if journal is not None:
            # Look for ISSN elements with IssnType attribute
            for issn_elem in journal.findall('.//ISSN'):
                if issn_elem.text:
                    issns.append(issn_elem.text.strip())
        # Also check MedlineJournalInfo for ISSNLinking
        issn_linking = article_element.find('.//MedlineJournalInfo/ISSNLinking')
        if issn_linking is not None and issn_linking.text:
            issns.append(issn_linking.text.strip())
        # Remove duplicates while preserving order
        seen = set()
        info['issns'] = [x for x in issns if not (x in seen or seen.add(x))]

        # Extract Abstract
        abstract_texts = []
        abstract_elem = article_element.find('.//Abstract')
        if abstract_elem is not None:
            # Handle structured abstracts with multiple AbstractText elements
            for abstract_text in abstract_elem.findall('AbstractText'):
                # Get label attribute if exists (e.g., "BACKGROUND", "METHODS")
                label = abstract_text.get('Label', '')
                text = ''.join(abstract_text.itertext()).strip()
                text = re.sub(r'\s+', ' ', text)

                if label:
                    abstract_texts.append(f"{label}: {text}")
                else:
                    abstract_texts.append(text)

        info['abstract'] = ' '.join(abstract_texts)

        # Extract Publication Date
        # First try DateCompleted
        date_completed = article_element.find('.//DateCompleted')
        if date_completed is not None:
            year = date_completed.find('Year')
            month = date_completed.find('Month')
            day = date_completed.find('Day')
            if year is not None and month is not None and day is not None:
                info['pub_date'] = f"{year.text}-{month.text.zfill(2)}-{day.text.zfill(2)}"

        # If DateCompleted not found, try PubMedPubDate with PubStatus="pubmed"
        if not info['pub_date']:
            history = article_element.find('.//History')
            if history is not None:
                for pubdate in history.findall('PubMedPubDate'):
                    if pubdate.get('PubStatus') == 'pubmed':
                        year = pubdate.find('Year')
                        month = pubdate.find('Month')
                        day = pubdate.find('Day')
                        if year is not None and month is not None and day is not None:
                            info['pub_date'] = f"{year.text}-{month.text.zfill(2)}-{day.text.zfill(2)}"
                            break

        # If still no date, try ArticleDate
        if not info['pub_date']:
            article_date = article_element.find('.//ArticleDate')
            if article_date is not None:
                year = article_date.find('Year')
                month = article_date.find('Month')
                day = article_date.find('Day')
                if year is not None and month is not None and day is not None:
                    info['pub_date'] = f"{year.text}-{month.text.zfill(2)}-{day.text.zfill(2)}"

        # Finally, try PubDate from Journal
        if not info['pub_date']:
            pub_date = article_element.find('.//PubDate')
            if pub_date is not None:
                year = pub_date.find('Year')
                month = pub_date.find('Month')
                day = pub_date.find('Day')
                if year is not None:
                    date_str = year.text
                    if month is not None:
                        # Convert month name to number if necessary
                        month_text = month.text
                        if month_text.isdigit():
                            date_str += f"-{month_text.zfill(2)}"
                        else:
                            # Handle month names
                            months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
                            month_num = months.get(month_text[:3], '01')
                            date_str += f"-{month_num}"
                        if day is not None:
                            date_str += f"-{day.text.zfill(2)}"
                    info['pub_date'] = date_str

    except Exception as e:
        log.error(f"Error processing article: {e}")

    return info


def parse_pubmed_xml_chunked(filepath: Union[str, Path], chunksize: int = 1000) -> Generator[pd.DataFrame, None, None]:
    """
    Parse a PubMed XML file and yield article data in DataFrame chunks.

    Args:
        filepath: Path to the XML file (can be .gz or plain XML)
        chunksize: Number of articles per chunk

    Yields:
        DataFrame chunks containing article information
    """
    filepath = Path(filepath)

    try:
        # Open file (handle both .gz and plain XML)
        if filepath.suffix == '.gz':
            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                content = f.read()
        else:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

        # Parse XML
        root = ET.fromstring(content)

        # Process articles in chunks
        current_chunk = []

        for article in root.findall('.//PubmedArticle'):
            article_info = extract_article_info(article)
            if article_info['pmid']:  # Only add if PMID exists
                current_chunk.append(article_info)

                # Yield chunk when it reaches the specified size
                if len(current_chunk) >= chunksize:
                    df = pd.DataFrame(current_chunk)
                    yield df
                    current_chunk = []

        # Yield remaining articles if any
        if current_chunk:
            df = pd.DataFrame(current_chunk)
            yield df

    except ET.ParseError as e:
        log.error(f"XML parsing error in {filepath}: {e}")
        # Return empty DataFrame on error
        yield pd.DataFrame(columns=['pmid', 'title', 'authors', 'journal', 'pub_date', 'abstract', 'url', 'issns'])
    except Exception as e:
        log.error(f"Error processing file {filepath}: {e}")
        yield pd.DataFrame(columns=['pmid', 'title', 'authors', 'journal', 'pub_date', 'abstract', 'url', 'issns'])


def parse_pubmed_directory_chunked(directory: Union[str, Path], chunksize: int = 1000,
                                  pattern: str = '*.xml.gz') -> Generator[pd.DataFrame, None, None]:
    """
    Parse all PubMed XML files in a directory and yield DataFrame chunks.

    Args:
        directory: Directory containing XML files
        chunksize: Number of articles per chunk
        pattern: File pattern to match (default: '*.xml.gz')

    Yields:
        DataFrame chunks containing article information from all files
    """
    directory = Path(directory)

    # Find all matching files
    xml_files = sorted(directory.glob(pattern))
    if not xml_files:
        log.warning(f"No files matching {pattern} found in {directory}")
        return

    log.info(f"Found {len(xml_files)} files to process")

    # Process each file and yield chunks
    for xml_file in xml_files:
        log.info(f"Processing {xml_file.name}...")
        for chunk_df in parse_pubmed_xml_chunked(xml_file, chunksize):
            yield chunk_df


# ============================================================================
# Convenience functions
# ============================================================================

def sync_and_parse_pubmed(n_files: int = 5, chunksize: int = 1000,
                         tmpdir: Optional[str] = None) -> Generator[pd.DataFrame, None, None]:
    """
    Download recent PubMed update files and parse them in chunks.

    Args:
        n_files: Number of recent files to download
        chunksize: Number of articles per DataFrame chunk
        tmpdir: Directory for downloads (defaults to $TMPDIR)

    Yields:
        DataFrame chunks containing parsed article data
    """
    # Download files
    if tmpdir is None:
        tmpdir = os.environ.get('TMPDIR', './tmp')

    sync_results = download_pubmed_files(n=n_files, tmpdir=tmpdir)

    # Parse downloaded files
    successful_downloads = [Path(path) for filename, path, success in sync_results if success]

    for filepath in successful_downloads:
        log.info(f"Parsing {filepath.name}...")
        for chunk_df in parse_pubmed_xml_chunked(filepath, chunksize):
            yield chunk_df