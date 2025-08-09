import streamlit as st
from yt_dlp import YoutubeDL
import os
import json
import time
from datetime import datetime
import threading
import queue
import zipfile
from pathlib import Path
import shutil

# =====================
# CONFIGURATION
# =====================
DOWNLOADS_DIR = "downloads"
PROGRESS_DIR = "progress"
METADATA_FILE = os.path.join(PROGRESS_DIR, "download_history.json")

# Create necessary directories
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(PROGRESS_DIR, exist_ok=True)

# =====================
# HELPER FUNCTIONS
# =====================
def save_download_history(video_info):
    """Save download history to JSON file"""
    history = load_download_history()
    download_record = {
        "title": video_info.get("title", "Unknown"),
        "url": video_info.get("webpage_url", ""),
        "duration": video_info.get("duration", 0),
        "uploader": video_info.get("uploader", "Unknown"),
        "download_date": datetime.now().isoformat(),
        "file_size": video_info.get("filesize", 0),
        "format": video_info.get("ext", "unknown")
    }
    history.append(download_record)
    
    with open(METADATA_FILE, "w") as f:
        json.dump(history, f, indent=2)

def load_download_history():
    """Load download history from JSON file"""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return []

def format_duration(seconds):
    """Format duration from seconds to readable format"""
    if not seconds:
        return "Unknown"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes}:{seconds}"
    return f"{minutes}:{seconds}"

def format_file_size(size_bytes):
    """Format file size to human readable format"""
    if not size_bytes or size_bytes == 0:
        return "Unknown"
    
    try:
        size_bytes = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    except (ValueError, TypeError):
        return "Unknown"

def get_video_info(url):
    """Get video information without downloading"""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

# =====================
# ADVANCED DOWNLOAD FUNCTION
# =====================
class DownloadProgress:
    def __init__(self):
        self.progress_data = {}
        
    def create_progress_hook(self, video_id, container):
        def progress_hook(d):
            filename = os.path.basename(d.get('filename', 'Unknown'))
            
            if d['status'] == 'downloading':
                percent_str = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', '0KB/s').strip()
                eta = d.get('_eta_str', 'Unknown').strip()
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes', d.get('total_bytes_estimate', 0))
                
                # Update progress bar
                if total and total > 0:
                    progress_percent = min(downloaded / total, 1.0)
                    container.progress(progress_percent, text=f"📥 {filename}")
                
                # Update status
                status_text = f"**Downloading:** {filename}\n"
                status_text += f"📊 Progress: {percent_str} | 🚀 Speed: {speed} | ⏱️ ETA: {eta}"
                container.info(status_text)
                
            elif d['status'] == 'finished':
                container.success(f"✅ **Download Complete:** {filename}")
                
        return progress_hook

def download_video_advanced(url, audio_only=False, quality='best', progress_container=None):
    """Advanced download function with better progress tracking"""
    video_id = url.split('v=')[-1].split('&')[0] if 'v=' in url else str(hash(url))
    
    # Get video info first
    try:
        video_info = get_video_info(url)
    except Exception as e:
        if progress_container:
            progress_container.error(f"❌ Error getting video info: {str(e)}")
        return False
    
    # Set up download options
    output_template = os.path.join(DOWNLOADS_DIR, "%(title)s.%(ext)s")
    
    if audio_only:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        if quality == 'best':
            format_selector = 'best[height<=1080]'
        elif quality == '720p':
            format_selector = 'best[height<=720]'
        elif quality == '480p':
            format_selector = 'best[height<=480]'
        else:
            format_selector = 'best'
            
        ydl_opts = {
            'format': format_selector,
            'outtmpl': output_template,
        }
    
    # Add progress hook if container provided
    if progress_container:
        progress_tracker = DownloadProgress()
        ydl_opts['progress_hooks'] = [progress_tracker.create_progress_hook(video_id, progress_container)]
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Save to history
        save_download_history(video_info)
        return True
        
    except Exception as e:
        if progress_container:
            progress_container.error(f"❌ Download failed: {str(e)}")
        return False

# =====================
# BATCH DOWNLOAD FUNCTION
# =====================
def download_multiple_videos(urls, audio_only=False, quality='best'):
    """Download multiple videos with progress tracking"""
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    
    successful_downloads = 0
    failed_downloads = 0
    
    for i, url in enumerate(urls, 1):
        with progress_placeholder.container():
            st.write(f"### Processing Video {i}/{len(urls)}")
            video_container = st.empty()
            
            if download_video_advanced(url, audio_only, quality, video_container):
                successful_downloads += 1
            else:
                failed_downloads += 1
    
    # Final summary
    status_placeholder.success(
        f"✅ Batch download complete!\n"
        f"✅ Successful: {successful_downloads} | ❌ Failed: {failed_downloads}"
    )

