#!/usr/bin/env python3

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import argparse
import shutil
from datetime import datetime
import time
import musicbrainzngs

musicbrainzngs.set_useragent(
    "JellyfinMetadataUpdater",
    "1.0",
    "https://github.com/yourusername/jellyfin-updater"
)

MUSICBRAINZ_DELAY = 1.0


def parse_artists(artist_string):
    if not artist_string:
        return []
    
    patterns = [
        r'\s+feat\.?\s+',
        r'\s+ft\.?\s+',
        r'\s+featuring\s+',
        r'\s+Feat\.?\s+',
        r'\s+Ft\.?\s+',
        r'\s+Featuring\s+',
    ]
    
    result = artist_string
    for pattern in patterns:
        result = re.sub(pattern, ', ', result, flags=re.IGNORECASE)

    result = re.sub(r'\s+&\s+', ', ', result)
    result = re.sub(r'\s+and\s+', ', ', result, flags=re.IGNORECASE)
    
    artists = [a.strip() for a in result.split(',')]
    artists = [a for a in artists if a]
    
    return artists


def format_artists_to_semicolon(artists_list):
    return ';'.join(artists_list)


def get_musicbrainz_id_from_nfo(root):
    mb_id = root.find('.//musicbrainzreleasegroupid')
    if mb_id is not None and mb_id.text:
        return mb_id.text.strip()
    mb_id = root.find('.//musicbrainzalbumid')
    if mb_id is not None and mb_id.text:
        return mb_id.text.strip()
    
    return None


def search_album_on_musicbrainz(album_name, artist_name):
    try:
        time.sleep(MUSICBRAINZ_DELAY)
        
        result = musicbrainzngs.search_release_groups(
            releasegroup=album_name,
            artist=artist_name,
            limit=1
        )
        
        if result['release-group-list']:
            return result['release-group-list'][0]['id']
        
    except Exception as e:
        print(f"  Warning: MusicBrainz search error: {e}")
    
    return None


def get_genres_from_musicbrainz(mb_id, is_release_group=True):
    try:
        time.sleep(MUSICBRAINZ_DELAY)
        
        if is_release_group:
            result = musicbrainzngs.get_release_group_by_id(
                mb_id,
                includes=['tags']
            )
            data = result.get('release-group', {})
        else:
            result = musicbrainzngs.get_release_by_id(
                mb_id,
                includes=['tags']
            )
            data = result.get('release', {})
        
        genres = []
        
        tag_list = data.get('tag-list', [])
        for tag in tag_list:
            count = int(tag.get('count', 0))
            if count >= 1:  # At least 1 vote
                tag_name = tag['name']
                tag_name = ' '.join(word.capitalize() for word in tag_name.split())
                genres.append(tag_name)
        return genres if genres else []
    except musicbrainzngs.NetworkError:
        print("  Warning: Network error connecting to MusicBrainz")
    except musicbrainzngs.ResponseError as e:
        print(f"  Warning: MusicBrainz API error: {e}")
    except Exception as e:
        print(f"  Warning: Error fetching genres: {e}")
    return []


