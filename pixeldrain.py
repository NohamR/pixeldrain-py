#!/usr/bin/env python3
import os
import requests
import mimetypes
from typing import List, Optional, Dict, Any, Union
import logging
import argparse
import sys
from base64 import b64encode
from dotenv import load_dotenv
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
PIXELDRAIN_API_KEY = os.getenv("PIXELDRAIN_API_KEY")


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
        Exception: If file not found or upload fails
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        
        logger.info(f"Uploading file to pixeldrain: {file_path}")
        
        file_size = os.path.getsize(file_path)
        
        # Create authorization header for API key authentication
        auth_header = f"Basic {b64encode(f':{PIXELDRAIN_API_KEY}'.encode()).decode()}"
        
        with open(file_path, 'rb') as f:
            with tqdm(
                total=file_size,
                unit="B",
                unit_scale=True,
                desc=f"Uploading {os.path.basename(file_path)}...",
            ) as progress:
                def progress_callback(monitor):
                    progress.update(monitor.bytes_read - progress.n)

                # Detect MIME type for proper content handling
                content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
                encoder = MultipartEncoder(
                    fields={
                        "file": (os.path.basename(file_path), f, content_type),
                    }
                )
                monitor = MultipartEncoderMonitor(encoder, progress_callback)
                headers = {
                    "Content-Type": monitor.content_type,
                    "Authorization": auth_header
                }

                response = requests.post('https://pixeldrain.com/api/file', data=monitor, headers=headers)
        
        if response.status_code == 200 or response.status_code == 201:
            json_response = response.json()
            if json_response['success']:
                file_id = json_response['id']
                logger.info(f"Upload completed: {os.path.basename(file_path)}")
                return f"https://pixeldrain.com/u/{file_id}"
            else:
                logger.error(f"Upload failed: {json_response.get('message', 'Unknown error')}")
        else:
            logger.error(f"Upload failed: HTTP {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Error uploading to pixeldrain: {e}")
    return None