# =====================
# SEARCH FUNCTION
# =====================
def search_youtube_advanced(query, max_results=10, search_type="video"):
    """Advanced YouTube search with more options"""
    search_prefix = f"ytsearch{max_results}:"
    if search_type == "playlist":
        search_prefix = f"ytplaylist:"
        
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            if search_type == "playlist":
                result = ydl.extract_info(query, download=False)
                entries = result.get("entries", [])
            else:
                result = ydl.extract_info(f"{search_prefix}{query}", download=False)
                entries = result.get("entries", [])
            
            # Ensure each entry has a proper URL
            for entry in entries:
                if entry and entry.get('id'):
                    if not entry.get('url') or not entry['url'].startswith('http'):
                        entry['url'] = f"https://www.youtube.com/watch?v={entry['id']}"
                        
            return entries
    except Exception as e:
        st.error(f"Search error: {str(e)}")
        return []

def download_selected_videos(selected_videos, audio_only=False, quality='best'):
    """Download multiple selected videos from search results"""
    if not selected_videos:
        st.warning("⚠️ No videos selected for download")
        return
    
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    
    successful_downloads = 0
    failed_downloads = 0
    
    for i, video_data in enumerate(selected_videos, 1):
        with progress_placeholder.container():
            st.write(f"### Processing Video {i}/{len(selected_videos)}")
            st.write(f"**Title:** {video_data.get('title', 'Unknown')}")
            video_container = st.empty()
            
            video_url = video_data.get('url')
            if not video_url:
                video_url = f"https://www.youtube.com/watch?v={video_data.get('id', '')}"
            
            if download_video_advanced(video_url, audio_only, quality, video_container):
                successful_downloads += 1
            else:
                failed_downloads += 1
        
        # Small delay between downloads
        time.sleep(1)
    
    # Final summary
    status_placeholder.success(
        f"✅ Selected downloads complete!\n"
        f"✅ Successful: {successful_downloads} | ❌ Failed: {failed_downloads}"
    )

# =====================
# STREAMLIT UI
# =====================
st.set_page_config(
    page_title="🎬 Advanced YouTube Downloader", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
.download-card {
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 15px;
    margin: 10px 0;
    background-color: #f9f9f9;
}
.stats-container {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    padding: 20px;
    border-radius: 10px;
    color: white;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

# Sidebar for settings and stats
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Download quality settings
    st.subheader("🎥 Video Quality")
    quality_option = st.selectbox(
        "Select Quality",
        ["best", "720p", "480p"],
        help="Choose video quality (best will select highest available up to 1080p)"
    )
    
    # Audio settings
    st.subheader("🎵 Audio Options")
    audio_quality = st.selectbox("Audio Quality", ["192", "256", "320"])
    
    # Download statistics
    st.subheader("📊 Download Statistics")
    history = load_download_history()
    
    if history:
        total_downloads = len(history)
        total_duration = sum([h.get("duration", 0) for h in history])
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Downloads", total_downloads)
        with col2:
            st.metric("Total Duration", format_duration(total_duration))
    else:
        st.info("No downloads yet!")

# Main title with emoji
st.title("🎬 Advanced YouTube Downloader")
st.markdown("*Download YouTube videos and audio with advanced features and progress tracking*")

# Create tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📥 Quick Download", 
    "🔍 Search & Download", 
    "📋 Batch Download", 
    "📁 File Manager", 
    "📈 Download History"
])

# Tab 1: Quick Download
with tab1:
    st.subheader("🚀 Quick Download")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        quick_url = st.text_input("🔗 Enter YouTube URL:", placeholder="https://www.youtube.com/watch?v=...")
    with col2:
        audio_only_quick = st.checkbox("🎵 Audio Only", key="quick_audio")
    
    if st.button("⬇️ Download Now", type="primary"):
        if quick_url:
            progress_container = st.empty()
            
            # Show video info first
            try:
                with st.spinner("Getting video information..."):
                    video_info = get_video_info(quick_url)
                
                # Display video info
                col1, col2 = st.columns(2)
                with col1:
                    st.info(f"**Title:** {video_info.get('title', 'Unknown')}")
                    st.info(f"**Duration:** {format_duration(video_info.get('duration'))}")
                with col2:
                    st.info(f"**Uploader:** {video_info.get('uploader', 'Unknown')}")
                    try:
                        view_count = video_info.get('view_count', 0)
                        if view_count:
                            view_count = int(float(view_count))
                            st.info(f"**Views:** {view_count:,}")
                        else:
                            st.info(f"**Views:** Unknown")
                    except (ValueError, TypeError):
                        st.info(f"**Views:** {video_info.get('view_count', 'Unknown')}")
                
                # Start download
                success = download_video_advanced(
                    quick_url, 
                    audio_only_quick, 
                    quality_option, 
                    progress_container
                )
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
        else:
            st.warning("⚠️ Please enter a valid YouTube URL")