def update_nfo_file(nfo_path, dry_run=False, backup=True, fetch_genres=False, force_genres=False):
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        
        changed = False
        
        artist_elements = root.findall('.//artist')
        for artist_elem in artist_elements:
            if artist_elem.text:
                original = artist_elem.text.strip()
                artists = parse_artists(original)
                
                if len(artists) > 1:
                    formatted = format_artists_to_semicolon(artists)
                    
                    if formatted != original:
                        if not dry_run:
                            artist_elem.text = formatted
                        changed = True
                        print(f"  Artist: '{original}' → '{formatted}'")
        
        if fetch_genres:
            existing_genres = root.findall('.//genre')
            
            needs_genre_fetch = False
            
            if force_genres:
                needs_genre_fetch = True
                if existing_genres:
                    print(f"  Force mode: replacing existing genres: {', '.join([g.text for g in existing_genres if g.text])}")
                else:
                    print("  Force mode: fetching genres from MusicBrainz...")
            elif not existing_genres:
                needs_genre_fetch = True
                print("  No genres found, fetching from MusicBrainz...")
            elif all(not g.text or not g.text.strip() for g in existing_genres):
                needs_genre_fetch = True
                print("  Empty genres found, fetching from MusicBrainz...")
            elif len(existing_genres) == 1 and existing_genres[0].text and existing_genres[0].text.strip().lower() == 'music':
                needs_genre_fetch = True
                print("  Generic 'Music' genre found, replacing with specific genres...")
            else:
                print(f"  Genres already exist: {', '.join([g.text for g in existing_genres if g.text])}")
            
            if needs_genre_fetch:
                mb_id = get_musicbrainz_id_from_nfo(root)
                
                if not mb_id:
                    album_elem = root.find('.//title')
                    artist_elem = root.find('.//artist')
                    
                    if album_elem is not None and artist_elem is not None:
                        album_name = album_elem.text
                        artist_name = artist_elem.text
                        
                        if album_name and artist_name:
                            print(f"  Searching for: {album_name} by {artist_name}")
                            mb_id = search_album_on_musicbrainz(album_name, artist_name)
                
                if mb_id:
                    genres = get_genres_from_musicbrainz(mb_id)
                    
                    if genres:
                        for genre_elem in existing_genres:
                            root.remove(genre_elem)
                        
                        for genre in genres:
                            genre_elem = ET.SubElement(root, 'genre')
                            genre_elem.text = genre
                        
                        print(f"  Added genres: {', '.join(genres)}")
                        changed = True
                    else:
                        print("  No genres found on MusicBrainz")
                else:
                    print("  Could not find album on MusicBrainz")
        
        if changed and not dry_run:
            if backup:
                backup_path = str(nfo_path) + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                shutil.copy2(nfo_path, backup_path)
            
            ET.indent(tree, space="  ")
            tree.write(nfo_path, encoding='utf-8', xml_declaration=True)
            return True, True, "Updated successfully"
        elif changed and dry_run:
            return True, True, "Would be updated (dry run)"
        else:
            return True, False, "No changes needed"
            
    except ET.ParseError as e:
        return False, False, f"XML parse error: {e}"
    except Exception as e:
        return False, False, f"Error: {e}"


def process_directory(music_dir, dry_run=False, backup=True, fetch_genres=False, force_genres=False):
    music_path = Path(music_dir)
    
    if not music_path.exists():
        print(f"Error: Directory '{music_dir}' does not exist!")
        return
    
    nfo_files = list(music_path.rglob('*.nfo'))
    
    if not nfo_files:
        print(f"No .nfo files found in '{music_dir}'")
        return
    
    print(f"Found {len(nfo_files)} .nfo file(s)")
    if dry_run:
        print("Running in DRY RUN mode - no files will be modified")
    if backup:
        print("Backup enabled - original files will be preserved")
    if fetch_genres:
        print("Genre fetching enabled - will query MusicBrainz for missing genres")
    if force_genres:
        print("FORCE mode enabled - will replace ALL existing genres with MusicBrainz data")
    print()
    
    stats = {'processed': 0, 'updated': 0, 'errors': 0}
    
    for nfo_file in nfo_files:
        print(f"\nProcessing: {nfo_file}")
        success, changed, message = update_nfo_file(nfo_file, dry_run, backup, fetch_genres, force_genres)
        
        stats['processed'] += 1
        if success and changed:
            stats['updated'] += 1
        elif not success:
            stats['errors'] += 1
            print(f"  ERROR: {message}")
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Files processed: {stats['processed']}")
    print(f"Files updated:   {stats['updated']}")
    print(f"Errors:          {stats['errors']}")
    
    if dry_run and stats['updated'] > 0:
        print("\nThis was a dry run. Run without --dry-run to apply changes.")


def main():
    parser = argparse.ArgumentParser(
        description='Update Jellyfin music .nfo files with formatted artists and MusicBrainz genres'
    )
    parser.add_argument(
        'music_dir',
        help='Path to your Jellyfin music library directory'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without actually modifying files'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup files (not recommended)'
    )
    parser.add_argument(
        '--fetch-genres',
        action='store_true',
        help='Fetch and add genre information from MusicBrainz'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force refetch all genres from MusicBrainz, replacing existing ones (requires --fetch-genres)'
    )
    
    args = parser.parse_args()
    
    if args.force and not args.fetch_genres:
        parser.error("--force requires --fetch-genres to be enabled")
    
    process_directory(
        args.music_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        fetch_genres=args.fetch_genres,
        force_genres=args.force
    )


if __name__ == '__main__':
    main()