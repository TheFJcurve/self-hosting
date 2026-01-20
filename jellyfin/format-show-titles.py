#!/usr/bin/env python3
"""
Jellyfin Episode Renamer
Fetches official episode names from AniList (anime) or TMDB (TV shows) and renames files accordingly
"""

import os
import re
import time
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests")
    sys.exit(1)

# API Configuration
TMDB_API_KEY = "6f17dd6d6cf3eeb6fc97ce13cfbfb580z"  # Get free API key from https://www.themoviedb.org/settings/api
TMDB_BASE_URL = "https://api.themoviedb.org/3"
ANILIST_API_URL = "https://graphql.anilist.co"

# ============================================================================
# AniList API Functions
# ============================================================================

def anilist_request(query: str, variables: dict) -> Optional[dict]:
    """Make a rate-limited request to AniList API"""
    global _last_anilist_request
    
    # Enforce minimum delay between requests
    current_time = time.time()
    time_since_last = current_time - _last_anilist_request
    if time_since_last < ANILIST_MIN_DELAY:
        sleep_time = ANILIST_MIN_DELAY - time_since_last
        time.sleep(sleep_time)
    
    # Make request
    response = requests.post(
        ANILIST_API_URL,
        json={'query': query, 'variables': variables}
    )
    _last_anilist_request = time.time()
    
    # Check for rate limiting
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 60))
        print(f"  ⚠️  Rate limited by AniList. Waiting {retry_after} seconds...")
        time.sleep(retry_after + 1)
        
        # Retry the request
        response = requests.post(
            ANILIST_API_URL,
            json={'query': query, 'variables': variables}
        )
        _last_anilist_request = time.time()
    
    if response.status_code == 200:
        return response.json()
    
    return None

def search_anime_anilist(anime_name: str) -> Optional[int]:
    """Search for an anime on AniList and return its ID"""
    query = '''
    query ($search: String) {
        Media(search: $search, type: ANIME) {
            id
            title {
                romaji
                english
                native
            }
        }
    }
    '''
    
    variables = {'search': anime_name}
    data = anilist_request(query, variables)
    
    if data and data.get('data', {}).get('Media'):
        return data['data']['Media']['id']
    return None

def get_episode_name_anilist(anime_id: int, episode: int) -> Optional[str]:
    """Fetch episode name from AniList using TVDB-style episode mapping"""
    # First, try to get the main anime's info
    query = '''
    query ($id: Int) {
        Media(id: $id, type: ANIME) {
            episodes
            streamingEpisodes {
                title
            }
            relations {
                edges {
                    relationType
                    node {
                        id
                        type
                        format
                        episodes
                        startDate { year }
                        streamingEpisodes {
                            title
                        }
                        title {
                            romaji
                        }
                    }
                }
            }
        }
    }
    '''
    
    variables = {'id': anime_id}
    data = anilist_request(query, variables)
    
    if not data:
        return None
    
    media = data.get('data', {}).get('Media', {})
    
    # Build a list of all seasons with their episodes
    seasons = []
    
    # Add main season
    main_episodes = media.get('streamingEpisodes', [])
    if main_episodes:
        seasons.append({
            'id': anime_id,
            'episodes': main_episodes,
            'start_ep': 1
        })
    
    # Find all sequels and add them in order
    relations = media.get('relations', {}).get('edges', [])
    sequels = []
    
    for edge in relations:
        relation_type = edge.get('relationType', '')
        node = edge.get('node', {})
        
        if (relation_type == 'SEQUEL' and 
            node.get('type') == 'ANIME' and 
            node.get('format') in ['TV', 'ONA']):
            
            sequel_eps = node.get('streamingEpisodes', [])
            year = node.get('startDate', {}).get('year', 9999)
            sequels.append({
                'id': node['id'],
                'episodes': sequel_eps,
                'year': year,
                'title': node.get('title', {}).get('romaji', '')
            })
    
    # Sort sequels by year
    sequels.sort(key=lambda x: x['year'])
    
    # Calculate episode ranges for each season
    current_ep = 1
    if main_episodes:
        current_ep += len(main_episodes)
    
    for sequel in sequels:
        sequel['start_ep'] = current_ep
        seasons.append(sequel)
        current_ep += len(sequel['episodes'])
    
    # Find the right episode
    for season in seasons:
        start = season['start_ep']
        end = start + len(season['episodes']) - 1
        
        if start <= episode <= end:
            local_ep = episode - start
            if local_ep < len(season['episodes']):
                title = season['episodes'][local_ep].get('title', '')
                # Clean up title
                title = re.sub(r'^\d+\.\s*', '', title)
                title = re.sub(r'^Episode\s+\d+\s*-\s*', '', title)
                return title if title else None
    
    return None

def calculate_absolute_episode(season: int, episode: int, episode_counts: Dict[int, int]) -> int:
    """Calculate absolute episode number from season/episode"""
    absolute = episode
    for s in range(1, season):
        absolute += episode_counts.get(s, 0)
    return absolute