# Tab 2: Search & Download
with tab2:
    st.subheader("🔍 Search YouTube")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_query = st.text_input("🔎 Search term:", placeholder="Enter keywords...")
    with col2:
        max_results = st.slider("Max results", 1, 20, 10)
    with col3:
        search_type = st.selectbox("Type", ["video", "playlist"])
    
    # Initialize session state for selected videos
    if 'selected_videos' not in st.session_state:
        st.session_state.selected_videos = []
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    
    if st.button("🔍 Search"):
        if search_query:
            with st.spinner("Searching YouTube..."):
                videos = search_youtube_advanced(search_query, max_results, search_type)
            
            if not videos:
                st.info("🤷‍♂️ No videos found.")
                st.session_state.search_results = []
            else:
                st.success(f"✅ Found {len(videos)} results")
                st.session_state.search_results = videos
                st.session_state.selected_videos = []  # Reset selections
        else:
            st.warning("⚠️ Please enter a search term")
    
    # Display search results if available
    if st.session_state.search_results:
        st.divider()
        
        # Bulk download options
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.subheader("📋 Bulk Download Options")
        with col2:
            bulk_audio_only = st.checkbox("🎵 Audio Only", key="bulk_search_audio")
        with col3:
            bulk_quality = st.selectbox("Quality", ["best", "720p", "480p"], key="bulk_search_quality")
        
        # Select all / Deselect all buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Select All"):
                st.session_state.selected_videos = st.session_state.search_results.copy()
                st.rerun()
        with col2:
            if st.button("❌ Deselect All"):
                st.session_state.selected_videos = []
                st.rerun()
        with col3:
            selected_count = len(st.session_state.selected_videos)
            if selected_count > 0:
                if st.button(f"⬇️ Download Selected ({selected_count})", type="primary"):
                    download_selected_videos(st.session_state.selected_videos, bulk_audio_only, bulk_quality)
        
        st.divider()
        
        # Display individual results with selection
        for i, video in enumerate(st.session_state.search_results):
            video_id = video.get('id', f'video_{i}')
            is_selected = any(v.get('id') == video_id for v in st.session_state.selected_videos)
            
            with st.container():
                col1, col2, col3, col4 = st.columns([0.5, 1, 3, 1])
                
                with col1:
                    # Selection checkbox
                    selected = st.checkbox("", value=is_selected, key=f"select_{video_id}")
                    
                    # Update selection state
                    if selected and not is_selected:
                        st.session_state.selected_videos.append(video)
                    elif not selected and is_selected:
                        st.session_state.selected_videos = [
                            v for v in st.session_state.selected_videos 
                            if v.get('id') != video_id
                        ]
                
                with col2:
                    # Display thumbnail if available
                    if 'thumbnails' in video and video['thumbnails']:
                        st.image(video['thumbnails'][0]['url'], width=100)
                
                with col3:
                    st.write(f"**{video.get('title', 'No title')}**")
                    if 'duration' in video:
                        st.caption(f"⏱️ Duration: {format_duration(video.get('duration'))}")
                    if 'uploader' in video:
                        st.caption(f"👤 Uploader: {video.get('uploader')}")
                    if 'view_count' in video and video.get('view_count'):
                        try:
                            view_count = int(float(video.get('view_count', 0)))
                            st.caption(f"👁️ Views: {view_count:,}")
                        except (ValueError, TypeError):
                            st.caption(f"👁️ Views: {video.get('view_count', 'Unknown')}")
                
                with col4:
                    # Individual download button
                    individual_audio = st.checkbox("🎵", key=f"audio_{video_id}", help="Audio only")
                    
                    if st.button("⬇️", key=f"download_{video_id}", help="Download this video"):
                        video_url = video.get('url')
                        if not video_url:
                            video_url = f"https://www.youtube.com/watch?v={video.get('id', '')}"
                        
                        progress_container = st.empty()
                        with progress_container.container():
                            st.info(f"📥 Starting download: {video.get('title', 'Unknown')}")
                            download_video_advanced(
                                video_url, 
                                individual_audio, 
                                quality_option, 
                                progress_container
                            )
                
                st.divider()
        
        # Show selection summary at bottom
        if st.session_state.selected_videos:
            st.info(f"📋 Selected {len(st.session_state.selected_videos)} videos for bulk download")