def download_from_pixeldrain(file_id: str, download_folder: str, force_download: bool = False) -> Optional[str]:
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
        logger.info(f"Getting file info for {file_id}")
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
            
        logger.info(f"Downloading file {filename} from pixeldrain")
        
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code == 200:
            total_size = int(response.headers.get('content-length', 0))
            os.makedirs(download_folder, exist_ok=True)
            
            # Download with progress bar
            with open(save_path, 'wb') as f:
                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=f"Downloading {filename}...",
                ) as progress:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # Filter out keep-alive chunks
                            f.write(chunk)
                            progress.update(len(chunk))
            
            logger.info(f"Download completed: {save_path}")
            return save_path
            
        elif response.status_code == 404:
            try:
                json_response = response.json()
                logger.error(f"File not found: {json_response.get('message', 'The file could not be found')}")
            except:
                logger.error("File not found")
            return None
            
        elif response.status_code == 403:
            try:
                json_response = response.json()
                error_value = json_response.get('value', '')
                message = json_response.get('message', 'Access forbidden')
                
                if 'rate_limited_captcha_required' in error_value:
                    logger.error(f"Rate limited: {message}")
                    logger.info(f"Please visit https://pixeldrain.com/u/{file_id} to complete captcha")
                elif 'virus_detected_captcha_required' in error_value:
                    logger.error(f"Virus detected: {message}")
                    logger.info(f"Please visit https://pixeldrain.com/u/{file_id} to complete captcha")
                else:
                    logger.error(f"Access forbidden: {message}")
            except:
                logger.error("Access forbidden")
            return None
            
        else:
            logger.error(f"Download failed: HTTP {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error downloading from pixeldrain: {e}")
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
        
        response = requests.get('https://pixeldrain.com/api/user/files', headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Successfully retrieved stats for {len(data.get('files', []))} files")
            return data
        else:
            logger.error(f"Failed to get stats: HTTP {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting stats from pixeldrain: {e}")
        return None
    

def print_stats_pixeldrain() -> None:
    """Print account statistics from pixeldrain.com."""
    stats = get_stats_pixeldrain()
    if stats and 'files' in stats:
        files = stats['files']
        logger.info(f"Found {len(files)} files in account")
        
        # Calculate some basic statistics
        total_size = sum(file.get('size', 0) for file in files)
        total_views = sum(file.get('views', 0) for file in files)
        total_downloads = sum(file.get('downloads', 0) for file in files)
        total_bandwidth = sum(file.get('bandwidth_used', 0) for file in files)

        logger.info(f"Total size: {total_size / (1024**3):.2f} GB")
        logger.info(f"Total views: {total_views:,}")
        logger.info(f"Total downloads: {total_downloads:,}")
        logger.info(f"Total bandwidth used: {total_bandwidth / (1024**3):.2f} GB")

        # Show top 5 most downloaded files
        top_downloads = sorted(files, key=lambda x: x.get('downloads', 0), reverse=True)[:5]
        logger.info("\nTop 5 most downloaded files:")
        for i, file in enumerate(top_downloads, 1):
            logger.info(f"{i}. {file.get('name', 'Unknown')} - {file.get('downloads', 0)} downloads")
    else:
        logger.error("Failed to get stats")


def get_file_info_pixeldrain(file_ids: Union[str, List[str]]) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
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
            logger.info(f"Fetching info for {len(file_ids)} files from pixeldrain")
        else:
            ids_str = file_ids
            logger.info(f"Fetching info for file {file_ids} from pixeldrain")
            
        auth_header = f"Basic {b64encode(f':{PIXELDRAIN_API_KEY}'.encode()).decode()}"
        headers = {"Authorization": auth_header}
        
        response = requests.get(f'https://pixeldrain.com/api/file/{ids_str}/info', headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            logger.info("Successfully retrieved file info")
            return data
        elif response.status_code == 404:
            json_response = response.json()
            logger.error(f"File not found: {json_response.get('value', 'Unknown error')}")
            return None
        else:
            logger.error(f"Failed to get file info: HTTP {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting file info from pixeldrain: {e}")
        return None
    

def print_file_info_pixeldrain(file_ids: Union[str, List[str]]) -> None:
    """Print information about one or more files from pixeldrain.com."""
    file_info = get_file_info_pixeldrain(file_ids)
    if file_info:
        logger.info(f"File name: {file_info.get('name', 'Unknown')}")
        logger.info(f"File size: {display_file_size(file_info.get('size', 0))}")
        logger.info(f"Views: {file_info.get('views', 0):,}")
        logger.info(f"Downloads: {file_info.get('downloads', 0):,}")
        logger.info(f"Upload date: {file_info.get('date_upload', 'Unknown')}")
        # logger.info(f"Last view: {file_info.get('date_last_view', 'Unknown')}")
        # logger.info(f"MIME type: {file_info.get('mime_type', 'Unknown')}")
        # logger.info(f"Can edit: {file_info.get('can_edit', False)}")


def reupload_pixeldrain(file_ids: Union[str, List[str]], download_folder: str, force_download: bool = False) -> Optional[str]:
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
    elif "pixeldrain.com/f/" in input_str:
        return input_str.split("pixeldrain.com/f/")[-1]
    elif "href.li/?" in input_str:
        return parse_file_id(input_str.split("href.li/?")[-1])
    return input_str


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="CLI for pixeldrain.com - Upload, download, and manage files")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload a file to pixeldrain')
    upload_parser.add_argument('file_path', help='Path to the file to upload')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download a file from pixeldrain')
    download_parser.add_argument('file_id', help='File ID or pixeldrain URL')
    download_parser.add_argument('-d', '--dir', default='/tmp', help='Download directory (default: /tmp)')
    download_parser.add_argument('-f', '--force', action='store_true', help='Force download (?download parameter)')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Get file information')
    info_parser.add_argument('file_id', help='File ID or pixeldrain URL')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Display account statistics')
    
    # Reupload command
    reupload_parser = subparsers.add_parser('reupload', help='Re-download and re-upload a file')
    reupload_parser.add_argument('file_id', help='File ID or pixeldrain URL')
    reupload_parser.add_argument('-d', '--dir', default='/tmp', help='Temporary directory (default: /tmp)')
    reupload_parser.add_argument('-f', '--force', action='store_true', help='Force download')
    
    args = parser.parse_args()
    
    # Check for API key for commands that need it
    if args.command in ['upload', 'stats', 'info', 'reupload'] and not PIXELDRAIN_API_KEY:
        logger.error("PIXELDRAIN_API_KEY is required for this command. Set it in your environment variables or in a .env file")
        sys.exit(1)
    
    if args.command == 'upload':
        if not os.path.isfile(args.file_path):
            logger.error(f"File not found: {args.file_path}")
            sys.exit(1)
        
        url = upload_to_pixeldrain(args.file_path)
        if url:
            print(f"File uploaded successfully: {url}")
        else:
            logger.error("Upload failed")
            sys.exit(1)
    
    elif args.command == 'download':
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
    
    elif args.command == 'info':
        file_id = parse_file_id(args.file_id)
        print_file_info_pixeldrain(file_id)
    
    elif args.command == 'stats':
        print_stats_pixeldrain()
    
    elif args.command == 'reupload':
        file_id = parse_file_id(args.file_id)
        url = reupload_pixeldrain(file_id, args.dir, args.force)
        if url:
            print(f"File re-uploaded successfully: {url}")
        else:
            logger.error("Re-upload failed")
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()