def detect_episode_numbering(show_path: Path) -> Tuple[bool, Dict[int, int]]:
    """
    Detect if episodes use absolute numbering or season-based numbering.
    Returns (is_absolute, episode_counts_per_season)
    """
    episode_counts = {}
    
    for season_dir in sorted(show_path.iterdir()):
        if not season_dir.is_dir():
            continue
        
        season_match = re.search(r'Season\s*(\d+)', season_dir.name, re.IGNORECASE)
        if not season_match:
            continue
        
        season_num = int(season_match.group(1))
        mkv_files = list(season_dir.glob("*.mkv"))
        
        if not mkv_files:
            continue
        
        # Get episode numbers from this season
        episode_nums = []
        for mkv_file in mkv_files:
            ep_num = extract_episode_number(mkv_file.name)
            if ep_num:
                episode_nums.append(ep_num)
        
        if episode_nums:
            min_ep = min(episode_nums)
            max_ep = max(episode_nums)
            count = len(episode_nums)
            episode_counts[season_num] = count
            
            # If season 2+ starts with episode number > 1, likely absolute numbering
            if season_num > 1 and min_ep > 1:
                return True, episode_counts
    
    return False, episode_counts

# ============================================================================
# TMDB API Functions
# ============================================================================

def search_show_tmdb(show_name: str) -> Optional[Tuple[int, str]]:
    """Search for a TV show on TMDB and return its ID and external IMDB ID"""
    url = f"{TMDB_BASE_URL}/search/tv"
    params = {
        "api_key": TMDB_API_KEY,
        "query": show_name
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            show_id = results[0]["id"]
            # Get external IDs including IMDB
            ext_url = f"{TMDB_BASE_URL}/tv/{show_id}/external_ids"
            ext_response = requests.get(ext_url, params={"api_key": TMDB_API_KEY})
            imdb_id = None
            if ext_response.status_code == 200:
                imdb_id = ext_response.json().get("imdb_id")
            return show_id, imdb_id
    return None

def get_episode_name_tmdb(show_id: int, season: int, episode: int) -> Optional[str]:
    """Fetch official episode name from TMDB"""
    url = f"{TMDB_BASE_URL}/tv/{show_id}/season/{season}/episode/{episode}"
    params = {"api_key": TMDB_API_KEY}
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get("name", "")
    return None

# ============================================================================
# Helper Functions
# ============================================================================

def extract_episode_number(filename: str) -> Optional[int]:
    """Extract episode number from filename"""
    # Match patterns like "01", "02", etc.
    patterns = [
        r'\s+(\d{2})\s+',  # Space-separated: "Kyojin 01 (1080p"
        r'[Ee](\d{2})',     # E01, e01
        r'Episode\s*(\d{2})', # Episode 01
        r'-\s*(\d{2})\s*-', # - 01 -
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return int(match.group(1))
    return None

def sanitize_filename(name: str) -> str:
    """Remove or replace invalid filename characters"""
    # Replace invalid characters with underscore
    invalid_chars = r'[<>:"/\\|?*]'
    name = re.sub(invalid_chars, '_', name)
    # Remove trailing dots and spaces
    name = name.rstrip('. ')
    return name

def find_associated_files(mkv_path: Path) -> List[Path]:
    """Find all files associated with an mkv file (nfo, jpg, etc.)"""
    base_name = mkv_path.stem
    parent = mkv_path.parent
    associated = []
    
    # Find files with same base name but different extensions
    for ext in ['.nfo', '-thumb.jpg', '.jpg']:
        associated_file = parent / f"{base_name}{ext}"
        if associated_file.exists():
            associated.append(associated_file)
    
    return associated

def is_anime(show_name: str) -> bool:
    """Determine if a show is an anime based on its name or prompt user"""
    # Try to detect common anime naming patterns
    anime_indicators = [
        'shingeki', 'no', 'kyojin', 'naruto', 'one piece', 'dragon ball',
        'attack on titan', 'demon slayer', 'kimetsu', 'jujutsu', 'bleach'
    ]
    
    show_lower = show_name.lower()
    for indicator in anime_indicators:
        if indicator in show_lower:
            return True
    
    # If unsure, ask the user
    while True:
        response = input(f"\nIs '{show_name}' an anime? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        print("Please answer 'y' or 'n'")

# ============================================================================
# Main Renaming Logic
# ============================================================================

def rename_episode_files(
    show_name: str,
    shows_dir: Path,
    dry_run: bool = True,
    force_anime: bool = False,
    force_tv: bool = False
) -> None:
    """Rename episode files in a show directory"""
    
    # Find show directory
    show_path = shows_dir / show_name
    if not show_path.exists():
        print(f"Error: Show directory not found: {show_path}")
        return
    
    # Determine if anime or regular TV show
    if force_anime:
        use_anilist = True
    elif force_tv:
        use_anilist = False
    else:
        use_anilist = is_anime(show_name)
    
    # Search for show
    if use_anilist:
        print(f"Searching for '{show_name}' on AniList...")
        show_id = search_anime_anilist(show_name)
        if not show_id:
            print(f"Error: Could not find anime on AniList")
            return
        print(f"Found anime ID: {show_id}")
        imdb_id = None
        
        # Detect episode numbering scheme
        is_absolute, episode_counts = detect_episode_numbering(show_path)
        if is_absolute:
            print(f"Detected absolute episode numbering across seasons")
        else:
            print(f"Detected season-based episode numbering")
    else:
        print(f"Searching for '{show_name}' on TMDB...")
        result = search_show_tmdb(show_name)
        if not result:
            print(f"Error: Could not find show on TMDB")
            return
        show_id, imdb_id = result
        print(f"Found show ID: {show_id}")
        if imdb_id:
            print(f"IMDB ID: {imdb_id}")
        is_absolute = False
        episode_counts = {}
    
    # Process each season directory
    for season_dir in sorted(show_path.iterdir()):
        if not season_dir.is_dir():
            continue
        
        # Extract season number from directory name
        season_match = re.search(r'Season\s*(\d+)', season_dir.name, re.IGNORECASE)
        if not season_match:
            continue
        
        season_num = int(season_match.group(1))
        print(f"\nProcessing Season {season_num}...")
        
        # Find all mkv files
        mkv_files = sorted(season_dir.glob("*.mkv"))
        
        for mkv_file in mkv_files:
            # Extract episode number
            episode_num = extract_episode_number(mkv_file.name)
            if not episode_num:
                print(f"  ⚠️  Could not extract episode number from: {mkv_file.name}")
                continue
            
            # Get official episode name
            if use_anilist:
                # For AniList with absolute numbering, use the episode number directly
                # For season-based numbering, calculate absolute episode number
                if is_absolute:
                    absolute_ep = episode_num
                else:
                    absolute_ep = calculate_absolute_episode(season_num, episode_num, episode_counts)
                
                episode_name = get_episode_name_anilist(show_id, absolute_ep)
            else:
                episode_name = get_episode_name_tmdb(show_id, season_num, episode_num)
            
            if not episode_name:
                print(f"  ⚠️  Could not fetch episode name for S{season_num:02d}E{episode_num:02d}")
                continue
            
            # Create new filename
            sanitized_name = sanitize_filename(episode_name)
            new_base = f"{show_name} - S{season_num:02d}E{episode_num:02d} - {sanitized_name}"
            new_mkv_name = f"{new_base}.mkv"
            new_mkv_path = season_dir / new_mkv_name
            
            # Check if already renamed
            if mkv_file.name == new_mkv_name:
                print(f"  ✓  Already renamed: {new_mkv_name}")
                continue
            
            # Find associated files
            associated_files = find_associated_files(mkv_file)
            
            # Perform rename
            if dry_run:
                print(f"  [DRY RUN] Would rename:")
                print(f"    {mkv_file.name}")
                print(f"    -> {new_mkv_name}")
                for assoc in associated_files:
                    new_assoc_name = new_base + assoc.suffix
                    print(f"    {assoc.name} -> {new_assoc_name}")
            else:
                try:
                    # Rename mkv file
                    mkv_file.rename(new_mkv_path)
                    print(f"  ✓  Renamed: {new_mkv_name}")
                    
                    # Rename associated files
                    for assoc in associated_files:
                        new_assoc_path = season_dir / f"{new_base}{assoc.suffix}"
                        assoc.rename(new_assoc_path)
                        print(f"    ✓  {assoc.suffix} renamed")
                        
                except Exception as e:
                    print(f"  ❌  Error renaming {mkv_file.name}: {e}")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Rename Jellyfin episode files with official names from AniList or TMDB"
    )
    parser.add_argument(
        "show_name",
        help="Name of the show (must match directory name)"
    )
    parser.add_argument(
        "--shows-dir",
        type=Path,
        default=Path.cwd(),
        help="Path to shows directory (default: current directory)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually rename files (default is dry-run)"
    )
    parser.add_argument(
        "--anime",
        action="store_true",
        help="Force using AniList API (for anime)"
    )
    parser.add_argument(
        "--tv",
        action="store_true",
        help="Force using TMDB API (for regular TV shows)"
    )
    
    args = parser.parse_args()
    
    # Check API key for TMDB if not forced to anime
    if not args.anime and TMDB_API_KEY == "YOUR_TMDB_API_KEY_HERE":
        print("Error: Please set your TMDB API key in the script")
        print("Get a free API key from: https://www.themoviedb.org/settings/api")
        print("Or use --anime flag to use AniList instead")
        sys.exit(1)
    
    print("=" * 60)
    print("Jellyfin Episode Renamer")
    print("=" * 60)
    
    if not args.execute:
        print("\n⚠️  DRY RUN MODE - No files will be modified")
        print("Use --execute to actually rename files\n")
    
    rename_episode_files(
        args.show_name,
        args.shows_dir,
        dry_run=not args.execute,
        force_anime=args.anime,
        force_tv=args.tv
    )
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)

if __name__ == "__main__":
    main()