# Tab 3: Batch Download
with tab3:
    st.subheader("📋 Batch Download")
    st.markdown("*Download multiple videos at once*")
    
    urls_input = st.text_area(
        "🔗 Enter YouTube URLs (one per line):",
        height=150,
        placeholder="https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=..."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        batch_audio_only = st.checkbox("🎵 Audio Only", key="batch_audio")
    with col2:
        batch_quality = st.selectbox("Quality", ["best", "720p", "480p"], key="batch_quality")
    
    if st.button("⬇️ Download All", type="primary"):
        urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
        if urls:
            st.info(f"🚀 Starting batch download of {len(urls)} videos...")
            download_multiple_videos(urls, batch_audio_only, batch_quality)
        else:
            st.warning("⚠️ Please enter at least one URL")

# Tab 4: File Manager
with tab4:
    st.subheader("📁 Downloaded Files")
    
    if os.path.exists(DOWNLOADS_DIR):
        files = [f for f in os.listdir(DOWNLOADS_DIR) if os.path.isfile(os.path.join(DOWNLOADS_DIR, f))]
        
        if files:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📁 Total Files", len(files))
            with col2:
                total_size = sum(os.path.getsize(os.path.join(DOWNLOADS_DIR, f)) for f in files)
                st.metric("💾 Total Size", format_file_size(total_size))
            with col3:
                if st.button("📦 Create ZIP"):
                    zip_path = os.path.join(DOWNLOADS_DIR, f"downloads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for file in files:
                            if not file.endswith('.zip'):
                                zipf.write(os.path.join(DOWNLOADS_DIR, file), file)
                    st.success(f"✅ ZIP created: {os.path.basename(zip_path)}")
            
            st.divider()
            
            # File list with actions
            for file in files:
                file_path = os.path.join(DOWNLOADS_DIR, file)
                file_size = os.path.getsize(file_path)
                
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"📄 **{file}**")
                    st.caption(f"💾 Size: {format_file_size(file_size)}")
                with col2:
                    if st.button("🗑️ Delete", key=f"del_{file}"):
                        os.remove(file_path)
                        st.rerun()
                with col3:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            "⬇️ Download",
                            f,
                            file_name=file,
                            key=f"dl_{file}"
                        )
        else:
            st.info("📂 No files downloaded yet")
    else:
        st.info("📂 Downloads folder not found")

# Tab 5: Download History
with tab5:
    st.subheader("📈 Download History")
    
    history = load_download_history()
    
    if history:
        # Statistics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 Total Downloads", len(history))
        with col2:
            total_duration = sum([h.get("duration", 0) for h in history])
            st.metric("⏱️ Total Duration", format_duration(total_duration))
        with col3:
            unique_uploaders = len(set([h.get("uploader", "Unknown") for h in history]))
            st.metric("👥 Unique Uploaders", unique_uploaders)
        with col4:
            if st.button("🗑️ Clear History"):
                with open(METADATA_FILE, "w") as f:
                    json.dump([], f)
                st.rerun()
        
        st.divider()
        
        # History table
        for i, record in enumerate(reversed(history[-20:])):  # Show last 20
            with st.expander(f"📹 {record.get('title', 'Unknown')} - {record.get('download_date', '')[:10]}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**👤 Uploader:** {record.get('uploader', 'Unknown')}")
                    st.write(f"**⏱️ Duration:** {format_duration(record.get('duration', 0))}")
                with col2:
                    st.write(f"**📅 Downloaded:** {record.get('download_date', 'Unknown')[:19]}")
                    st.write(f"**🔗 URL:** {record.get('url', 'Unknown')[:50]}...")
    else:
        st.info("📊 No download history available")

# Footer
st.divider()
st.markdown("---")
st.markdown("**🎬 Advanced YouTube Downloader** | Built with ❤️ using Streamlit")
st.caption("⚠️ Please respect copyright laws and YouTube's Terms of Service when downloading content.")