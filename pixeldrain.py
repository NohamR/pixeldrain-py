#!/usr/bin/env python3
import argparse
import logging
import mimetypes
import os
import sys
from base64 import b64encode
from typing import List, Optional, Dict, Any, Union

import requests
from dotenv import load_dotenv
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
PIXELDRAIN_API_KEY = os.getenv("PIXELDRAIN_API_KEY")

# Constants
CHUNK_SIZE = 8192
TIMEOUT = 30


def display_file_size(size: int) -> str:
    """Return a human-readable file size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def upload_to_pixeldrain(file_path: str) -> Optional[str]:
    """
    Upload a file to pixeldrain.com and return the shareable URL.

    Args:
        file_path (str): Path to the file to upload

    Returns:
        Optional[str]: The pixeldrain URL if successful, None otherwise

    Raises:
        FileNotFoundError: If file not found
        requests.RequestException: If upload fails
    """
    try:
        if not os.path.exists(file_path):
            logger.error("File not found: %s", file_path)
            return None

        logger.info("Uploading file to pixeldrain: %s", file_path)

        file_size = os.path.getsize(file_path)

        # Create authorization header for API key authentication
        auth_header = f"Basic {b64encode(f':{PIXELDRAIN_API_KEY}'.encode()).decode()}"

        with open(file_path, 'rb') as file:
            with tqdm(
                total=file_size,
                unit="B",
                unit_scale=True,
                desc=f"Uploading {os.path.basename(file_path)}...",
            ) as progress:
                def progress_callback(monitor):
                    progress.update(monitor.bytes_read - progress.n)

                # Detect MIME type for proper content handling
                content_type = (mimetypes.guess_type(file_path)[0] or
                               "application/octet-stream")
                encoder = MultipartEncoder(
                    fields={
                        "file": (os.path.basename(file_path), file, content_type),
                    }
                )
                monitor = MultipartEncoderMonitor(encoder, progress_callback)
                headers = {
                    "Content-Type": monitor.content_type,
                    "Authorization": auth_header
                }

                response = requests.post(
                    'https://pixeldrain.com/api/file',
                    data=monitor,
                    headers=headers,
                    timeout=TIMEOUT
                )

        if response.status_code in (200, 201):
            json_response = response.json()
            if json_response['success']:
                file_id = json_response['id']
                logger.info("Upload completed: %s", os.path.basename(file_path))
                return f"https://pixeldrain.com/u/{file_id}"
            logger.error("Upload failed: %s",
                        json_response.get('message', 'Unknown error'))
            return None

        logger.error("Upload failed: HTTP %s - %s",
                    response.status_code, response.text)
        return None

    except (OSError, requests.RequestException) as error:
        logger.error("Error uploading to pixeldrain: %s", error)
        return None


def _handle_successful_download(response, save_path: str, filename: str,
                              download_folder: str) -> str:
    """Handle successful download response."""
    total_size = int(response.headers.get('content-length', 0))
    os.makedirs(download_folder, exist_ok=True)

    # Download with progress bar
    with open(save_path, 'wb') as file:
        with tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            desc=f"Downloading {filename}...",
        ) as progress:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:  # Filter out keep-alive chunks
                    file.write(chunk)
                    progress.update(len(chunk))

    logger.info("Download completed: %s", save_path)
    return save_path


def _handle_404_error(response):
    """Handle 404 error response."""
    try:
        json_response = response.json()
        logger.error("File not found: %s",
                    json_response.get('message', 'The file could not be found'))
    except requests.exceptions.JSONDecodeError:
        logger.error("File not found")


def _handle_403_error(response, file_id: str):
    """Handle 403 error response."""
    try:
        json_response = response.json()
        error_value = json_response.get('value', '')
        message = json_response.get('message', 'Access forbidden')

        if 'rate_limited_captcha_required' in error_value:
            logger.error("Rate limited: %s", message)
            logger.info("Please visit https://pixeldrain.com/u/%s to complete captcha",
                       file_id)
        elif 'virus_detected_captcha_required' in error_value:
            logger.error("Virus detected: %s", message)
            logger.info("Please visit https://pixeldrain.com/u/%s to complete captcha",
                       file_id)
        else:
            logger.error("Access forbidden: %s", message)
    except requests.exceptions.JSONDecodeError:
        logger.error("Access forbidden")


def download_from_pixeldrain(file_id: str, download_folder: str,
                           force_download: bool = False) -> Optional[str]:
    """
    Download a file from pixeldrain.com using its file ID.

    Args:
        file_id (str): The pixeldrain file ID
        download_folder (str): Directory to save the downloaded file
        force_download (bool): Force download by adding ?download parameter

    Returns:
        Optional[str]: Path to downloaded file if successful, None otherwise
    """
    try:
        if not PIXELDRAIN_API_KEY:
            logger.warning("PIXELDRAIN_API_KEY not found - downloading as anonymous user")
            headers = {}
        else:
            auth_header = f"Basic {b64encode(f':{PIXELDRAIN_API_KEY}'.encode()).decode()}"
            headers = {"Authorization": auth_header}

        # Get file info to determine the filename
        logger.info("Getting file info for %s", file_id)
        file_info = get_file_info_pixeldrain(file_id)
        if not file_info:
            logger.error("Could not retrieve file information")
            return None

        filename = file_info.get('name', f"{file_id}_unknown")
        save_path = os.path.join(download_folder, filename)

        # Construct URL with optional download parameter
        url = f'https://pixeldrain.com/api/file/{file_id}'
        if force_download:
            url += '?download'

        logger.info("Downloading file %s from pixeldrain", filename)

        response = requests.get(url, headers=headers, stream=True, timeout=TIMEOUT)
        if response.status_code == 200:
            return _handle_successful_download(response, save_path, filename, download_folder)

        if response.status_code == 404:
            _handle_404_error(response)
            return None

        if response.status_code == 403:
            _handle_403_error(response, file_id)
            return None

        logger.error("Download failed: HTTP %s - %s",
                    response.status_code, response.text)
        return None

    except (OSError, requests.RequestException) as error:
        logger.error("Error downloading from pixeldrain: %s", error)
        return None


def get_stats_pixeldrain() -> Optional[Dict[str, Any]]:
    """Get stats from pixeldrain.com."""
    try:
        if not PIXELDRAIN_API_KEY:
            logger.error("PIXELDRAIN_API_KEY not found in environment variables")
            return None

        logger.info("Fetching files stats from pixeldrain")
        auth_header = f"Basic {b64encode(f':{PIXELDRAIN_API_KEY}'.encode()).decode()}"
        headers = {"Authorization": auth_header}

        response = requests.get('https://pixeldrain.com/api/user/files',
                              headers=headers, timeout=TIMEOUT)

        if response.status_code == 200:
            data = response.json()
            logger.info("Successfully retrieved stats for %s files",
                       len(data.get('files', [])))
            return data

        logger.error("Failed to get stats: HTTP %s - %s",
                    response.status_code, response.text)
        return None

    except (OSError, requests.RequestException) as error:
        logger.error("Error getting stats from pixeldrain: %s", error)
        return None


def print_stats_pixeldrain() -> None:
    """Print account statistics from pixeldrain.com."""
    stats = get_stats_pixeldrain()
    if stats and 'files' in stats:
        files = stats['files']
        logger.info("Found %s files in account", len(files))

        # Calculate some basic statistics
        total_size = sum(file.get('size', 0) for file in files)
        total_views = sum(file.get('views', 0) for file in files)
        total_downloads = sum(file.get('downloads', 0) for file in files)
        total_bandwidth = sum(file.get('bandwidth_used', 0) for file in files)

        logger.info("Total size: %.2f GB", total_size / (1024**3))
        logger.info("Total views: %s", f"{total_views:,}")
        logger.info("Total downloads: %s", f"{total_downloads:,}")
        logger.info("Total bandwidth used: %.2f GB", total_bandwidth / (1024**3))

        # Show top 5 most downloaded files
        top_downloads = sorted(files, key=lambda x: x.get('downloads', 0), reverse=True)[:5]
        logger.info("Top 5 most downloaded files:")
        for i, file in enumerate(top_downloads, 1):
            logger.info("%s. %s - %s downloads", i, file.get('name', 'Unknown'),
                       file.get('downloads', 0))
    else:
        logger.error("Failed to get stats")


def get_file_info_pixeldrain(file_ids: Union[str, List[str]]) -> Optional[
    Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """Get information about one or more files from pixeldrain.com."""
    try:
        if not PIXELDRAIN_API_KEY:
            logger.error("PIXELDRAIN_API_KEY not found in environment variables")
            return None

        # Handle both single ID and list of IDs
        if isinstance(file_ids, list):
            if len(file_ids) > 1000:
                logger.error("Maximum 1000 files per request")
                return None
            ids_str = ",".join(file_ids)
            logger.info("Fetching info for %s files from pixeldrain", len(file_ids))
        else:
            ids_str = file_ids
            logger.info("Fetching info for file %s from pixeldrain", file_ids)

        auth_header = f"Basic {b64encode(f':{PIXELDRAIN_API_KEY}'.encode()).decode()}"
        headers = {"Authorization": auth_header}

        response = requests.get(f'https://pixeldrain.com/api/file/{ids_str}/info',
                              headers=headers, timeout=TIMEOUT)

        if response.status_code == 200:
            data = response.json()
            logger.info("Successfully retrieved file info")
            return data

        if response.status_code == 404:
            json_response = response.json()
            logger.error("File not found: %s", json_response.get('value', 'Unknown error'))
            return None

        logger.error("Failed to get file info: HTTP %s - %s",
                    response.status_code, response.text)
        return None

    except (OSError, requests.RequestException) as error:
        logger.error("Error getting file info from pixeldrain: %s", error)
        return None


def print_file_info_pixeldrain(file_ids: Union[str, List[str]]) -> None:
    """Print information about one or more files from pixeldrain.com."""
    file_info = get_file_info_pixeldrain(file_ids)
    if file_info:
        logger.info("File name: %s", file_info.get('name', 'Unknown'))
        logger.info("File size: %s", display_file_size(file_info.get('size', 0)))
        logger.info("Views: %s", f"{file_info.get('views', 0):,}")
        logger.info("Downloads: %s", f"{file_info.get('downloads', 0):,}")
        logger.info("Upload date: %s", file_info.get('date_upload', 'Unknown'))


def reupload_pixeldrain(file_ids: Union[str, List[str]], download_folder: str,
                       force_download: bool = False) -> Optional[str]:
    """Reupload files from pixeldrain.com."""
    downloaded_file = download_from_pixeldrain(file_ids, download_folder, force_download)
    if not downloaded_file:
        logger.error("Download failed, cannot reupload")
        return None

    return upload_to_pixeldrain(downloaded_file)


def parse_file_id(input_str: str) -> str:
    """Extract file ID from pixeldrain URL or return as-is if already an ID."""
    # Handle various pixeldrain URL formats
    input_str = input_str.strip()
    if "pixeldrain.com/u/" in input_str:
        return input_str.split("pixeldrain.com/u/")[-1]
    if "pixeldrain.com/f/" in input_str:
        return input_str.split("pixeldrain.com/f/")[-1]
    if "href.li/?" in input_str:
        return parse_file_id(input_str.split("href.li/?")[-1])
    return input_str


def _setup_argument_parser():
    """Set up the argument parser with all commands and options."""
    parser = argparse.ArgumentParser(
        description="CLI for pixeldrain.com - Upload, download, and manage files"
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload a file to pixeldrain')
    upload_parser.add_argument('file_path', help='Path to the file to upload')

    # Download command
    download_parser = subparsers.add_parser('download',
                                          help='Download a file from pixeldrain')
    download_parser.add_argument('file_id', help='File ID or pixeldrain URL')
    download_parser.add_argument('-d', '--dir', default='/tmp',
                                help='Download directory (default: /tmp)')
    download_parser.add_argument('-f', '--force', action='store_true',
                                help='Force download (?download parameter)')

    # Info command
    info_parser = subparsers.add_parser('info', help='Get file information')
    info_parser.add_argument('file_id', help='File ID or pixeldrain URL')

    # Stats command
    subparsers.add_parser('stats', help='Display account statistics')

    # Reupload command
    reupload_parser = subparsers.add_parser('reupload',
                                          help='Re-download and re-upload a file')
    reupload_parser.add_argument('file_id', help='File ID or pixeldrain URL')
    reupload_parser.add_argument('-d', '--dir', default='/tmp',
                                help='Temporary directory (default: /tmp)')
    reupload_parser.add_argument('-f', '--force', action='store_true',
                                help='Force download')

    return parser


def _handle_upload_command(args):
    """Handle upload command."""
    if not os.path.isfile(args.file_path):
        logger.error("File not found: %s", args.file_path)
        sys.exit(1)

    url = upload_to_pixeldrain(args.file_path)
    if url:
        print(f"File uploaded successfully: {url}")
    else:
        logger.error("Upload failed")
        sys.exit(1)


def _handle_download_command(args):
    """Handle download command."""
    file_id = parse_file_id(args.file_id)
    result = download_from_pixeldrain(file_id, args.dir, args.force)
    if result:
        print(f"File downloaded successfully: {result}")
        if os.path.exists(result):
            file_size = os.path.getsize(result)
            print(f"File size: {display_file_size(file_size)}")
    else:
        logger.error("Download failed")
        sys.exit(1)


def _handle_reupload_command(args):
    """Handle reupload command."""
    file_id = parse_file_id(args.file_id)
    url = reupload_pixeldrain(file_id, args.dir, args.force)
    if url:
        print(f"File re-uploaded successfully: {url}")
    else:
        logger.error("Re-upload failed")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = _setup_argument_parser()
    args = parser.parse_args()

    # Check for API key for commands that need it
    if args.command in ['upload', 'stats', 'info', 'reupload'] and not PIXELDRAIN_API_KEY:
        logger.error("PIXELDRAIN_API_KEY is required for this command. "
                    "Set it in your environment variables or in a .env file")
        sys.exit(1)

    if args.command == 'upload':
        _handle_upload_command(args)
    elif args.command == 'download':
        _handle_download_command(args)
    elif args.command == 'info':
        file_id = parse_file_id(args.file_id)
        print_file_info_pixeldrain(file_id)
    elif args.command == 'stats':
        print_stats_pixeldrain()
    elif args.command == 'reupload':
        _handle_reupload_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()