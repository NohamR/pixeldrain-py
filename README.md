# Pixeldrain CLI

A comprehensive command-line interface for interacting with [pixeldrain.com](https://pixeldrain.com), allowing you to upload, download, and manage files through the pixeldrain API.

## Features

- 📤 **Upload files** with real-time progress bar
- 📥 **Download files** with progress tracking
- 📊 **Get file information** and statistics
- 🔄 **Reupload files** (download + upload in one command)
- 🔑 **Authentication support** for pixeldrain accounts
- 🌐 **Anonymous downloads** when no API key is provided
- 🔗 **URL parsing** - automatically extracts file IDs from pixeldrain URLs
- ⚡ **Error handling** with detailed messages for rate limits, captchas, etc.

## Installation

1. Clone this repository:
```bash
git clone https://github.com/NohamR/pixeldrain-py.git
cd pixeldrain-py
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Set up your pixeldrain API key:
```bash
export PIXELDRAIN_API_KEY="your_api_key_here"
```

Or create a `.env` file:
```
PIXELDRAIN_API_KEY=your_api_key_here
```

## Usage

### Upload a file
```bash
python pixeldrain.py upload /path/to/your/file.pdf
```

### Download a file
```bash
# Using file ID
python pixeldrain.py download abc123def456

# Using full URL
python pixeldrain.py download https://pixeldrain.com/u/abc123def456

# Download to specific directory
python pixeldrain.py download abc123def456 --dir ~/Downloads

# Force download (bypass browser preview)
python pixeldrain.py download abc123def456 --force
```

### Get file information
```bash
python pixeldrain.py info abc123def456
```

### View account statistics
```bash
python pixeldrain.py stats
```

### Reupload a file
```bash
# Download and re-upload in one command
python pixeldrain.py reupload abc123def456
```

## Command Reference

### `upload`
Upload a file to pixeldrain.

**Arguments:**
- `file_path` - Path to the file to upload

**Example:**
```bash
python pixeldrain.py upload document.pdf
```

### `download`
Download a file from pixeldrain.

**Arguments:**
- `file_id` - File ID or pixeldrain URL

**Options:**
- `-d, --dir` - Download directory (default: /tmp)
- `-f, --force` - Force download with ?download parameter

**Example:**
```bash
python pixeldrain.py download abc123 --dir ~/Downloads --force
```

### `info`
Get information about a file.

**Arguments:**
- `file_id` - File ID or pixeldrain URL

**Example:**
```bash
python pixeldrain.py info abc123
```

### `stats`
Display account statistics (requires API key).

**Example:**
```bash
python pixeldrain.py stats
```

### `reupload`
Download and re-upload a file.

**Arguments:**
- `file_id` - File ID or pixeldrain URL

**Options:**
- `-d, --dir` - Temporary directory (default: /tmp)
- `-f, --force` - Force download

**Example:**
```bash
python pixeldrain.py reupload abc123 --dir /tmp
```

## API Key

To upload files or access account features, you need a pixeldrain API key:

1. Go to [pixeldrain.com](https://pixeldrain.com)
2. Create an account or log in
3. Go to your account settings
4. Generate an API key
5. Set it as an environment variable or in a `.env` file

## Error Handling

The CLI handles common pixeldrain errors gracefully:

- **Rate limiting**: Shows captcha URL when rate limited
- **Virus detection**: Provides instructions for manual verification
- **File not found**: Clear error messages for missing files
- **Authentication**: Warnings for missing API keys